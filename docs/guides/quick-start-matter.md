# Quick Start: Matter over Thread

End-to-end guide for setting up the smart vent system with Matter over Thread. Covers hub setup, firmware flashing, commissioning via Google Home, adding Home Assistant as a second admin, and Thread network resilience.

> **Migrating from CoAP-only?** See [migration.md](migration.md) for what changes and how to preserve existing config.

## Why Matter over Thread?

With the legacy CoAP-only firmware, Thread credentials were hardcoded in the firmware. If the OTBR was recreated (`dataset init new`), the Extended PAN ID changed and devices refused to rejoin — requiring a reflash.

With Matter, the **Matter SDK manages Thread credentials**. During BLE commissioning, the controller (Google Nest, HA, etc.) pushes the current Thread dataset to the device automatically. If the network changes, you re-commission — no reflash needed.

| Scenario | CoAP-only (v0.1.x) | Matter (v0.2.0+) |
|----------|---------------------|-------------------|
| OTBR recreated | Reflash required | Re-commission via BLE |
| Thread credentials changed | Reflash required | Re-commission via BLE |
| Device power cycled | Auto-rejoin (if creds match) | Auto-rejoin (Matter stores creds) |
| Want to change ecosystems | N/A | Factory reset + re-commission |
| Firmware update | Must re-match creds | Thread creds preserved in NVS |

---

## Prerequisites

**Hardware:**
- Raspberry Pi 4B with Raspberry Pi OS (64-bit)
- Thread RCP dongle: Nordic nRF52840 or SMLIGHT SLZB-07 (with OT RCP firmware)
- XIAO ESP32-C6 + SG90 servo ([wiring](../hardware/wiring.md))
- Google Nest Hub, Nest Mini, or other Thread-capable Google device

**Software (development machine):**
- Rust ESP toolchain (`espup install`)
- `espflash` (`cargo install espflash`)
- Python 3.10+ (for QR code generation and hub CLI)

---

## Phase 1: Hub Setup (Raspberry Pi)

### 1.1 Kernel Modules

OTBR requires `ip6tables` for firewall and Thread routing:

```bash
sudo modprobe ip6table_filter
sudo modprobe ip6_tables

# Persist across reboots
echo "ip6table_filter" | sudo tee -a /etc/modules
echo "ip6_tables" | sudo tee -a /etc/modules
```

### 1.2 OTBR (OpenThread Border Router)

Plug in your RCP dongle and run the setup script:

```bash
cd ~/vent/tools/scripts
./setup_otbr.sh
```

The script auto-detects your dongle type (nRF52840 at `/dev/ttyACM0` or SLZB-07 at `/dev/ttyUSB0`) and starts the OTBR Docker container.

If using WiFi instead of Ethernet:
```bash
BACKBONE_INTERFACE=wlan0 ./setup_otbr.sh
```

Verify OTBR is running:
```bash
docker exec otbr ot-ctl state          # Should show "leader" after ~10s
docker exec otbr ot-ctl dataset active  # Note the dataset (for reference only)
```

Check Thread routing is working:
```bash
ip -6 route show | grep wpan0   # Should show mesh-local routes
```

> **With Matter, you do NOT need to manually configure Thread credentials on the OTBR or match them in the firmware.** The OTBR forms its own network automatically. During Matter commissioning, the controller (Google Home, HA) reads the Thread dataset from the OTBR and pushes it to the device via BLE.

#### If `ot-ctl state` returns `disabled`

The OTBR container is running but the Thread radio stack has not started. This
typically means either the Thread network interface is down or no dataset has
been committed yet.

**Step 1 — Bring up the interface and start Thread:**

```bash
docker exec otbr ot-ctl ifconfig up
docker exec otbr ot-ctl thread start
```

Wait a few seconds, then check again:

```bash
docker exec otbr ot-ctl state   # Should now show "leader"
```

If the state transitions to `leader` (or `router`/`child`), you're good — continue to the next section.

**Step 2 — If it's still `disabled`, check the radio connection:**

The OTBR cannot talk to the RCP dongle. Verify:

