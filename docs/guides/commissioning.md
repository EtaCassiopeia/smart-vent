# Commissioning New Vent Devices

## Overview

Commissioning adds a new ESP32-C6 vent controller to the Thread network and registers it with the hub.

## 1. Flash the Firmware

See `flash-firmware.md` for detailed instructions.

## 2. Thread Network Join

The firmware automatically attempts to join the Thread network on boot using the credentials compiled into `sdkconfig.defaults`.

To join a different network, update the Thread dataset via the OTBR:

1. Get the active dataset from OTBR:
   ```bash
   curl http://<rpi-ip>:8081/v1/node/dataset/active -o dataset.json
   ```

2. The device will attempt to join and obtain an IPv6 address.

3. Verify the device joined:
   ```bash
   curl http://<rpi-ip>:8081/v1/node/neighbor-table
   ```

## 3. Discover the Device

Use the hub CLI to discover new devices:

```bash
vent-hub discover
```

Expected output:

```
Discovered 1 new device(s):
  aa:bb:cc:dd:ee:ff:00:01 at fd00::1234:5678:abcd:ef01
```

## 4. Assign Room and Floor

```bash
vent-hub assign aa:bb:cc:dd:ee:ff:00:01 bedroom 2
```

This stores the assignment both on the device (NVS) and in the hub's registry.

## 5. Verify Operation

```bash
# Check device status
vent-hub get aa:bb:cc:dd:ee:ff:00:01

# Test vent control
vent-hub set aa:bb:cc:dd:ee:ff:00:01 180   # open
vent-hub set aa:bb:cc:dd:ee:ff:00:01 90    # close
```

## 6. Home Assistant

After discovery, the device appears in Home Assistant:

1. Go to **Settings -> Devices & Services**
2. The Vent Control integration should show the new device
3. Assign it to an area matching the room

## Adding Multiple Devices

Flash and power on each device one at a time. Run `vent-hub discover` after each one joins the network.

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
