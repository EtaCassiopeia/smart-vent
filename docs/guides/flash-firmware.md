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

## 2. Build

Always use `--release` — the debug build far exceeds the flash partition size.

```bash
cd firmware/vent-controller
cargo build --release
```

The first build downloads ESP-IDF v5.2.3 and the `esp_matter` component (~1.3.x),
which compiles the CHIP SDK. This takes several minutes. Subsequent builds are
incremental (~10 seconds).

The release binary is approximately **2.04 MB** (Matter + Thread + BLE).

## 3. Flash

The Matter-enabled firmware requires a **custom partition table** (`partitions.csv`)
with a 3 MB app partition — the default `single_app_large` layout (1.5 MB) is
too small. You also need the **project-built bootloader** to avoid a version
mismatch with the bundled `espflash` bootloader.

```bash
espflash flash \
    --port /dev/cu.usbmodem101 \
    --bootloader target/riscv32imac-esp-espidf/release/build/esp-idf-sys-*/out/build/bootloader/bootloader.bin \
    --partition-table partitions.csv \
    target/riscv32imac-esp-espidf/release/vent-controller
```

Expected output:

```
Chip type:         esp32c6 (revision v0.2)
Flash size:        4MB
App/part. size:    2,116,432/3,145,728 bytes, 67.28%
Flashing has completed!
```

> **Why `--bootloader`?** `espflash` bundles its own bootloader (currently built
> from ESP-IDF v5.5.x). Our firmware is built with ESP-IDF v5.2.3. Mixing
> bootloader and app from different ESP-IDF versions causes a
> "Segment 0 load address doesn't match" error at boot.

> **Why `--partition-table`?** The build uses `CONFIG_PARTITION_TABLE_SINGLE_APP_LARGE`
> to avoid path resolution issues with custom partition tables in the esp-idf-sys
> cmake build. The actual 3 MB partition layout is applied at flash time via the
> `partitions.csv` file in the project root.

## 4. Monitor Serial Output

Use system Python with pyserial (espflash's built-in monitor requires an
interactive terminal):

```bash
python3 -c "
import serial, sys
s = serial.Serial('/dev/cu.usbmodem101', 115200, timeout=1)
while True:
    line = s.readline()
    if line:
        sys.stdout.write(line.decode('utf-8', errors='replace'))
        sys.stdout.flush()
"
```

Press Ctrl+C to exit.

Expected output on first boot:

```
Vent Controller v0.1.0
Wakeup cause: fresh_boot
EUI-64: 58:e6:c5:ff:fe:01:0a:dc
First boot detected — initializing defaults
Restoring checkpoint: 90°
Power mode: always_on (default)
Initializing Matter...
I (1106) matter_bridge: Initializing Matter node...
I (1116) matter_bridge: Window Covering endpoint ID: 1
I (1116) matter_bridge: Discriminator derived from EUI-64: 173
I (1116) matter_bridge: Matter node initialized (VID=0xFFF1, PID=0x8001, disc=173)
Starting Matter...
I (1126) matter_bridge: Configuring OpenThread platform for Matter...
I (1136) matter_bridge: Starting Matter event loop...
...
I (1276) chip[DL]: Configuring CHIPoBLE advertising (interval 160 ms, connectable)
```

The device is advertising via BLE and ready for Matter commissioning.

## 5. Matter Pairing Information

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

## 6. Factory Reset

To clear all Matter and Thread credentials (e.g., to re-commission with a
different ecosystem):

```bash
# Erase the NVS partition
espflash erase-region --port /dev/cu.usbmodem101 0x9000 0x6000

# Reset the device
espflash reset --port /dev/cu.usbmodem101
```

The device reboots and starts BLE advertising for fresh commissioning.

## Partition Layout

The custom `partitions.csv` used at flash time:

| Name     | Type | SubType | Offset   | Size      |
|----------|------|---------|----------|-----------|
| nvs      | data | nvs     | 0x9000   | 0x6000 (24 KB) |
| phy_init | data | phy     | 0xf000   | 0x1000 (4 KB) |
| factory  | app  | factory | 0x10000  | 0x300000 (3 MB) |

Total flash used: ~3.1 MB out of 4 MB.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Device not found (`/dev/cu.usbmodem*`) | Check USB-C cable (some are charge-only), try a different port |
| `Segment 0 load address doesn't match` | You're using `espflash`'s bundled bootloader instead of the project-built one. Add the `--bootloader` flag (see Step 3) |
| `App/part. size` exceeds partition | Make sure you pass `--partition-table partitions.csv` to use the 3 MB partition |
| Build fails with linker errors | Run `source ~/export-esp.sh` |
| `controller_sleep_init` assert crash | Power management conflicts with BLE on ESP32-C6/v5.2.3. Ensure `CONFIG_PM_ENABLE` is commented out in `sdkconfig.defaults` |
| Thread won't connect | Device needs Matter commissioning first — it does not auto-join a Thread network |
| Servo doesn't move | Check wiring — signal goes to D2/GPIO2 (see `hardware/wiring.md`) |