```bash
# Is the dongle plugged in?
ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null

# Check OTBR container logs for radio errors
docker logs otbr 2>&1 | tail -20
```

Common causes:
- **Dongle not plugged in or not detected** — reconnect USB, check `lsusb` output
- **Wrong serial device** — the OTBR was started with a `RADIO_URL` pointing to a device that doesn't exist. Recreate the container with the correct path (see `setup_otbr.sh`)
- **Dongle not flashed with RCP firmware** — the SLZB-07 ships with Zigbee firmware by default. See [setup-rpi.md](setup-rpi.md#3-flash-dongle-with-rcp-firmware) for flashing instructions
- **Kernel modules missing** — if `ip6table_filter` isn't loaded, the OTBR firewall fails silently and the radio stack never starts. Run `sudo modprobe ip6table_filter` and restart: `docker restart otbr`

**Step 3 — If the radio is fine but there's no dataset:**

```bash
# Check if a dataset exists
docker exec otbr ot-ctl dataset active
```

If this returns empty or an error, the OTBR has no network to start. Form one:

```bash
docker exec otbr ot-ctl dataset init new
docker exec otbr ot-ctl dataset commit active
docker exec otbr ot-ctl ifconfig up
docker exec otbr ot-ctl thread start
```

This generates a random Thread network. With Matter commissioning, the exact
credentials don't matter — they're pushed to devices automatically during BLE
commissioning.

### 1.3 Matter Server

The HA Matter integration requires a **separate Matter Server** container
(`python-matter-server`). This is NOT bundled with HA Container installs —
only HA OS/Supervised includes it as a built-in add-on.

The `setup_ha.sh` script starts both containers automatically:

```bash
./setup_ha.sh
```

If you already have HA running and just need the Matter Server:

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
    --storage-path /data --paa-root-cert-dir /data/credentials
```

Verify it's running:
```bash
docker logs matter-server 2>&1 | tail -5   # Should show "Started"
```

Key flags:
- `--network host` — required so HA (also on host network) can reach it on `localhost:5580`
- `-v /run/dbus:/run/dbus:ro` — required for BLE commissioning (BlueZ access)
- `--security-opt apparmor=unconfined` — required on systems with AppArmor (default on Raspberry Pi OS)

### 1.4 Home Assistant

If HA isn't running yet:
```bash
./setup_ha.sh   # Starts both Matter server and HA
```

Then open `http://<pi-ip>:8123` and:

1. Create your admin account
2. Go to **Settings** -> **Devices & Services** -> **Add Integration**
3. Search for **Matter (BETA)** and add it
4. When prompted for the WebSocket URL, use: `ws://localhost:5580/ws`
5. The integration connects to the Matter Server and is ready for commissioning

> **Tip:** If you also want the extended telemetry (RSSI, heap, room/floor) from the CoAP custom component, you can install both. See the [HA user guide](home-assistant.md) for the custom component setup.

---

## Phase 2: Flash the Controller

On your development machine, connect the XIAO ESP32-C6 via USB-C.

### Build

```bash
cd firmware/vent-controller
cargo build --release
```

The first build downloads ESP-IDF v5.2.3 and the `esp_matter` component (compiles
the CHIP SDK). This takes several minutes. The release binary is approximately
**2.04 MB**.

### Flash

The Matter firmware requires a custom partition table (3 MB app partition) and the
project-built bootloader:

```bash
espflash flash \
    --port /dev/cu.usbmodem101 \
    --bootloader target/riscv32imac-esp-espidf/release/build/esp-idf-sys-*/out/build/bootloader/bootloader.bin \
    --partition-table partitions.csv \
    target/riscv32imac-esp-espidf/release/vent-controller
```

Expected: `App/part. size: 2,116,432/3,145,728 bytes, 67.28%`

> **Why `--bootloader`?** `espflash` bundles a v5.5.x bootloader. Our firmware uses
> ESP-IDF v5.2.3. Mismatched bootloader/app versions cause a "Segment 0 load address
> doesn't match" error. See [flash-firmware.md](flash-firmware.md) for details.

### Serial output

On boot, the serial output displays the Matter pairing info:

```
Vent Controller v0.1.0
EUI-64: 58:e6:c5:ff:fe:01:0a:dc
Initializing Matter...
matter_bridge: Window Covering endpoint ID: 1
matter_bridge: Discriminator derived from EUI-64: 173
matter_bridge: Matter node initialized (VID=0xFFF1, PID=0x8001, disc=173)
...
Manual pairing code: 34970112332
QR code payload: MT:Y3.13OTB00KA0648G00
```

**Save the pairing code and QR payload** — you need one of them for commissioning.

Optionally, generate a printable QR code:
```bash
cd tools/qr-generator
pip install qrcode[pil]
python generate_qr.py "MT:Y3.13OTB00KA0648G00" --output vent-qr.png
```

At this point the device is **not on the Thread network** — it is advertising via BLE, waiting for a Matter commissioner.

---

## Phase 3: Commission via Google Home

1. Open the **Google Home** app on your phone
2. Tap **+** -> **Set up device** -> **New device**
3. Choose your home
4. The app scans for nearby Matter devices via BLE
5. When the vent appears, tap it
6. **Scan the QR code** or enter the manual pairing code
7. Wait ~30 seconds for commissioning to complete
8. Assign the device to a room (e.g., "Bedroom") and name it (e.g., "Bedroom Vent")

The vent now appears as a "Window covering" in Google Home. Thread credentials were provisioned automatically — no hardcoding needed.

**Verify on serial monitor:**
```
OPENTHREAD:[N] Mle-----------: Role detached -> child
Matter: commissioned into fabric
```

**Voice commands:**

| Command | Action |
|---------|--------|
| "Hey Google, open the bedroom vent" | Fully open (180 deg) |
| "Hey Google, close the bedroom vent" | Fully close (90 deg) |
| "Hey Google, set the bedroom vent to 50%" | Half open (135 deg) |
| "Hey Google, what's the bedroom vent position?" | Report current position |

---

## Phase 4: Add Home Assistant (Multi-Admin)

A single vent can be controlled by up to 5 ecosystems simultaneously. To add HA as a second controller:

1. In the **Google Home** app, go to the vent's device settings
2. Tap **Linked Matter apps & services** -> **Link new app**
   - This opens a commissioning window (~2 minutes)
3. In **Home Assistant**: go to **Settings** -> **Devices & Services** -> **Matter**
4. Click **Commission Device**
5. Enter the manual pairing code or scan the QR code
6. Wait for commissioning to complete

The vent now appears in HA as a **Cover** entity (`cover.smart_hvac_vent`):

| Action | HA Service | Effect |
|--------|-----------|--------|
| Open | `cover.open_cover` | Fully open (180 deg) |
| Close | `cover.close_cover` | Fully close (90 deg) |
| Set position | `cover.set_cover_position` | 0% = closed, 100% = open |

> **Note:** HA's cover convention (0%=closed, 100%=open) is the inverse of Matter's percent100ths (0%=open, 100%=closed). HA handles the conversion automatically.

### Dashboard card

```yaml
type: tile
entity: cover.smart_hvac_vent
name: Bedroom Vent
features:
  - type: cover-position
```

### Automation example

```yaml
automation:
  - alias: "Close vents at night"
    trigger:
      - platform: time
        at: "22:00:00"
    action:
      - service: cover.close_cover
        target:
          entity_id: cover.smart_hvac_vent
```

See the [HA Matter integration guide](home-assistant-matter.md) for more dashboard and automation options.

---

## Phase 5: Identify Your Devices

If you have multiple vents, use the **identify** feature to match physical devices to their digital representation:

- **Google Home**: device settings -> find an identify option
- **Home Assistant**: click the identify icon on the device page
- **chip-tool**: `chip-tool identify identify 1 1 10`

The servo **wiggles back and forth** for ~10 seconds so you can see which physical vent you're looking at.

---

## Thread Network Resilience

Matter eliminates the biggest pain point of the CoAP-only setup: Thread network changes no longer require reflashing.

### How it works

1. **Matter stores Thread credentials in NVS** — they survive reboots and firmware updates
2. **Thread credentials are provisioned during BLE commissioning** — not hardcoded in firmware
3. **If the Thread network changes** (OTBR recreated, new dataset), the device loses connectivity but does NOT need reflashing

### Recovery: Thread network changed

If the OTBR is recreated with a new dataset:

1. The device falls off the Thread network (serial shows `Role child -> detached`)
2. **Factory reset** the device:
   - Hold the boot button for 10 seconds, OR
   - Reflash the firmware (this also clears Matter state)
3. The device starts BLE advertising again
4. Re-commission from Google Home and/or HA — new Thread credentials are pushed automatically
5. Room/floor/name assignments are preserved (stored in NVS, not cleared by factory reset)

### Recovery: Device not responding

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Serial shows `detached` | Thread network changed or OTBR down | Check OTBR state. If network changed, factory reset + re-commission |
| No serial output | Device not powered or USB disconnected | Check power and USB cable |
| Commissioned but no control | Thread routing issue | Verify `ip -6 route show \| grep wpan0` on Pi |
| Position always 0% | Firmware not reporting correctly | Check serial log for position updates |

### Data preserved across operations

| Data | Reboot | Re-commission | Factory reset | Reflash |
|------|--------|--------------|---------------|---------|
| EUI-64 (eFuse) | Yes | Yes | Yes | Yes |
| NVS config (room/floor/name) | Yes | Yes | Yes | Yes |
| Last vent angle (WAL) | Yes | Yes | Yes | Yes |
| Thread credentials | Yes | Updated | Cleared | Cleared |
| Matter fabric info | Yes | Updated | Cleared | Cleared |

---

## Adding More Devices

For each additional vent controller:

1. Flash firmware (see [Phase 2](#phase-2-flash-the-controller))
2. Note the pairing code from serial output
3. Commission via Google Home (Phase 3)
4. Optionally add to HA as second admin (Phase 4)

For batch setup, flash all devices first, then commission them one at a time — each has a unique pairing code.

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| HA Matter: "cannot connect to `ws://localhost:5580/ws`" | The Matter Server container is not running. Start it: `docker start matter-server` or see [Phase 1.3](#13-matter-server). |
| OTBR `ip6tables` error | `sudo modprobe ip6table_filter && docker restart otbr` |
| OTBR shows `disabled` not `leader` | Run `docker exec otbr ot-ctl ifconfig up && docker exec otbr ot-ctl thread start` |
| No `wpan0` routes on Pi | Check kernel modules and backbone interface. See [commissioning.md](commissioning.md#prerequisites) |
| BLE device not found during scan | Ensure firmware is v0.2.0+ (serial shows "QR code payload"). Move phone closer. |
| Google Home "setup failed" | Power-cycle the vent and retry. Ensure your Nest device supports Thread. |
| HA "commission failed" | Ensure HA can reach the Thread network. Check OTBR is running. Verify BLE on HA host. |
| CoAP still works? | Yes — CoAP runs on port 5683 over the same Thread interface. Both protocols share state. |
| `espflash` "image too big" | Pass `--partition-table partitions.csv` to use the 3 MB app partition. |
| `Segment 0 load address doesn't match` | Pass `--bootloader` with the project-built bootloader (see [Phase 2](#phase-2-flash-the-controller)). |
| `controller_sleep_init` assert crash | Ensure `CONFIG_PM_ENABLE` is disabled in `sdkconfig.defaults`. |
| Servo doesn't move | Check wiring — signal goes to D2/GPIO2. See [hardware/wiring.md](../hardware/wiring.md). |

---

## Next Steps

- [Multi-admin setup](multi-admin.md) — add Alexa or Apple Home as additional controllers
- [HA Matter guide](home-assistant-matter.md) — dashboard cards and automations
- [HA user guide](home-assistant.md) — CoAP custom component for extended telemetry
- [Architecture](../architecture.md) — full system reference
