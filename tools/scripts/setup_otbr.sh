#!/usr/bin/env bash
# Setup OpenThread Border Router on Raspberry Pi 4B with nRF52840 dongle.
set -euo pipefail

echo "=== OTBR Setup for Vent Control System ==="

# Check for nRF52840 dongle
if ! lsusb | grep -q "1915:cafe\|Nordic"; then
    echo "WARNING: nRF52840 dongle not detected. Plug it in and re-run."
fi

# Install Docker if not present
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$USER"
    echo "Docker installed. Log out and back in, then re-run this script."
    exit 0
fi

# Determine the nRF52840 serial device
DONGLE_DEV=""
for dev in /dev/ttyACM0 /dev/ttyACM1 /dev/ttyUSB0; do
    if [ -e "$dev" ]; then
        DONGLE_DEV="$dev"
        break
    fi
done

if [ -z "$DONGLE_DEV" ]; then
    echo "ERROR: No serial device found for nRF52840 dongle."
    exit 1
fi

echo "Using nRF52840 dongle at: $DONGLE_DEV"

# Pull and run OTBR Docker container
echo "Starting OTBR container..."
docker pull nrfconnect/otbr:latest 2>/dev/null || docker pull openthread/otbr:latest

docker run -d \
    --name otbr \
    --restart unless-stopped \
    --network host \
    --privileged \
    -v /dev:/dev \
    -e RADIO_URL="spinel+hdlc+uart://${DONGLE_DEV}?uart-baudrate=1000000" \
    -e BACKBONE_INTERFACE=eth0 \
    openthread/otbr:latest

echo ""
echo "OTBR is running!"
echo "  REST API: http://localhost:8081"
echo "  Web GUI:  http://localhost:80"
echo ""
echo "Next steps:"
echo "  1. Open the web GUI and form a new Thread network"
echo "  2. Note the network credentials for device commissioning"
echo "  3. Run setup_ha.sh to install Home Assistant"
