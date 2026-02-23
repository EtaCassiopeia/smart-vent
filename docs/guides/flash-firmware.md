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
App/part. size:    922,288/1,536,000 bytes, 60.04%
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
Vent Controller v0.1.0
Wakeup cause: fresh_boot
EUI-64: 58:e6:c5:ff:fe:01:0a:dc
First boot detected — initializing defaults
Restoring checkpoint: 90°
Power mode: always_on (default)
Initializing OpenThread stack...
OpenThread started on channel 15, PAN ID 0x1234, network 'OpenThreadDemo'
Registering CoAP resources...
CoAP server started on port 5683
OpenThread mainloop started
Vent controller running. Waiting for CoAP commands...
```

If the OTBR is running with matching credentials, you should also see the device
join the network within a few seconds:

```
OPENTHREAD:[N] Mle-----------: Role detached -> child
```

## 4. Matter Pairing Information

After boot, the serial output will display the Matter pairing information:

```
Manual pairing code: 34970112332
QR code payload: MT:Y3.13OTB00KA0648G00
```

Use the **manual pairing code** when commissioning via CLI tools (e.g. `chip-tool`), or generate a printable QR code:

```bash
cd tools/qr-generator
pip install qrcode[pil]
python generate_qr.py "MT:Y3.13OTB00KA0648G00" --output vent-qr.png
```

Scan the QR code with the Google Home, Alexa, or Apple Home app to commission the device.

## 5. Verify CoAP

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
