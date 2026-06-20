# smart-vent Runbook

Step-by-step procedures. Every section has copy-paste commands and a
verification step. When you want to understand **why** a step matters, the
matching handbook section is linked at the top. Numbered cross-refs to
**[handbook.md](handbook.md)** are written as "handbook §N".

---

## 1. How to use this runbook

Read this once to find your starting point.

- **First time setting up the whole system on a new Pi?** Start at §2.
- **Pi already runs OTBR + matter-server + HA, just adding a new vent?**
  Start at §5 (flash) then §6 (commission) then §7 (room).
- **Something is broken**: jump to the troubleshooting matrix in §10.
- **Looking for a one-liner you saw before?** §11 (cheatsheet).

### Quick start: flash and commission vent N+1

You already have the firmware built, the Pi services running, and at least
one vent commissioned. You want to add another.

```bash
# 1. Plug the new XIAO directly into the Pi USB. Verify:
lsusb -d 303a:                                      # expect one row

# 2. Put it in download mode: hold BOOT, replug, release BOOT.

# 3. Flash (full command — see §5.3 for what each flag does):
cd ~/code/smart-vent/firmware/vent-controller
espflash flash \
  --partition-table partitions.csv \
  --bootloader target/riscv32imac-esp-espidf/release/build/esp-idf-sys-*/out/build/bootloader/bootloader.bin \
  --port /dev/ttyACM0 \
  target/riscv32imac-esp-espidf/release/vent-controller

# 4. Unplug+replug (NO BOOT hold this time). Watch serial for pairing code:
cat /dev/ttyACM0 | grep -m1 "Manual pairing code"

# 5. Open HA, Settings → Devices → Add Integration → Matter, paste the code.

# 6. Once HA shows the new cover entity, set its Area to the right room.
```

If anything misbehaves, see §10. Full details for each step are in §5–§7.

---

## 2. Dev environment on the Pi

The Pi is both your build host and your runtime host. Everything lives on
the Pi.

> **Why**: handbook §3 explains why all services run on the Pi (host
> network mode, BLE access, OTBR routing).

### 2.1 OS and kernel modules

Raspberry Pi OS (Debian-based). Anything modern (Bookworm or newer) works.

Load the IPv6 netfilter modules OTBR needs, and persist them:

```bash
sudo modprobe ip6_tables
sudo modprobe ip6table_filter

# Make it stick across reboot:
echo 'ip6_tables' | sudo tee /etc/modules-load.d/otbr.conf
echo 'ip6table_filter' | sudo tee -a /etc/modules-load.d/otbr.conf

# Verify:
lsmod | grep -E '^ip6_tables|^ip6table_filter'
```

Expect two non-empty lines. Without these, OTBR comes up but can't route
IPv6 between Thread and wlan0; symptom is "device on Thread but
matter-server times out forever." See §10.9.

### 2.2 Docker and base tools

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin \
                    curl wscat avahi-utils bluez \
                    libssl-dev pkg-config build-essential \
                    git python3-pip python3-venv

sudo usermod -aG docker $USER         # log out and back in for this to apply
```

Verify:
```bash
docker info | grep -E 'Server Version|Operating System'
```

### 2.3 Rust + ESP toolchain (for building firmware)

We use **nightly Rust** (the `rust-toolchain.toml` requests `channel="esp"`,
but `espup` on the Pi only installs the RISC-V targets, so we override with
`RUSTUP_TOOLCHAIN=nightly` at build time).

```bash
# rustup
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
. "$HOME/.cargo/env"
rustup install nightly
rustup component add rust-src --toolchain nightly

# espup for the ESP-IDF / RISC-V targets
cargo install espup
espup install --targets riscv32imac-esp-espidf

# Helper tools (linker proxy + flasher)
cargo install ldproxy
cargo install espflash --version '^3'
```

Verify:
```bash
rustup toolchain list                 # nightly should be there
which ldproxy espflash                # both should resolve
```

### 2.4 Swap (for the build, not runtime)

The Matter SDK + esp-idf-sys release link uses ~3 GB of RAM at peak. Pi 4B
has 4 GB or 8 GB; with a fresh boot it can build, but it's slow because
Linux falls back to small swap. Add 4 GB swap to be safe:

```bash
sudo fallocate -l 4G /var/swap2
sudo chmod 600 /var/swap2
sudo mkswap /var/swap2
sudo swapon /var/swap2
echo '/var/swap2 none swap sw 0 0' | sudo tee -a /etc/fstab
free -h                              # confirm 4G+ swap
```

### 2.5 USB / udev permissions

Allow your user to access the XIAO and the SLZB-07 without sudo. Drop this
file:

```bash
sudo tee /etc/udev/rules.d/99-vent.rules <<'EOF'
# Espressif ESP32 (XIAO C6)
SUBSYSTEM=="tty", ATTRS{idVendor}=="303a", ATTRS{idProduct}=="1001", \
  GROUP="plugdev", MODE="0660"
# SMLIGHT SLZB-07 (CP210x)
SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", \
  GROUP="dialout", MODE="0660"
EOF

sudo udevadm control --reload-rules
sudo udevadm trigger

