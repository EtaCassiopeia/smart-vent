# First-boot AP-mode WiFi onboarding

Run by `smart-vent-firstboot.service` (see `../systemd/`). Brings up a
WPA2 AP, serves a captive-style page where the client picks their home
WiFi, switches to client mode, and reboots into the main runtime.

## Files

```
firstboot/
  wizard.py         The systemd ExecStart target. ~250 LOC.
  templates/
    index.html      Captive page (SSID picker + password)
    joining.html    "Joining now…" page shown after submit
  static/
    style.css       Minimal mobile-first styling
```

## Why not comitup / RaspiWiFi

The plan said "spike comitup first, only build custom if it doesn't
fit." For this project, custom fits better:

- We need branded UX (the SSID and captive-page styling match the
  printed kit-card). comitup forces `comitup-<host>` SSIDs.
- We're keeping NetworkManager as the Bookworm default; comitup
  replaces the whole network stack.
- The code is small (~250 LOC) — less integration surface than the
  comitup adapter would be.

## Behaviour

On startup the wizard:

1. Computes `smart-vent-setup-<short-eui>` from wlan0's MAC.
2. Reads the AP password from `/etc/smart-vent/ap-password`
   (operator-overridable, baked by the SD image / `install.sh`).
   Falls back to a printed default if absent.
3. Sets `wlan0` to unmanaged in NetworkManager, gives it
   `192.168.4.1/24`, writes minimal `hostapd.conf` and
   `dnsmasq.conf` to `/run/smart-vent/`, and spawns both as
   children.
4. Runs a Flask app on `:80`. Captive-portal probe URLs
   (`/generate_204`, `/hotspot-detect.html`, etc.) all 302 to the
   wizard page so iOS / Android pop the captive sheet.
5. On form POST: tears down the AP, reclaims the interface for
   NetworkManager, creates a `smart-vent-home` NM connection with
   the submitted creds, runs `nmcli connection up`, and on success
   writes `/var/lib/smart-vent/.configured` and reboots.

After reboot `smart-vent-firstboot.service` is skipped (the
`.configured` flag is present), `smart-vent.service` runs, and the
hub containers come up.

## Debugging

The wizard is a systemd service; its stdout/stderr land in journald:

```bash
journalctl -u smart-vent-firstboot.service -f
```

Each subprocess invocation is logged (`$ nmcli connection add ...`)
so you can replay them by hand if something fails.

If the AP comes up but you can't reach `http://192.168.4.1/`, check:

- `ip addr show wlan0` includes `192.168.4.1/24`
- `ss -tlnp '( sport = :80 )'` shows the python3 wizard
- `journalctl -u smart-vent-firstboot.service` for hostapd/dnsmasq
  failures

If the wizard wedges (panel-edge bug, can't reach Flask), reboot
the Pi — the wizard restarts cleanly because every step is
idempotent.
