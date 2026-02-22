# Commissioning New Vent Devices

## Overview

Commissioning adds a new ESP32-C6 vent controller to the Thread network and
registers it with the hub. Both the OTBR and the device must share the same
Thread network credentials (network key, channel, PAN ID, network name).

## 1. Configure OTBR with Known Credentials

The firmware ships with default development credentials. Configure the OTBR
to use the same credentials so devices can join automatically.

### Option A: Match OTBR to firmware defaults (recommended for development)

Run these commands on the Raspberry Pi to set the OTBR's dataset to match
the firmware's default `ThreadConfig`:

```bash
docker exec otbr ot-ctl dataset clear
docker exec otbr ot-ctl dataset networkkey 00112233445566778899aabbccddeeff
docker exec otbr ot-ctl dataset channel 25
docker exec otbr ot-ctl dataset panid 0xabcd
docker exec otbr ot-ctl dataset networkname VentNet
docker exec otbr ot-ctl dataset commit active
docker exec otbr ot-ctl ifconfig up
docker exec otbr ot-ctl thread start
```

Verify the dataset is active:

```bash
docker exec otbr ot-ctl dataset active
docker exec otbr ot-ctl state
```

The state should show `leader` after a few seconds.

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

The device should join the OTBR's network automatically on boot. Check the
serial monitor output for:

```
INFO vent_controller::thread: OpenThread started on channel 25, PAN ID 0xabcd, network 'VentNet'
```

Check the OTBR side to see if the device joined:

```bash
# List neighbor devices
docker exec otbr ot-ctl neighbor table

# List child devices (MTDs like our vent controller)
docker exec otbr ot-ctl child table
```

If the device doesn't appear, verify:
- The network key matches exactly between OTBR and firmware
- The channel and PAN ID match
- The OTBR state is `leader` or `router`

## 4. Discover the Device

Use the hub CLI to discover new devices on the Thread network:

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

After discovery, the device appears in Home Assistant:

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

## Security Note

The default development credentials (`00112233...eeff`) are **not secure**.
For production deployments, generate unique credentials:

```bash
docker exec otbr ot-ctl dataset init new
docker exec otbr ot-ctl dataset commit active
docker exec otbr ot-ctl dataset active
```

Then update the firmware's `ThreadConfig` to match and rebuild.