# Make sure your user is in those groups:
sudo usermod -aG plugdev,dialout $USER       # log out + back in
```

Verify:
```bash
ls -la /dev/ttyACM0 /dev/ttyUSB0
# Expect group plugdev / dialout, mode 660. Your user is in both groups.
```

---

## 3. Pi services bring-up

Three Docker containers: OTBR, matter-server, Home Assistant. All host
networking.

> **Why**: handbook §3 walks through what each container does and why
> host networking is required.

### 3.1 OTBR — Thread border router

Plug the SLZB-07 dongle into a Pi USB port (direct, not through a hub).
Verify it shows up:

```bash
lsusb -d 10c4:ea60         # expect "SMLIGHT SLZB-07"
ls -l /dev/ttyUSB0          # exists
```

Determine your "backbone" interface (the one with your LAN IP):

```bash
ip route show default       # something like "default via 192.168.1.1 dev wlan0"
BACKBONE=wlan0              # adjust if you use eth0
```

Start OTBR:

```bash
docker run -d \
  --name otbr \
  --restart unless-stopped \
  --network host \
  --privileged \
  -v /dev:/dev \
  -v otbr-data:/var/lib/thread \
  -e RADIO_URL="spinel+hdlc+uart:///dev/ttyUSB0?uart-baudrate=460800" \
  -e BACKBONE_INTERFACE="${BACKBONE}" \
  openthread/otbr:latest
```

Wait ~10 s, then verify it formed a network and is leader:

```bash
docker exec otbr ot-ctl state           # expect: "leader"
docker exec otbr ot-ctl dataset active  # expect a populated dataset
```

**If `state` is `disabled`**, the network didn't form. Either form one
manually with `ot-ctl dataset init new; ot-ctl dataset commit active;
ot-ctl ifconfig up; ot-ctl thread start`, or restore a previously
backed-up dataset (see §9.4). Form-new is the right move on a fresh
install.

**Back up the dataset** (in case OTBR's volume ever needs restoring):

```bash
mkdir -p ~/.thread
docker exec otbr ot-ctl dataset active -x | tr -d '[:space:]' > ~/.thread/dataset-backup.txt
chmod 600 ~/.thread/dataset-backup.txt
```

### 3.2 matter-server — Matter controller

```bash
mkdir -p ~/matter-server

docker run -d \
  --name matter-server \
  --restart unless-stopped \
  --network host \
  --security-opt apparmor=unconfined \
  -v ~/matter-server:/data \
  -v /run/dbus:/run/dbus:ro \
  ghcr.io/home-assistant-libs/python-matter-server:stable \
  --storage-path /data --paa-root-cert-dir /data/credentials \
  --primary-interface wlan0 --bluetooth-adapter 0
```

Adjust `--primary-interface` if you use `eth0`. `--bluetooth-adapter 0`
means `hci0`.

Verify the WebSocket is reachable:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5580
# Expect 200 (or a 400-class — it's a WS endpoint, just needs to respond)

docker logs --tail 20 matter-server | grep -i 'initialized\|listening\|started'
```

### 3.3 Home Assistant

```bash
mkdir -p ~/homeassistant

docker run -d \
  --name homeassistant \
  --restart unless-stopped \
  --network host \
  -v ~/homeassistant:/config \
  -v /etc/localtime:/etc/localtime:ro \
  ghcr.io/home-assistant/home-assistant:stable
```

Open `http://<pi-ip>:8123` in a browser. Create an account.

Add the **Matter (BETA)** integration:

1. Settings → Devices & services → Add integration.
2. Search for "Matter".
3. When prompted for the matter-server URL, enter
   `ws://localhost:5580/ws`.
4. Submit. HA connects to matter-server and the integration appears as
   healthy.

The HA Android app (separate install) is what you'll use for the actual
BLE commissioning UX in §6. The web UI can also do it; the app is more
reliable on the BLE side.

### 3.4 Verification checklist

```bash
docker ps --format '{{.Names}}: {{.Status}}'
# Expect three containers, all Up.

docker exec otbr ot-ctl state               # leader
docker exec otbr ot-ctl child table         # may be empty if no devices yet

curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5580 # 4xx/200
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8123 # 2xx

avahi-browse -art -t _matter._tcp _matterc._udp     # empty is OK pre-commission
```

Pi side is now ready.

---

## 4. Build the firmware

> **Why**: handbook §4.2 explains the stack (Rust → esp-idf-sys → esp-matter
> → CHIP).

The firmware lives in `firmware/vent-controller/`. You build once, then
flash the same binary to every vent.

```bash
cd ~/code/smart-vent/firmware/vent-controller

# Build (this takes 15–25 min on a Pi 4 the first time, ~3 min on incremental)
RUSTUP_TOOLCHAIN=nightly cargo build --release
```

Outputs:

```
target/riscv32imac-esp-espidf/release/vent-controller             # the app ELF
target/riscv32imac-esp-espidf/release/build/esp-idf-sys-*/out/build/
  bootloader/bootloader.bin                                       # CRITICAL for flash
  partition_table/partition-table.bin                             # informational
```

Verify the app exists:

```bash
ls -la target/riscv32imac-esp-espidf/release/vent-controller
# Should be ~5 MB
```

Locate the bootloader:

```bash
ls target/riscv32imac-esp-espidf/release/build/esp-idf-sys-*/out/build/bootloader/bootloader.bin
```

Note the path — you will pass it to `espflash`. **Always.** Skipping the
`--bootloader` flag uses espflash's bundled v5.5.1 stub which can't load
our v5.2.3 app; see §10.1.

### 4.1 Re-build after editing C++ side or sdkconfig

Cargo's incremental rebuild doesn't always notice when `sdkconfig.defaults`
or files under `components/esp_matter_bridge/` change. Force a CMake
re-config:

