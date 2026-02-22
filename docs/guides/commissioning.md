# Commissioning New Vent Devices

## Overview

Commissioning adds a new ESP32-C6 vent controller to the Thread network and
registers it with the hub. Both the OTBR and the device must share the same
Thread network credentials (network key, channel, PAN ID, network name).

## Prerequisites

Before commissioning, ensure the OTBR is running correctly on the Raspberry Pi.

### Kernel modules

The OTBR firewall requires `ip6table_filter`. Without it, the OTBR startup
script fails and the `wpan0` interface is never created — meaning the host
(and Home Assistant) cannot reach Thread devices via IPv6.

```bash
# Load modules (required after every reboot unless persisted)
sudo modprobe ip6table_filter
sudo modprobe ip6_tables

# Persist across reboots
grep -q ip6table_filter /etc/modules 2>/dev/null || echo "ip6table_filter" | sudo tee -a /etc/modules
grep -q ip6_tables /etc/modules 2>/dev/null || echo "ip6_tables" | sudo tee -a /etc/modules
```

### Backbone interface

The OTBR's `BACKBONE_INTERFACE` must match the Pi's active network interface.
If the Pi uses WiFi, this must be `wlan0` (not the default `eth0`). Check
which interface has connectivity:

```bash
ip -br link show | grep UP
```

If the OTBR was started with the wrong backbone interface, recreate it:

```bash
docker stop otbr && docker rm otbr
# Then re-run setup_otbr.sh or docker run with -e BACKBONE_INTERFACE=wlan0
```

### Verify OTBR networking

After the OTBR starts, confirm the `wpan0` interface exists and the mesh-local
prefix is routable from the host:

```bash
ip -6 route show | grep wpan0
```

You should see routes for the mesh-local prefix (e.g., `fdxx:xxxx:xxxx:xxxx::/64 dev wpan0`).
If no `wpan0` routes appear, check the kernel modules and backbone interface above.

## 1. Configure OTBR with Known Credentials

The firmware ships with default development credentials. Configure the OTBR
to use the same credentials so devices can join automatically.

### Option A: Match OTBR to firmware defaults (recommended for development)

Run these commands on the Raspberry Pi to set the OTBR's dataset to match
the firmware's default `ThreadConfig`:

```bash
docker exec otbr ot-ctl dataset init new
docker exec otbr ot-ctl dataset networkkey 00112233445566778899aabbccddeeff
docker exec otbr ot-ctl dataset channel 15
docker exec otbr ot-ctl dataset panid 0x1234
docker exec otbr ot-ctl dataset networkname OpenThreadDemo
docker exec otbr ot-ctl dataset commit active
docker exec otbr ot-ctl ifconfig up
docker exec otbr ot-ctl thread start
```

`dataset init new` generates required fields like the Active Timestamp and
Extended PAN ID. The subsequent commands override only the fields that must
match the firmware. The Extended PAN ID is randomly generated and does not
need to match — the firmware does not constrain it.

Verify the dataset is active:

```bash
docker exec otbr ot-ctl dataset active
docker exec otbr ot-ctl state
```

The state should show `leader` after a few seconds.

**Important:** Note the full `dataset active` output. If you ever need to
recreate the OTBR container, you must reproduce the exact same dataset
(including the Extended PAN ID) or reflash the devices. Devices store the
full dataset and will not rejoin a network with a different Extended PAN ID.

### Option B: Match firmware to OTBR (for existing networks)

If you already have a Thread network running on the OTBR, get its credentials
and update the firmware to match:

```bash
# Get the active dataset from OTBR
docker exec otbr ot-ctl dataset active
```

This outputs fields like:

```
Network Key: aabbccdd...
Channel: 25
PAN ID: 0xabcd
Network Name: MyNetwork
```

Update `firmware/vent-controller/src/thread.rs` in `ThreadConfig::default()`:

```rust
Self {
    network_name: "MyNetwork".into(),
    channel: 25,
    panid: 0xabcd,
    network_key: [
        0xaa, 0xbb, 0xcc, 0xdd, ...  // your 16-byte key
    ],
}
```

Then rebuild and flash:

```bash
cargo espflash flash --release --port /dev/cu.usbmodem101 --monitor
```

## 2. Flash the Firmware

See `flash-firmware.md` for detailed instructions.

```bash
cd firmware/vent-controller
cargo espflash flash --release --port /dev/cu.usbmodem101 --monitor
```

## 3. Verify Device Joined the Network

The device should join the OTBR's network automatically on boot. Watch the
serial monitor for the full boot sequence:

```
Vent Controller v0.1.0
Wakeup cause: fresh_boot
Initializing OpenThread stack...
OpenThread started on channel 15, PAN ID 0x1234, network 'OpenThreadDemo'
CoAP server started on port 5683
OpenThread mainloop started
Vent controller running. Waiting for CoAP commands...
```

A successful network join shows the role transition within a few seconds:

```
OPENTHREAD:[N] Mle-----------: Role detached -> child
```

Check the OTBR side to confirm the device appeared:

```bash
# List child devices (MTDs like our vent controller)
docker exec otbr ot-ctl child table

# List neighbor devices
docker exec otbr ot-ctl neighbor table
```

