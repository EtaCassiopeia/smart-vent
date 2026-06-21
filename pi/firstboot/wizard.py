#!/usr/bin/env python3
"""First-boot AP-mode WiFi onboarding for smart-vent.

Run by smart-vent-firstboot.service as root. The wizard:

  1. Brings up an AP on wlan0 named "smart-vent-setup-<short-eui>"
     with WPA2, IP 192.168.4.1, DHCP 192.168.4.10-50.
  2. Runs a small Flask app on :80 that scans visible SSIDs and
     accepts the client's home WiFi credentials.
  3. Tears down the AP, writes an NM connection, joins the home
     network. On success writes /var/lib/smart-vent/.configured
     and reboots — which puts smart-vent.service in charge.

This is intentionally ~250 LOC of Python rather than something like
comitup so that:

  - The SSID and captive page are branded smart-vent rather than the
    upstream's defaults — matches what's printed on the kit-card.
  - We keep using NetworkManager (Bookworm default) rather than
    swapping the whole network stack for an alternative.
  - One systemd unit, one process; no shell-out maze.
"""
from __future__ import annotations

import logging
import re
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

try:
    from flask import Flask, redirect, render_template, request, url_for
except ImportError:
    sys.stderr.write(
        "wizard.py needs python3-flask. "
        "apt install python3-flask, or rerun install.sh.\n"
    )
    raise

# ----------------------------------------------------------------- constants
AP_INTERFACE = "wlan0"
AP_IP = "192.168.4.1"
AP_NETMASK = "24"
DHCP_RANGE = "192.168.4.10,192.168.4.50,12h"
NM_CON_NAME = "smart-vent-home"

STATE_FLAG = Path("/var/lib/smart-vent/.configured")
AP_PASSWORD_FILE = Path("/etc/smart-vent/ap-password")
DEFAULT_AP_PASSWORD = "smart-vent-setup"

RUN_DIR = Path("/run/smart-vent")
HOSTAPD_CONF = RUN_DIR / "hostapd.conf"
DNSMASQ_CONF = RUN_DIR / "dnsmasq.conf"
DNSMASQ_LEASES = RUN_DIR / "dnsmasq.leases"

logging.basicConfig(
    level=logging.INFO,
    format="firstboot: %(message)s",
)
log = logging.getLogger("firstboot")

# Sub-processes we own; torn down on shutdown / on join success.
_subprocs: list[subprocess.Popen] = []


# ============================================================ helpers
def short_eui() -> str:
    """Last 4 hex chars of the wlan0 MAC, lowercase, no separators."""
    mac = Path(f"/sys/class/net/{AP_INTERFACE}/address").read_text().strip()
    return mac.replace(":", "").lower()[-4:]


def ap_ssid() -> str:
    return f"smart-vent-setup-{short_eui()}"


def ap_password() -> str:
    """Operator-overridable AP password; default is the printed one.

    /etc/smart-vent/ap-password takes precedence so the provider can
    bake a per-kit password into the SD image. Must be >= 8 chars
    (WPA2 minimum); falls back to default otherwise.
    """
    if AP_PASSWORD_FILE.exists():
        pw = AP_PASSWORD_FILE.read_text().strip()
        if len(pw) >= 8:
            return pw
        log.warning(
            "AP password in %s is too short (<8 chars); using default.",
            AP_PASSWORD_FILE,
        )
    return DEFAULT_AP_PASSWORD


def run(cmd: list[str], *, check: bool = True, **kw) -> subprocess.CompletedProcess:
    log.info("$ %s", " ".join(cmd))
    return subprocess.run(cmd, check=check, text=True, **kw)


# ============================================================ AP bring-up
def write_hostapd_conf(ssid: str, password: str) -> None:
    HOSTAPD_CONF.write_text(textwrap.dedent(f"""\
        interface={AP_INTERFACE}
        driver=nl80211
        ssid={ssid}
        hw_mode=g
        channel=6
        auth_algs=1
        wpa=2
        wpa_passphrase={password}
        wpa_key_mgmt=WPA-PSK
        wpa_pairwise=TKIP
        rsn_pairwise=CCMP
    """))


def write_dnsmasq_conf() -> None:
    DNSMASQ_CONF.write_text(textwrap.dedent(f"""\
        interface={AP_INTERFACE}
        bind-interfaces
        dhcp-range={DHCP_RANGE}
        dhcp-leasefile={DNSMASQ_LEASES}
        # Captive-portal style: resolve everything to ourselves so the
        # client phone's connectivity probe sees the wizard page.
        address=/#/{AP_IP}
        no-resolv
        log-queries
        log-dhcp
    """))


def bring_up_ap(ssid: str, password: str) -> None:
    log.info("Bringing up AP %r on %s ...", ssid, AP_INTERFACE)
    RUN_DIR.mkdir(parents=True, exist_ok=True)

    # NM must not fight us for wlan0 while the AP is up.
    run(["nmcli", "device", "set", AP_INTERFACE, "managed", "no"], check=False)

    # Reset interface to a known state, give it the AP IP.
    run(["ip", "addr", "flush", "dev", AP_INTERFACE], check=False)
    run(["ip", "link", "set", AP_INTERFACE, "up"], check=False)
    run(["ip", "addr", "add", f"{AP_IP}/{AP_NETMASK}", "dev", AP_INTERFACE])

    write_hostapd_conf(ssid, password)
    write_dnsmasq_conf()

    # Stop systemd's copies if they happen to be running; we manage
    # both processes directly.
    for unit in ("hostapd.service", "dnsmasq.service"):
        run(["systemctl", "stop", unit], check=False)

    _subprocs.append(subprocess.Popen(["hostapd", str(HOSTAPD_CONF)]))
    _subprocs.append(subprocess.Popen(
        ["dnsmasq", "--no-daemon", "--conf-file=" + str(DNSMASQ_CONF)],
    ))
    log.info("AP %r is up at http://%s/", ssid, AP_IP)