```bash
rm -rf target/riscv32imac-esp-espidf/release/build/esp-idf-sys-*/out/build
touch sdkconfig.defaults
touch src/main.rs
RUSTUP_TOOLCHAIN=nightly cargo build --release
```

The CMake re-config adds ~5–10 minutes vs. an incremental Rust-only build.

---

## 5. Flash a new vent

> **Why**: handbook §4.1 and §8 explain the hardware and what the device
> does during a fresh boot. Handbook §10.6/§10.7 explain why each command
> flag matters.

### 5.1 Plug in the XIAO

Plug the XIAO ESP32-C6 **directly** into a Pi USB port. Not through a
USB hub.

Verify it enumerated:

```bash
lsusb -d 303a:
# Expect: Espressif USB JTAG/serial debug unit  (vendor 303a:1001)

ls /dev/ttyACM0
# Expect: the file exists.

dmesg | tail -10 | grep -i ttyACM        # confirm fresh enumeration
```

If `lsusb -d 303a:` returns nothing, you're plugged into the USB hub.
Move to a direct port (§10.10).

### 5.2 Enter download mode (BOOT-hold + replug)

Every reflash on the C6 needs manual download-mode entry. The XIAO has
two tiny buttons next to the USB-C connector: **B** (BOOT) and **R**
(RESET).

Procedure:

1. **Press and hold B** (the BOOT button).
2. While still holding B, **unplug the USB cable** (or press R briefly).
3. **Replug the USB cable** (or release R), still holding B.
4. **Wait ~1 second**, then **release B**.

The XIAO is now in ROM download mode. `/dev/ttyACM0` re-enumerated; espflash
can now talk to the ROM USB driver. If you forget the BOOT-hold, espflash
hangs at `Connecting...` for ~30 s and gives up (§10.3).

### 5.3 Flash with the correct bootloader

From `firmware/vent-controller/`:

```bash
espflash flash \
  --partition-table partitions.csv \
  --bootloader target/riscv32imac-esp-espidf/release/build/esp-idf-sys-*/out/build/bootloader/bootloader.bin \
  --port /dev/ttyACM0 \
  target/riscv32imac-esp-espidf/release/vent-controller
```

What each flag does:

| Flag | What | Why |
|------|------|-----|
| `--partition-table partitions.csv` | Flashes our 3 MB factory app layout | The compiled-in default uses a different layout |
| `--bootloader .../out/build/bootloader/bootloader.bin` | Flashes the matching v5.2.3 bootloader | Without it, espflash uses its bundled v5.5.1 stub which rejects our app — boot loop with `rst:0x3 LP_SW_HPSYS` (§10.1) |
| `--port /dev/ttyACM0` | Which serial port to talk to | XIAO's USB Serial/JTAG |
| positional arg | The app ELF | espflash reads it, extracts segments, writes the factory partition |

Expected output (last lines):
```
App/part. size:    2,123,904/3,145,728 bytes, 67.52%
Flashing has completed!
```

This takes ~10 s.

### 5.4 Optional: wipe NVS

Use this **only** when you want a fresh, uncommissioned device. Specifically:

- After changing Matter cluster configuration (added/removed a feature flag,
  changed cluster IDs, etc.).
- When the device is "commissioned-but-unreachable" for >5 minutes and §10.5
  fixes haven't helped.
- When matter-server has lost its fabric and the device is orphaned.

```bash
# Device must still be in download mode (BOOT-hold + replug again if needed).
espflash erase-partition --port /dev/ttyACM0 nvs
```

