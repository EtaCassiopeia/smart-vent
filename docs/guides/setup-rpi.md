# Raspberry Pi 4B Hub Setup

## Prerequisites

- Raspberry Pi 4B with Raspberry Pi OS (64-bit)
- A Thread RCP dongle — **one** of the following:
  - Nordic nRF52840 USB dongle (PCA10059)
  - SMLIGHT SLZB-07
- Ethernet or WiFi connection
- MicroSD card (32GB+)

## 1. Flash Raspberry Pi OS

1. Download Raspberry Pi Imager
2. Flash Raspberry Pi OS Lite (64-bit) to SD card
3. Enable SSH in imager settings
4. Boot the Pi and connect via SSH

## 2. Update System

```bash
sudo apt update && sudo apt upgrade -y
```

## 3. Flash Dongle with RCP Firmware

Your USB dongle must run OpenThread RCP (Radio Co-Processor) firmware.
Follow the section for your dongle below.

### Option A: Nordic nRF52840 (PCA10059)

Download pre-built RCP firmware from the OpenThread repository or build from source:

```bash
# Using nRF Connect SDK
west build -b nrf52840dongle_nrf52840 nrf/samples/openthread/coprocessor -- \
    -DOVERLAY_CONFIG=overlay-rcp.conf
nrfutil pkg generate --hw-version 52 --sd-req=0x00 \
    --application build/zephyr/zephyr.hex --application-version 1 rcp.zip
nrfutil dfu usb-serial -pkg rcp.zip -p /dev/ttyACM0
```

The dongle appears as `/dev/ttyACM0` (or `ttyACM1`).

### Option B: SMLIGHT SLZB-07

The SLZB-07 ships with Zigbee firmware by default. You must re-flash it with
OpenThread RCP firmware before it can be used with this project.

1. Open the SMLIGHT web flasher: <https://smlight.tech/flasher/>
2. Connect the SLZB-07 via USB and select it
3. Choose firmware type **Thread (RCP)** for the EFR32MG21 chip
4. Flash the firmware

Alternatively, use the community [Silicon Labs firmware builder](https://darkxst.github.io/silabs-firmware-builder/)
to download an `ot-rcp` firmware image for the EFR32MG21 and flash with:

```bash
# Install the Silicon Labs flash tool
pip install universal-silabs-flasher

# Flash OT RCP firmware (replace with your actual firmware file)
universal-silabs-flasher --device /dev/ttyUSB0 \
    flash --firmware ot-rcp-v2.4.x-slzb-07.gbl
```

The SLZB-07 uses a CP2102N USB-UART chip and appears as `/dev/ttyUSB0`.

## 4. Load Kernel Modules

OTBR requires `ip6tables` kernel modules for firewall and routing. These are
not loaded by default on Raspberry Pi OS:

```bash
sudo modprobe ip6table_filter
sudo modprobe ip6_tables
```

Make them load automatically on boot:

```bash
echo "ip6table_filter" | sudo tee -a /etc/modules
echo "ip6_tables" | sudo tee -a /etc/modules
```

## 5. Install OTBR

Run the provided setup script:

```bash
cd vent/tools/scripts
./setup_otbr.sh
```

The script auto-detects your dongle type (nRF52840 or SLZB-07) and configures
the correct serial device and baud rate.

Or manually:

```bash
# nRF52840: /dev/ttyACM0 at 1000000 baud
docker run -d --name otbr --network host --privileged \
    -v /dev:/dev \
    -e RADIO_URL="spinel+hdlc+uart:///dev/ttyACM0?uart-baudrate=1000000" \
    openthread/otbr:latest

# SLZB-07: /dev/ttyUSB0 at 460800 baud
docker run -d --name otbr --network host --privileged \
    -v /dev:/dev \
    -e RADIO_URL="spinel+hdlc+uart:///dev/ttyUSB0?uart-baudrate=460800" \
    openthread/otbr:latest
```

> **Note:** `docker ps` will not show ports in the PORTS column when using `--network host`.
> This is normal — all container ports are exposed directly on the host.

Verify OTBR is running:

```bash
docker exec otbr ot-ctl state
```

## 6. Form Thread Network

### Option A: Matter commissioning (recommended)

If you are using Matter-enabled firmware (v0.2.0+), the OTBR forms a Thread
network automatically on startup — **no manual credential configuration is
needed**. During Matter commissioning (via Google Home, Alexa, HA, or
chip-tool), the controller reads the Thread dataset from the OTBR and pushes
it to the device via BLE.

Verify the OTBR has formed a network:

```bash
docker exec otbr ot-ctl state          # Should show "leader"
docker exec otbr ot-ctl dataset active  # Note for reference (not needed in firmware)
```

> **Thread resilience:** Because Thread credentials are provisioned during BLE
> commissioning (not hardcoded in firmware), recreating the OTBR with a new
> dataset no longer requires reflashing devices. Instead, factory-reset the
> device and re-commission it. See the
> [quick start guide](quick-start-matter.md#thread-network-resilience) for
> recovery steps.

### Option B: Legacy CoAP commissioning (v0.1.x)

For the CoAP-only firmware, configure the OTBR to use the same credentials as the
firmware defaults so devices join automatically:

```bash
docker exec otbr ot-ctl dataset clear
docker exec otbr ot-ctl dataset networkkey 00112233445566778899aabbccddeeff
docker exec otbr ot-ctl dataset channel 15
docker exec otbr ot-ctl dataset panid 0x1234
docker exec otbr ot-ctl dataset networkname OpenThreadDemo
docker exec otbr ot-ctl dataset commit active
docker exec otbr ot-ctl ifconfig up
docker exec otbr ot-ctl thread start
```

Verify the dataset and state:

```bash
docker exec otbr ot-ctl dataset active
docker exec otbr ot-ctl state
```

> **Security note:** The default development credentials are not secure. For
> production, generate unique credentials and update both the OTBR and firmware.
> See `commissioning.md` for details.
>
> **Important:** If you recreate the OTBR container, `dataset init new`
> generates a new Extended PAN ID. Devices that joined the old network will NOT
> rejoin — they must be reflashed. This limitation does not apply to the Matter
> firmware path (Option A).

## 7. Install Home Assistant

Run the provided setup script:

```bash
./setup_ha.sh
```

Or manually:

```bash
docker run -d --name homeassistant --network host \
    -v ~/homeassistant:/config \
    ghcr.io/home-assistant/home-assistant:stable
```

### Enable the Matter integration (recommended)

1. Open `http://<rpi-ip>:8123`
2. Go to **Settings** -> **Devices & Services** -> **Add Integration**
3. Search for **Matter (BETA)** and add it
4. Follow the setup wizard to connect to the Matter server

This enables HA to commission Matter devices directly and control them as
standard Cover entities — no custom component needed.

## 8. Install Vent Control Component (Optional)

The custom component provides extended telemetry (RSSI, heap, room/floor)
via CoAP. It works alongside the Matter integration.

```bash
cp -r vent/homeassistant/custom_components/vent_control \
    ~/homeassistant/custom_components/
docker restart homeassistant
```

## Verification

- OTBR is running: `docker exec otbr ot-ctl state` (should show `leader` or `router`)
- Thread dataset is set: `docker exec otbr ot-ctl dataset active`
- Home Assistant web UI loads: `http://<rpi-ip>:8123`
- Matter integration is enabled (if using Matter firmware)

## Next Steps

- **Matter firmware**: Follow the [Quick Start: Matter over Thread](quick-start-matter.md) guide
- **Legacy CoAP firmware**: Follow the [Commissioning Guide](commissioning.md#legacy-coap-commissioning)
