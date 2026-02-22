#!/usr/bin/env bash
# Setup OpenThread Border Router on Raspberry Pi 4B.
# Supports: Nordic nRF52840 dongle, SMLIGHT SLZB-07.
set -euo pipefail

echo "=== OTBR Setup for Vent Control System ==="

# Detect dongle type via USB vendor/product IDs
#   nRF52840:  1915:cafe  (Nordic Semiconductor)
#   SLZB-07:   10c4:ea60  (CP2102N / Silicon Labs USB-UART)
DONGLE_TYPE=""
if lsusb | grep -q "1915:cafe\|1915:521f\|Nordic"; then
    DONGLE_TYPE="nrf52840"
    echo "Detected: Nordic nRF52840 dongle"
elif lsusb | grep -q "10c4:ea60"; then
    DONGLE_TYPE="slzb07"
    echo "Detected: SMLIGHT SLZB-07 (CP2102N)"
else
    echo "WARNING: No supported dongle detected."
    echo "  Supported dongles:"
    echo "    - Nordic nRF52840 (1915:cafe)"
    echo "    - SMLIGHT SLZB-07 (10c4:ea60)"
    echo "  Plug in your dongle and re-run, or set DONGLE_DEV and BAUD_RATE manually."
fi

# Install Docker if not present
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$USER"
    echo "Docker installed. Log out and back in, then re-run this script."
    exit 0
fi

# Ensure ip6tables kernel modules are loaded (required by OTBR firewall)
if ! lsmod | grep -q ip6table_filter; then
    echo "Loading ip6tables kernel modules..."
    sudo modprobe ip6table_filter
    sudo modprobe ip6_tables
    # Persist across reboots
    grep -q ip6table_filter /etc/modules 2>/dev/null || echo "ip6table_filter" | sudo tee -a /etc/modules
    grep -q ip6_tables /etc/modules 2>/dev/null || echo "ip6_tables" | sudo tee -a /etc/modules
fi

# Determine serial device and baud rate based on dongle type
DONGLE_DEV="${DONGLE_DEV:-}"
BAUD_RATE="${BAUD_RATE:-}"

if [ -z "$DONGLE_DEV" ]; then
    case "$DONGLE_TYPE" in
        nrf52840)
            # nRF52840 uses CDC-ACM driver
            for dev in /dev/ttyACM0 /dev/ttyACM1; do
                if [ -e "$dev" ]; then
                    DONGLE_DEV="$dev"
                    break
                fi
            done
            ;;
        slzb07)
            # SLZB-07 uses CP2102N USB-UART (ttyUSB)
            for dev in /dev/ttyUSB0 /dev/ttyUSB1; do
                if [ -e "$dev" ]; then
                    DONGLE_DEV="$dev"
                    break
                fi
            done
            ;;
        *)
            # Unknown dongle type — try all common paths
            for dev in /dev/ttyACM0 /dev/ttyACM1 /dev/ttyUSB0 /dev/ttyUSB1; do
                if [ -e "$dev" ]; then
                    DONGLE_DEV="$dev"
                    break
                fi
            done
            ;;
    esac
fi

if [ -z "$DONGLE_DEV" ]; then
    echo "ERROR: No serial device found. Check that your dongle is plugged in."
    exit 1
fi

if [ -z "$BAUD_RATE" ]; then
    case "$DONGLE_TYPE" in
        nrf52840) BAUD_RATE=1000000 ;;
        slzb07)   BAUD_RATE=460800  ;;
        *)        BAUD_RATE=460800  ;;
    esac
fi

echo "Using dongle at: $DONGLE_DEV (baud: $BAUD_RATE)"

# Pull and run OTBR Docker container
echo "Starting OTBR container..."
docker pull nrfconnect/otbr:latest 2>/dev/null || docker pull openthread/otbr:latest

docker run -d \
    --name otbr \
    --restart unless-stopped \
    --network host \
    --privileged \
    -v /dev:/dev \
    -e RADIO_URL="spinel+hdlc+uart://${DONGLE_DEV}?uart-baudrate=${BAUD_RATE}" \
    -e BACKBONE_INTERFACE=eth0 \
    openthread/otbr:latest

# Wait for OTBR to start and verify
echo "Waiting for OTBR to start..."
sleep 5

if curl -s -o /dev/null -w "%{http_code}" http://localhost:8081/v1/node/state 2>/dev/null | grep -q "200"; then
    echo ""
    echo "OTBR is running and responding!"
else
    echo ""
    echo "OTBR container started (ports may take a moment to become available)."
    echo "Check status with: docker logs otbr"
fi

echo ""
echo "  REST API: http://localhost:8081"
echo "  Web GUI:  http://localhost:80"
echo ""
echo "NOTE: 'docker ps' will NOT show ports in the PORTS column when using"
echo "      --network host. This is normal — all ports are exposed directly."
echo "      Verify with: curl http://localhost:8081/v1/node/state"
echo ""
echo "Next steps:"
echo "  1. Open the web GUI and form a new Thread network"
echo "  2. Note the network credentials for device commissioning"
echo "  3. Run setup_ha.sh to install Home Assistant"