After NVS wipe the device will, on next boot, advertise BLE for re-commissioning
(it doesn't know its fabric or Thread network anymore). See §6.

### 5.5 Power-cycle and verify

Unplug and replug the USB cable (no BOOT-hold). The XIAO boots normally.
Watch the serial output:

```bash
stty -F /dev/ttyACM0 115200 raw -echo
cat /dev/ttyACM0
```

Expected sequence (the timing in parentheses is seconds since boot):

```
(0.0)   I (22)  boot: ESP-IDF v5.2.3 2nd stage bootloader     <- matching bootloader ✓
(0.1)   I (24)  cpu_start: ESP-IDF: v5.2.3
(0.2)   ...     Project name: libespidf
(0.5)   I       Vent Controller v0.1.0
(1.0)   I       EUI-64: 58:e6:c5:01:0a:dc                    <- per-board identifier
(1.5)   I       Restoring checkpoint: 90° / 180°              <- or first boot defaults
(2.0)   I       Setting OpenThread device type to MINIMAL END DEVICE
(2.5)   I       chip[SVR]: Server initialization complete
(3.0)   I       Manual pairing code: 34970112332              <- write this down if commissioning
(3.0)   I       QR code payload: MT:....
(5–30)  I       (uncommissioned) NimBLE GAP: advertising started
                (commissioned)   Mle-----------: Send Parent Request
(10–60) I       Mle-----------: attached as Child
```

If you see this sequence ending with "attached as Child" or with BLE
advertising, the flash was successful. If you see `rst:0x3` repeating
within 100 ms, the bootloader is wrong (§10.1). If you see
`rst:0x7 TG0_WDT_HPSYS` after 30–200 s, Wi-Fi wasn't disabled (§10.2).

Press Ctrl+C to stop the serial dump.

---

## 6. Commission via Home Assistant

> **Why**: handbook §6 walks through the full commissioning protocol — BLE
> PASE → operational credentials → Thread credential push → CASE handoff.

### 6.1 Get the setup code

The firmware logs the manual pairing code and QR payload on every boot.
Capture it cleanly from a freshly-booted device:

```bash
stty -F /dev/ttyACM0 115200 raw -echo
cat /dev/ttyACM0 | head -n 200 | grep -E "Manual pairing code|QR code payload"
```

Sample output:

```
Manual pairing code: 34970112332
QR code payload: MT:Y.K90E0KL4D5GVB10
```

Either works. The QR payload is the same code, encoded for QR scanning.

> If you missed it, power-cycle the device (unplug+replug, no BOOT-hold)
> — the codes are emitted again on each boot, and the device starts a
> fresh BLE fast-adv window on each boot too (handbook §6.2).

### 6.2 Pair via the HA Android app (or web UI)

The HA Android app handles the BLE-side commissioning more reliably than
the web UI. Either works.

**Android app path** (recommended):

1. Install **Home Assistant** from the Play Store. Sign in with your HA
   account.
2. Settings → Devices & services → Add Integration → Matter.
3. Tap "Scan QR code" or "Enter setup code manually".
4. Enter the code from §6.1.
5. The app will scan BLE, find the device, and walk the commissioning
   sequence. Takes 30–90 s. You'll see status messages like "Pairing
   device... Configuring network... Finalizing commissioning..."

**Web UI path**:

1. In a browser on the Pi or a phone on the same network: HA web UI →
   Settings → Devices & services → Add Integration → Matter.
2. Choose "Setup code".
3. Paste the code. HA will hand it to matter-server, which scans BLE.
4. Sometimes the BLE side is unreliable here (BlueZ quirks). If pairing
   fails, restart BlueZ on the Pi and retry, or switch to the Android
   app.

You should also watch matter-server logs while pairing — it's the most
informative view:

```bash
docker logs -f matter-server | grep -E "Commission|PASE|CASE|Setup|Node|Error"
```

Expected: `Commissioning succeeded for node N`. The node ID (`N`) is
assigned by matter-server.

### 6.3 Post-commission verification

Right after commissioning, run through this checklist:

```bash
# 1. Device joined Thread?
docker exec otbr ot-ctl child table
# Expect a row with the device's EUI-64 (matches what serial logged).

# 2. Device's SRP record registered?
docker exec otbr ot-ctl srp server host
docker exec otbr ot-ctl srp server service
# Expect a host like "<fabric-id>-<node-id>" and a _matter._tcp service.

# 3. mDNS visible from the Pi host?
avahi-browse -art -t _matter._tcp 2>/dev/null | grep matter
# Expect the same fabric-id-node-id record.

# 4. matter-server has it as a known node?
docker logs --tail 30 matter-server | grep -E "Node:.*Re-Subscription|Node:.*Discovered"
# Expect "Re-Subscription succeeded" or "Discovered on mDNS".

# 5. Functional test from HA: click Close, then Open. Vent should move.
```

Items 1+2 are the device's side. Item 3 is OTBR's mDNS proxy. Item 4 is
matter-server. If 1 and 2 are green but 3 or 4 are not, see §10.5. If 1
is green but 2 is empty for >5 min, see §10.5.

### 6.4 Fallback — direct IP commissioning

When BLE keeps failing **and** the device is already on Thread from a
previous attempt (uncommon, but happens if commissioning was interrupted
after the Thread push but before the operational handoff), you can
commission over IP.

Find the device's OMR IPv6 address — it logs every address it gets in
the serial output:

```bash
cat /dev/ttyACM0 | grep -E "Address.*added|interface.*up|fdbf:|fdf6:" | head
```

Or from OTBR's side: any non-link-local address it lists for the device.

Then commission via matter-server's WebSocket API. Example Python
snippet (the same script template we used in earlier sessions; see
`/tmp/commission_ip.py` if it's still around, otherwise write a fresh
script):

```python
# /tmp/commission_ip.py
import asyncio, json, websockets

async def main():
    async with websockets.connect("ws://localhost:5580/ws") as ws:
        await ws.recv()       # server hello
        msg = {
            "message_id": "1",
            "command": "commission_with_code",
            "args": {
                "code": "34970112332",
                "network_only": False,
                "ip_addr": "fdbf:cc11:94a3:1e8c:d3db:7cd4:67b1:a636",
            },
        }
        await ws.send(json.dumps(msg))
        print(json.loads(await ws.recv()))

asyncio.run(main())
```

Run with `python3 /tmp/commission_ip.py`. The command path is the same
post-PASE; only the discovery is bypassed.

---

## 7. Assign to a room, floor, and entity name (HA Area + Floor)

Grouping vents by room or floor relies entirely on Home Assistant's
**Areas** (rooms) and **Floors** (since HA 2024.3). Set these up once,
then every vent you commission slots into the hierarchy.

### 7.1 Create Floors and Areas (once)

1. HA UI → Settings → **Areas, zones & labels**.
2. **Floors** tab → add one Floor per physical floor: "Basement",
   "Main Floor", "Upper Floor", ...
3. **Areas** tab → add one Area per room ("Living Room", "Study",
   "Bedroom 1", ...). For each Area, set its Floor.

You only need to do this once for the whole house.

### 7.2 Assign each commissioned vent to a room

For every vent after commissioning (§6):

1. Settings → Devices & services → Matter → click the new device.
2. **Rename the device**. HA assigns a default like "Window Covering"
   or "Smart HVAC Vent" (from the firmware's Basic Information).
   Change to e.g. "Living Room Vent 1".
3. **Set the Area**. Click the device's pencil icon → Area → pick the
   room. The cover entity inherits both the Area and (transitively)
   the Floor.
4. **Rename the entity_id** to a consistent pattern. Click the cover
   entity → settings (cog) → "Entity ID" → set to
   `cover.<room>_vent_<n>` (e.g. `cover.living_room_vent_1`,
   `cover.study_vent_2`). This is what the dashboards and per-entity
   scripts in `homeassistant/` target.

> The HA Area + Floor model is the only "grouping" you need. Nothing
> on the device knows about rooms — see handbook §9.3 / §9.4.

### 7.3 Quick check

Settings → Areas, zones & labels → Areas → click the vent's Area.
The cover entity should be listed under "Entities" with the new
name. Devices & services → Matter shows the device under its room.

---

## 7.5 Group control and scheduling

Once Areas and Floors exist, HA's standard `cover.*` services do all
the grouping work. The repo has ready-made templates in
`homeassistant/`:

| Template | What it gives you |
|---|---|
| `scripts.yaml` | `close_all_vents_on_floor`, `open_room_vents`, `set_vent_position`, and a per-entity granular example |
| `automations.yaml` | Daily time-of-day automations **and** Schedule-helper-driven automations |
| `helpers/schedule_helpers.yaml` | Weekly recurring windows editable as a calendar in the HA UI |
| `dashboards/vents.yaml` | A floor → room → entity Lovelace dashboard with whole-house, per-floor, and per-room buttons |

### 7.5.1 Install templates

```bash
# On the Pi, with HA already running (runbook §3.3):
cp -r ~/code/smart-vent/homeassistant/scripts.yaml         ~/homeassistant/
cp -r ~/code/smart-vent/homeassistant/automations.yaml     ~/homeassistant/
mkdir -p ~/homeassistant/helpers ~/homeassistant/dashboards
cp ~/code/smart-vent/homeassistant/helpers/schedule_helpers.yaml \
   ~/homeassistant/helpers/
cp ~/code/smart-vent/homeassistant/dashboards/vents.yaml \
   ~/homeassistant/dashboards/
```

Then edit `~/homeassistant/configuration.yaml` so HA loads them:

```yaml
script:    !include scripts.yaml
automation: !include automations.yaml
schedule:  !include helpers/schedule_helpers.yaml

lovelace:
  mode: storage
  dashboards:
    vents:
      mode: yaml
      title: Vents
      icon: mdi:air-filter
      show_in_sidebar: true
      filename: dashboards/vents.yaml
```

Replace placeholder `area_id`, `floor_id`, and `entity_id` values in
the copied files with the slugs HA assigned to your own Areas/Floors
and the entity_ids you picked in §7.2.

Reload via HA UI → Developer Tools → YAML → reload each section, or
`docker restart homeassistant` for a clean reload. Watch
`docker logs -f homeassistant` for YAML errors.

> **Note:** if you ran an earlier hub-based setup, the HA container
> may still carry a `-v .../devices.db:/config/devices.db` bind
> mount pointing at the now-removed legacy sqlite file. Inspect with
> `docker inspect homeassistant --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}'`.
> If present, re-create the container with the canonical command from
> §3.3 (no extra mounts) at a convenient time — the running container
> is healthy until it restarts.

### 7.5.2 Group call from the UI (sanity check)

Developer Tools → **Actions** → choose `cover.close_cover` →
Targets → Area → pick the room with your vent. Run. The vent moves.
Same with Floors. Same `cover.open_cover` / `cover.set_cover_position`.

### 7.5.3 Per-vent (granular) calls

When the entity_ids follow `cover.<room>_vent_<n>`, "close vents 1+2
in study, keep vent 3 open" is one service call:

```yaml
service: cover.close_cover
target:
  entity_id:
    - cover.study_vent_1
    - cover.study_vent_2
```

`scripts.yaml` ships `close_study_vents_1_and_2` as a one-tap version
of exactly this.

### 7.5.4 Schedule helpers (calendar style)

Settings → Devices & services → **Helpers** → click any
`schedule.*` helper → drag/draw windows on the weekly grid. The
matching automation in `automations.yaml` fires on the state edges.

### 7.5.5 Query vents and status

Three ways, depending on what you need:

- **Dashboard**: open the "Vents" sidebar entry — every vent appears
  under its floor → room with current position.
- **Developer Tools → States** → filter `entity_id` for `vent` → see
  every cover with `current_position`, `state`, `friendly_name`.
- **REST API** (good for scripts, future voice integrations):
  ```bash
  HA_TOKEN=...   # Profile → Long-Lived Access Tokens
  curl -s -H "Authorization: Bearer $HA_TOKEN" \
    http://localhost:8123/api/states \
    | jq '[.[] | select(.entity_id | startswith("cover.")) | {entity_id, state, position: .attributes.current_position, friendly_name: .attributes.friendly_name}]'
  ```

---

## 8. Add the next vent

The whole loop:

1. Build firmware: done once (§4). No rebuild needed for additional
   vents — same binary.
2. Plug the new XIAO in directly (§5.1).
3. BOOT-hold + replug → flash (§5.2 + §5.3).
4. Power-cycle (§5.5), capture the new pairing code from serial (§6.1).
5. Commission via HA Android app or web UI (§6.2).
6. Verify on Thread + SRP + HA (§6.3).
7. Assign to its room **and** rename the entity to
   `cover.<room>_vent_<n>` (§7.2). Doing this immediately keeps the
   `homeassistant/` templates and dashboard cards working as N grows.

Per device: ~2 minutes operator time + ~1–2 minutes waiting for boot
and BLE pairing.

The discriminator is derived from the EUI-64 per device (handbook §9.2),
so there's no manual config to change between units. The pairing code
is also unique-ish per device (derived from the SDK's default passcode
combined with the discriminator). If you wanted absolutely unique
passcodes you'd build a per-device factory partition, but we don't —
fine for a private home network.

---

## 9. Day-2 operations

### 9.1 Inspecting Thread mesh state

```bash
# Are we still leader, are routers/end-devices on the mesh?
docker exec otbr ot-ctl state
docker exec otbr ot-ctl leaderdata
docker exec otbr ot-ctl router table
docker exec otbr ot-ctl child table
docker exec otbr ot-ctl ipaddr            # all of OTBR's addresses

# Per-device: their advertised SRP records:
docker exec otbr ot-ctl srp server host
docker exec otbr ot-ctl srp server service
```

`child table` Age column is the most useful health signal. <30 s for an
MED-class device means active. >120 s means trouble (out of range, stuck,
or power off). >240 s = the parent has dropped them.

### 9.2 Watching matter-server in real time

```bash
docker logs -f matter-server | grep -E "Node:|Error|Subscription|Discovered|Commission"
```

Key log lines:

- `<Node:N> Discovered on mDNS` — matter-server saw the device via mDNS.
- `<Node:N> Re-Subscription succeeded` — operational CASE session is up.
- `<Node:N> Subscription failed with CHIP Error 0x32: Timeout` — device
  is unreachable; address resolve timed out. §10.5.
- `Msg Retransmission … failure (max retries:4)` — device stopped acking
  on a CASE session. Usually precedes the above.

### 9.3 Re-pair after NVS wipe

If you wiped NVS (§5.4) on an already-commissioned vent, HA will show the
old entity but the device is no longer in your fabric. Clean recovery:

1. In HA: Settings → Devices → click the old device → "Delete device".
   This removes it from HA's registry. (matter-server's fabric still
   has the old node id; that's fine, it'll get cleaned up next time
   matter-server prunes.)
2. The device has been in BLE fast-adv since boot (it wiped). If it's
   been >15 minutes since the wipe, power-cycle the device to restart
   the fast-adv window (handbook §6.2).
3. Commission as if it were a new device: §6.
4. Re-assign to its room: §7.

### 9.4 Restore OTBR dataset

If the OTBR container or its `otbr-data` volume gets destroyed, the
Thread network is gone — every commissioned vent is orphaned.

Recover from the backup at `~/.thread/dataset-backup.txt`:

```bash
DATASET=$(cat ~/.thread/dataset-backup.txt)
docker exec otbr ot-ctl dataset set active "$DATASET"
docker exec otbr ot-ctl ifconfig up
docker exec otbr ot-ctl thread start
docker exec otbr ot-ctl state          # expect: leader
```

All previously-commissioned vents will re-attach to the mesh because
the network key and PAN ID match the dataset they have in NVS.

### 9.5 Restart matter-server

If matter-server gets into a bad state (unrecoverable subscription
errors, BlueZ hung, etc.):

```bash
docker restart matter-server
docker logs -f matter-server | head -50
```

The fabric persists across restarts (in the mounted `~/matter-server/`
volume); commissioned devices will reappear and HA will reconnect.

### 9.6 Restart Home Assistant

```bash
docker restart homeassistant
# Then reload the HA web UI.
```

The Matter integration in HA will reconnect to matter-server's
WebSocket on its own. No state lost.

---

## 10. Troubleshooting matrix

Symptom-driven. For each row: what you see, what's wrong, how to
verify, how to fix. Cross-links to handbook are where to read up on
"why".

### 10.1 Boot loop with `rst:0x3 LP_SW_HPSYS`, "Segment 0 ... doesn't match data"

**Symptom**: device emits the bootloader banner, fails immediately
with `E (75) esp_image: Segment 0 load address 0x42198020, doesn't
match data 0x00010020`, then `rst:0x3 (LP_SW_HPSYS)`, repeats every
~100 ms.

**Cause**: bootloader on flash is a different ESP-IDF version than
the app. Almost always: you ran `espflash flash` without
`--bootloader`, so it overwrote our v5.2.3 bootloader with its
bundled v5.5.1 stub.

**Verify**: in the serial banner, the bootloader version printed
right after `2nd stage bootloader` doesn't match the version your
app was built for.

**Fix**: re-flash with the matching bootloader, per §5.3:

```bash
espflash flash \
  --partition-table partitions.csv \
  --bootloader target/riscv32imac-esp-espidf/release/build/esp-idf-sys-*/out/build/bootloader/bootloader.bin \
  --port /dev/ttyACM0 \
  target/riscv32imac-esp-espidf/release/vent-controller
```

(BOOT-hold + replug first.)

> Handbook §10.6.

### 10.2 Boot loop with `rst:0x7 TG0_WDT_HPSYS` after 30-200 s

**Symptom**: device boots, joins Thread, runs for some time, then
panics with `Core 0 panic'ed (Interrupt wdt timeout on CPU0)` and
`rst:0x7 (TG0_WDT_HPSYS)`. Repeats every 30–200 s. `task_wdt` may
also fire showing `ot_task` or `wifi` as the currently running task.

**Cause**: Wi-Fi driver is still in the build. ESP32-C6's Wi-Fi/802.15.4
radio co-existence holds interrupts >300 ms during init/calibration;
during a Thread re-attach burst the interrupt WDT (default 300 ms)
fires.

**Verify**: check `sdkconfig.defaults` has `CONFIG_ESP_WIFI_ENABLED=n`
(not just the CHIP station disable). Look in the boot log for
`wifi:` lines — if you see WiFi driver init, Wi-Fi is still in.

**Fix**: in `sdkconfig.defaults`, ensure:

```
CONFIG_ESP_WIFI_ENABLED=n
CONFIG_CHIP_DEVICE_CONFIG_ENABLE_WIFI_STATION=n
CONFIG_ESP_INT_WDT_TIMEOUT_MS=1000
```

Rebuild with CMake re-config (§4.1), reflash (§5.3).

> Handbook §10.1.

### 10.3 espflash hangs at "Connecting..." then fails

**Symptom**:

```
[INFO ] Serial port: '/dev/ttyACM0'
[INFO ] Connecting...
[ERROR] Failed to connect to ESP32 device
```

**Cause**: device isn't in download mode. Our running firmware
doesn't honor espflash's RTS/DTR soft-reset signals reliably.

**Fix**: manual BOOT-hold + replug + release BOOT (§5.2). Then
rerun the espflash command.

> Handbook §10.7.

### 10.4 BLE commissioning fails / times out

**Symptom**: HA shows "Commissioning failed" or matter-server logs
`le-connection-abort-by-local`, `Failed to connect over BLE`, or
silent timeouts.

**Likely causes** (in order of probability):

- **BLE fast-adv window expired.** Device booted >15 min ago and
  is now in slow-adv (or off). Power-cycle the device (unplug+replug,
  no BOOT-hold). The next 15 min is a fresh fast-adv window.
- **BlueZ wedged.** Restart it:
  ```bash
  sudo systemctl restart bluetooth
  docker restart matter-server
  ```
  Then retry commissioning.
- **Pi BT chip overheated / stuck.** `dmesg | tail` for any
  `hci0` errors. Reboot the Pi as a last resort.
- **Stale pairing.** Use `bluetoothctl` to remove cached entries:
  ```bash
  bluetoothctl
  > paired-devices
  > remove <BD_ADDR>
  ```

**Verify the device is actually advertising**:

```bash
sudo bluetoothctl scan on
# Expect to see a device with name "MATTER-1234" (or similar) appearing
# in the scan output.
```

> Handbook §6.1, §6.2.

### 10.5 Device commissions but is unreachable in HA

**Symptom**: HA shows the device as Unavailable. matter-server logs
`Subscription failed with CHIP Error 0x32: Timeout`,
`AddressResolve_DefaultImpl.cpp:124: Timeout`, or
`Msg Retransmission ... failure`.

**Run the four-check ladder** (handbook §5.9 / §6.3):

```bash
# 1. On Thread?
docker exec otbr ot-ctl child table | grep -i "$(get device EUI here)"

# 2. SRP registered?
docker exec otbr ot-ctl srp server host

# 3. mDNS visible?
avahi-browse -art -t _matter._tcp

# 4. matter-server logs:
docker logs --tail 50 matter-server | grep "Node:"
```

Possible outcomes:

| Checks 1-2-3-4 | Diagnosis | Fix |
|----------------|-----------|-----|
| ✗-?-?-? | Device not on Thread (powered off, out of range, wrong dataset) | Check power, check distance to OTBR, re-commission |
| ✓-✗-?-✗ | SRP didn't register | Power-cycle device. Wait 1 min. Recheck. If still empty, NVS-wipe + re-commission |
| ✓-✓-✗-✗ | OTBR's mDNS proxy / Avahi broken | `sudo systemctl restart avahi-daemon` |
| ✓-✓-✓-✗ | matter-server's session is stuck | `docker restart matter-server` |
| ✓-✓-✓-✓ but HA unhappy | HA Matter integration confused | Restart HA |

> Handbook §5.6 / §5.8.

### 10.6 HA shows device Unavailable after every Pi reboot

**Symptom**: each time you reboot the Pi, the vent entity stays
Unavailable for several minutes before recovering.

**Cause**: normal — Phase F (SRP re-register) takes 30–90 s after
boot. Sometimes 2–5 min on first MLE re-attach.

**Fix**: wait. If it's stuck >5 min, run §10.5's check ladder.

> Handbook §8.

### 10.7 Close/Open button does nothing in HA, no error

**Symptom**: HA accepts the click (no error in UI), but the vent
doesn't move and nothing changes in HA's state.

**Verify on the device**:

```bash
cat /dev/ttyACM0 | grep -i "DownOrClose\|UpOrOpen\|WindowCovering\|Matter:"
```

If you **don't see "DownOrClose command received"** after clicking
HA's Close, the command isn't reaching the cluster server. Either
mDNS/CASE is broken (§10.5) or the WindowCovering cluster is
mis-configured. Check `sdkconfig.defaults` and `matter_bridge.cpp`:

- Cluster server must have a delegate registered **after**
  `esp_matter::start()`.
- Cluster must include the `PositionAwareLift` feature.

If both of those are in place but you still see no command reaching
the device, the path is broken upstream (§10.5).

If you **do** see "DownOrClose command received" but the vent doesn't
move, check the servo wiring and that the state machine reached
target: `grep "Vent reached target"`. Then check the servo itself —
power, signal wire, GPIO2.

> Handbook §4.4.

### 10.8 Vent moves to wrong position (e.g. close goes to 176° not 90°)

**Symptom**: HA says "closed" but the louver is almost wide open
(or some other wrong angle).

**Cause**: regression in the `percent100ths` <-> angle conversion in
`src/matter.rs`. Specifically, integer overflow in u16 when
multiplying ~10000 × ~100.

**Verify**: in `src/matter.rs`, both functions must promote to u32:

```rust
let range = (ANGLE_OPEN - ANGLE_CLOSED) as u32;
let from_open = (ANGLE_OPEN - clamped) as u32;
((from_open * 10000) / range) as u16
```

If you see u16 arithmetic in either direction, it's the bug.

**Fix**: apply the u32 promotion (current code has it; this is
a regression-prevention check).

> Handbook §4.5.

### 10.9 OTBR won't form Thread network

**Symptom**: `ot-ctl state` returns `disabled` or an empty
response. `ot-ctl ifconfig` returns `down`.

**Likely causes**:

- **Kernel modules missing.** Run §2.1 again. Re-check `lsmod`.
- **Dongle on wrong device path.** Check `RADIO_URL` env var in the
  container vs. `ls /dev/ttyUSB0`.
- **Dataset never committed.** `ot-ctl dataset` returns blank.
  Either form a new dataset:
  ```bash
  docker exec otbr ot-ctl dataset init new
  docker exec otbr ot-ctl dataset commit active
  docker exec otbr ot-ctl ifconfig up
  docker exec otbr ot-ctl thread start
  ```
  Or restore from backup (§9.4).
- **Dongle physically dead / unplugged.** `lsusb -d 10c4:ea60`
  must show it.

### 10.10 `lsusb -d 303a:` returns nothing

**Symptom**: XIAO plugged in, power LED on, but `lsusb` doesn't
see it and `/dev/ttyACM0` doesn't appear.

**Cause**: plugged through a USB hub that doesn't pass data.
Specifically the VIA Labs 2109:3431 + TI 0451:8442 chain we've
identified.

**Fix**: unplug the XIAO from the hub. Plug it directly into a Pi
USB port. Re-check:

```bash
lsusb -d 303a:           # should now show the XIAO
ls /dev/ttyACM0          # should now exist
```

> Handbook §3.4 / §4.1.

### 10.11 Build OOMs / takes forever

**Symptom**: `cargo build` is killed by OOM-killer (look in
`dmesg`), or hangs spending 30+ minutes in one source file.

**Causes**:

- **Not enough swap.** Add 4 GB (§2.4).
- **First-time build of esp-idf-sys.** Expect 15–25 min on a Pi 4
  the first time. Subsequent builds are much faster.
- **Parallel jobs exhausting RAM.** Add `-j2` (or `-j1`) to the
  cargo invocation if your Pi is small.

### 10.12 Matter integration won't add in HA

**Symptom**: HA UI's "Add Integration → Matter" fails with
"Failed to connect" or stays in a loading state.

**Verify**: matter-server is up:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5580
docker logs --tail 30 matter-server | grep -E "Server.*initialized|Listening"
```

If matter-server is up but HA can't reach it, double-check the URL
you entered: `ws://localhost:5580/ws` (note the `/ws`).

If matter-server isn't up: `docker restart matter-server` and
re-check logs.

---

## 11. Appendix — command cheatsheet

### OTBR / Thread

```bash
docker exec otbr ot-ctl state                       # leader/router/child/disabled
docker exec otbr ot-ctl leaderdata                  # who's leader, network info
docker exec otbr ot-ctl child table                 # connected end devices
docker exec otbr ot-ctl router table                # connected routers
docker exec otbr ot-ctl ipaddr                      # OTBR's IPv6 addresses
docker exec otbr ot-ctl srp server host             # SRP-registered host names
docker exec otbr ot-ctl srp server service          # SRP-registered services
docker exec otbr ot-ctl dataset active              # active operational dataset
docker exec otbr ot-ctl dataset active -x           # same, as hex
docker exec otbr ping <ipv6>                        # ping a device on the mesh
```

### mDNS / Avahi

```bash
avahi-browse -art _matter._tcp                      # commissioned devices
avahi-browse -art _matterc._udp                     # devices in commissioning mode
avahi-browse -arvt                                  # all services, verbose
```

### espflash

```bash
espflash flash --partition-table partitions.csv \
               --bootloader <bootloader.bin> \
               --port /dev/ttyACM0 \
               <app-elf>                           # flash app + bootloader + partition table
espflash erase-partition --port /dev/ttyACM0 nvs   # wipe NVS only
espflash board-info --port /dev/ttyACM0            # chip info
espflash monitor --port /dev/ttyACM0               # serial monitor (Ctrl+] to exit)
```

### matter-server (via wscat)

```bash
wscat -c ws://localhost:5580/ws
# Then send JSON like:
# {"message_id":"1","command":"get_nodes","args":{}}
# {"message_id":"1","command":"ping_node","args":{"node_id":14}}
# {"message_id":"1","command":"device_command","args":{"node_id":14,"endpoint_id":1,"cluster_id":258,"command_name":"DownOrClose","payload":{}}}
```

### Docker housekeeping

```bash
docker ps                                           # what's running
docker logs -f --tail 50 <container>                # follow logs
docker restart <container>                          # restart
docker exec -it <container> sh                      # shell inside
```

### Bluetooth

```bash
sudo systemctl restart bluetooth                    # restart BlueZ
sudo bluetoothctl
> scan on                                           # see advertisements
> devices                                           # cached devices
> remove <BD_ADDR>                                  # forget a paired device
```

---

End of runbook. For "why does this work," go to **[handbook.md](handbook.md)**.
