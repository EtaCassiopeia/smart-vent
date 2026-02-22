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

## 4. Install OTBR

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

## 5. Form Thread Network

1. Open OTBR web GUI: `http://<rpi-ip>:80`
2. Click "Form" to create a new Thread network
3. Save the network credentials (you'll need these for commissioning)

Verify via REST API:

```bash
curl http://localhost:8081/v1/node/dataset/active
```

## 6. Install Home Assistant

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

## 7. Install Vent Control Component

Copy the custom component:

```bash
cp -r vent/homeassistant/custom_components/vent_control \
    ~/homeassistant/custom_components/
docker restart homeassistant
```

## Verification

- OTBR REST API responds: `curl http://localhost:8081/v1/node/state`
- Home Assistant web UI loads: `http://<rpi-ip>:8123`
- Thread network is active and ready for devices
