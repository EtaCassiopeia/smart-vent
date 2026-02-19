# Raspberry Pi 4B Hub Setup

## Prerequisites

- Raspberry Pi 4B with Raspberry Pi OS (64-bit)
- Nordic nRF52840 USB dongle (flashed with OT RCP firmware)
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

## 3. Flash nRF52840 with RCP Firmware

The nRF52840 dongle must run OpenThread RCP (Radio Co-Processor) firmware.

Download pre-built RCP firmware from the OpenThread repository or build from source:

```bash
# Using nRF Connect SDK
west build -b nrf52840dongle_nrf52840 nrf/samples/openthread/coprocessor -- \
    -DOVERLAY_CONFIG=overlay-rcp.conf
nrfutil pkg generate --hw-version 52 --sd-req=0x00 \
    --application build/zephyr/zephyr.hex --application-version 1 rcp.zip
nrfutil dfu usb-serial -pkg rcp.zip -p /dev/ttyACM0
```

## 4. Install OTBR

Run the provided setup script:

```bash
cd vent/tools/scripts
./setup_otbr.sh
```

Or manually:

```bash
docker run -d --name otbr --network host --privileged \
    -v /dev:/dev \
    -e RADIO_URL="spinel+hdlc+uart:///dev/ttyACM0?uart-baudrate=1000000" \
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