def tear_down_ap() -> None:
    log.info("Tearing down AP processes...")
    for p in _subprocs:
        try:
            p.terminate()
        except Exception:
            pass
    for p in _subprocs:
        try:
            p.wait(timeout=5)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
    _subprocs.clear()
    run(["ip", "addr", "flush", "dev", AP_INTERFACE], check=False)
    run(["nmcli", "device", "set", AP_INTERFACE, "managed", "yes"], check=False)


# ============================================================ scan + join
def scan_ssids() -> list[str]:
    """Return visible non-empty SSIDs, deduplicated, signal-sorted."""
    # nmcli requires NM to manage the interface for scanning, but we
    # set it unmanaged above. Easiest workaround: ask nmcli to rescan
    # while temporarily reclaiming the iface? Simpler: use `iw scan`
    # which talks to nl80211 directly.
    result = run(
        ["iw", "dev", AP_INTERFACE, "scan", "ap-force"],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        log.warning("iw scan failed (rc=%s); SSID list will be empty.", result.returncode)
        return []

    ssids = []
    seen = set()
    for line in result.stdout.splitlines():
        m = re.match(r"\s*SSID: (.+)", line)
        if not m:
            continue
        ssid = m.group(1).strip()
        if not ssid or ssid in seen:
            continue
        seen.add(ssid)
        ssids.append(ssid)
    return ssids


def join_home_wifi(ssid: str, password: str) -> bool:
    """Switch wlan0 to client mode and try to join the home network."""
    log.info("Tearing down AP, switching to client mode for SSID %r ...", ssid)
    tear_down_ap()

    # Remove any prior smart-vent-home connection so re-runs don't pile up.
    run(["nmcli", "connection", "delete", NM_CON_NAME], check=False)
    add = run(
        [
            "nmcli", "connection", "add",
            "type", "wifi",
            "ifname", AP_INTERFACE,
            "con-name", NM_CON_NAME,
            "ssid", ssid,
            "wifi-sec.key-mgmt", "wpa-psk",
            "wifi-sec.psk", password,
            "connection.autoconnect", "yes",
        ],
        check=False,
    )
    if add.returncode != 0:
        return False

    up = run(["nmcli", "connection", "up", NM_CON_NAME], check=False, capture_output=True)
    if up.returncode == 0:
        log.info("Joined %r.", ssid)
        return True

    log.warning("nmcli connection up failed: %s", up.stderr.strip())
    # Clean up the bad connection so we don't retry it forever.
    run(["nmcli", "connection", "delete", NM_CON_NAME], check=False)
    return False


# ============================================================ flask app
app = Flask(
    "smart-vent-firstboot",
    template_folder=str(Path(__file__).resolve().parent / "templates"),
    static_folder=str(Path(__file__).resolve().parent / "static"),
)


@app.route("/", methods=["GET"])
def index():
    return render_template(
        "index.html",
        ssid=ap_ssid(),
        ssids=scan_ssids(),
    )


# Captive-portal hint endpoints: phones probe these and follow the redirect.
@app.route("/generate_204")
@app.route("/hotspot-detect.html")
@app.route("/connecttest.txt")
@app.route("/ncsi.txt")
def captive_probe():
    return redirect(url_for("index"), code=302)


@app.route("/join", methods=["POST"])
def join():
    ssid = (request.form.get("ssid") or "").strip()
    password = request.form.get("password") or ""

    if not ssid:
        return render_template("index.html", ssid=ap_ssid(), ssids=scan_ssids(),
                               error="Please pick a network."), 400
    if len(password) < 8:
        return render_template("index.html", ssid=ap_ssid(), ssids=scan_ssids(),
                               error="WPA2 passwords need at least 8 characters."), 400

    # Render the joining page first so the user sees feedback before we
    # drop the AP from under them.
    page = render_template("joining.html", ssid=ssid)

    def _finish():
        # Give the response time to flush back over the AP before we
        # tear it down.
        time.sleep(2)
        if join_home_wifi(ssid, password):
            STATE_FLAG.parent.mkdir(parents=True, exist_ok=True)
            STATE_FLAG.touch()
            log.info("Onboarding succeeded; rebooting.")
            run(["systemctl", "reboot"], check=False)
        else:
            log.warning("Onboarding failed; bringing the AP back up.")
            bring_up_ap(ap_ssid(), ap_password())

    # Schedule _finish in a child thread so Flask returns the HTML first.
    import threading
    threading.Thread(target=_finish, daemon=True).start()
    return page


# ============================================================ main
def _shutdown(*_):
    tear_down_ap()
    sys.exit(0)


def main() -> int:
    if STATE_FLAG.exists():
        log.info(".configured already exists; nothing to do.")
        return 0

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    bring_up_ap(ap_ssid(), ap_password())
    log.info(
        "Wizard listening on %s:80 (SSID %r, password %r).",
        AP_IP, ap_ssid(), ap_password(),
    )
    app.run(host="0.0.0.0", port=80, debug=False, use_reloader=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
