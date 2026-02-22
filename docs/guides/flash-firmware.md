# Flashing Firmware to XIAO ESP32C6

## Prerequisites

- Seeed Studio XIAO ESP32C6
- USB-C cable
- Rust ESP toolchain installed (see `setup-dev-env.md`)
- `espflash` installed (`cargo install espflash`)

## 1. Connect the Board

Connect the XIAO ESP32C6 to your computer via USB-C. The board should appear
as a serial device:

```bash
# macOS
ls /dev/cu.usbmodem*

# Linux
ls /dev/ttyACM* /dev/ttyUSB*
```

## 2. Build and Flash

Always use `--release` — the debug build exceeds the flash partition size.

```bash
cd firmware/vent-controller
cargo espflash flash --release --port /dev/cu.usbmodem101 --monitor
```

This builds the firmware, flashes it, and opens a serial monitor.

Expected output:

```
App/part. size:    822,208/1,536,000 bytes, 53.53%
Flashing has completed!
```

To flash without monitoring:

```bash
cargo espflash flash --release --port /dev/cu.usbmodem101
```

## 3. Monitor Serial Output

```bash
cargo espflash monitor --port /dev/cu.usbmodem101
```

Expected output on first boot:

```
INFO vent_controller: Vent Controller v0.1.0
INFO vent_controller: Wakeup cause: fresh_boot
INFO vent_controller::identity: Device EUI-64: aa:bb:cc:dd:ee:ff:00:01
INFO vent_controller: First boot detected — initializing defaults
INFO vent_controller: Restoring vent angle: 90°
INFO vent_controller::thread: Initializing OpenThread stack...
INFO vent_controller::coap: Registering CoAP resources...
INFO vent_controller::coap: CoAP server started on port 5683
INFO vent_controller: Vent controller running. Waiting for CoAP commands...
```

## 4. Verify CoAP

From the hub (or any machine on the Thread network):

```bash
# Using aiocoap-client
aiocoap-client coap://[<device-ipv6>]/device/identity
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Device not found (`/dev/cu.usbmodem*`) | Check USB-C cable (some are charge-only), try a different port |
| Image too big error | Make sure you're building with `--release` |
| Build fails with linker errors | Run `source ~/export-esp.sh` |
| Thread won't connect | Verify OTBR is running and network credentials match |
| Servo doesn't move | Check wiring — signal goes to D2/GPIO2 (see `hardware/wiring.md`) |