If the device doesn't appear, verify:
- The network key matches exactly between OTBR and firmware
- The channel and PAN ID match
- The OTBR state is `leader` or `router`
- The serial output shows "OpenThread mainloop started" (if missing, the
  event loop isn't running)

## 4. Discover the Device

Run the following commands **on the Raspberry Pi hub** (not on the machine you
used to flash the firmware).

If you haven't installed the hub CLI yet, install it first:

```bash
cd vent/hub
pip install -e .
```

> See `setup-dev-env.md` for full Python environment setup.

Then discover new devices on the Thread network:

```bash
vent-hub discover
```

Expected output:

```
Discovered 1 new device(s):
  aa:bb:cc:dd:ee:ff:00:01 at fd00::1234:5678:abcd:ef01
```

## 5. Assign Room and Floor

```bash
vent-hub assign aa:bb:cc:dd:ee:ff:00:01 bedroom 2
```

This stores the assignment both on the device (NVS) and in the hub's registry.

## 6. Verify Operation

```bash
# Check device status
vent-hub get aa:bb:cc:dd:ee:ff:00:01

# Test vent control
vent-hub set aa:bb:cc:dd:ee:ff:00:01 180   # open
vent-hub set aa:bb:cc:dd:ee:ff:00:01 90    # close
```

## 7. Home Assistant

The HA integration reads discovered devices from the hub's SQLite database
(`devices.db`). For this to work, the database file must be mounted into the
Home Assistant container.

### First-time setup

Run `setup_ha.sh` which handles the container creation and DB mount:

```bash
tools/scripts/setup_ha.sh
```

This mounts `devices.db` at `/config/devices.db` inside the HA container.

If HA is already running without the DB mount, recreate the container:

```bash
docker stop homeassistant && docker rm homeassistant
docker run -d \
    --name homeassistant \
    --restart unless-stopped \
    --network host \
    -v ~/homeassistant:/config \
    -v /path/to/devices.db:/config/devices.db \
    -v /etc/localtime:/etc/localtime:ro \
    ghcr.io/home-assistant/home-assistant:stable
```

Replace `/path/to/devices.db` with the actual path (default: the directory
where you run `vent-hub`, typically the project root).

### Add the integration

1. Open Home Assistant at `http://<pi-ip>:8123`
2. Go to **Settings -> Devices & Services -> Add Integration**
3. Search for **Smart Vent Control**
4. Enter the hub connection details (defaults are usually correct):
   - Hub Host: `localhost`
   - Hub Port: `5683`
   - Poll Interval: `30` seconds
   - Hub Database Path: `/config/devices.db`

### Verify the device appears

After adding the integration, wait one poll cycle (30 seconds). The device
should appear as a **cover** entity (device class: damper) under the
Vent Control integration.

New devices discovered later via `vent-hub discover` are picked up
automatically on the next poll cycle — no HA restart needed.

1. Go to **Settings -> Devices & Services**
2. The Vent Control integration should show the new device
3. Assign it to an area matching the room

## Adding Multiple Devices

Flash and power on each device one at a time. Run `vent-hub discover` after
each one joins the network.

For batch commissioning, power on all devices and run a single discover:

```bash
# Wait 30 seconds for all devices to join
sleep 30
vent-hub discover
```

## Removing a Device

To remove a device from the system:

1. Power off the physical device
2. Remove from hub: `vent-hub delete <eui64>` (if implemented)
3. Remove from Home Assistant via the UI

## Troubleshooting

### OTBR firewall fails (`ip6tables` error)

```
ip6tables: can't initialize ip6tables table 'filter': Table does not exist
*** ERROR: Failed to start firewall service
```

The `ip6table_filter` kernel module is not loaded. See [Prerequisites](#kernel-modules).

### `ot-ctl` returns "Connection refused"

The OTBR management daemon isn't running, usually because the startup script
exited early due to the firewall failure above. Fix the kernel modules and
restart the OTBR container:

```bash
sudo modprobe ip6table_filter && sudo modprobe ip6_tables
docker restart otbr
```

### No `wpan0` routes on the host

If `ip -6 route show | grep wpan0` returns nothing, the OTBR is not bridging
Thread traffic. Check:

1. Kernel modules are loaded (see above)
2. Backbone interface matches the active network interface (`wlan0` for WiFi)
3. OTBR container is running and `ot-ctl state` returns `leader` or `router`

### Device doesn't rejoin after OTBR recreation

When the OTBR container is recreated, `dataset init new` generates a new
Extended PAN ID. Devices that joined the old network store the old Extended
PAN ID and will not recognize the new network.

Fix: reflash the device firmware so it re-joins using only the network key,
channel, PAN ID, and network name (which are not constrained to a specific
Extended PAN ID).

### Device visible in hub but not in Home Assistant

Check these in order:

1. **DB mounted?** — `docker exec homeassistant ls /config/devices.db` should show
   the file. If not, recreate the HA container with the `-v` mount.
2. **CoAP reachable?** — The HA container must be able to reach Thread devices
   via IPv6. Verify `wpan0` routes exist on the host (HA uses `--network host`).
3. **Check HA logs** — `docker exec homeassistant cat /config/home-assistant.log`
   for errors from the `vent_control` integration.

## Security Note

The default development credentials (`00112233...eeff`) are **not secure**.
For production deployments, generate unique credentials:

```bash
docker exec otbr ot-ctl dataset init new
docker exec otbr ot-ctl dataset commit active
docker exec otbr ot-ctl dataset active
```

Then update the firmware's `ThreadConfig` to match and rebuild.
