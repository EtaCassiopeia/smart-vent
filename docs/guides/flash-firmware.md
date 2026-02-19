# Flashing Firmware to ESP32-C6

## Prerequisites

- ESP32-C6 development board
- USB-C cable
- Rust ESP toolchain installed (see `setup-dev-env.md`)

## 1. Connect the Board

Connect ESP32-C6 to your computer via USB-C. The board should appear as a serial device:

```bash
# macOS
ls /dev/cu.usbserial-*

# Linux
ls /dev/ttyUSB* /dev/ttyACM*
```

## 2. Build the Firmware

```bash
cd firmware/vent-controller
cargo build --release
```

## 3. Flash

```bash
cargo run --release
```

This uses `espflash` (configured in `.cargo/config.toml`) to flash and open a serial monitor.

Alternatively, flash without monitoring:

```bash
espflash flash target/riscv32imac-esp-espidf/release/vent-controller
```

## 4. Monitor Serial Output

```bash
espflash monitor
```

Expected output on first boot:

```
INFO vent_controller: Vent Controller v0.1.0
INFO vent_controller: Wakeup cause: fresh_boot
INFO vent_controller::identity: Device EUI-64: aa:bb:cc:dd:ee:ff:00:01
INFO vent_controller: First boot detected — initializing defaults
INFO vent_controller: Restoring vent angle: 90°
INFO vent_controller::thread: Initializing OpenThread stack...
INFO vent_controller::thread: OpenThread started on channel 15, PAN ID 0x1234
INFO vent_controller::coap: Registering CoAP resources...
INFO vent_controller::coap: CoAP server started on port 5683
INFO vent_controller: Vent controller running. Waiting for CoAP commands...
```

## 5. Verify CoAP

From the hub (or any machine on the Thread network):

```bash
# Using aiocoap-client
aiocoap-client coap://[<device-ipv6>]/device/identity
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `espflash` can't find device | Check USB cable, try a different port |
| Build fails with linker errors | Run `source ~/export-esp.sh` |
| Thread won't connect | Verify OTBR is running and network credentials match |
| Servo doesn't move | Check wiring (see `hardware/wiring.md`) |
