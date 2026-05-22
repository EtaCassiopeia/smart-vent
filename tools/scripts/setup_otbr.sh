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

# Detect backbone interface (first UP non-loopback interface with a default route)
BACKBONE="${BACKBONE_INTERFACE:-}"
if [ -z "$BACKBONE" ]; then
    BACKBONE=$(ip -br link show | awk '/UP/ && !/^lo / {print $1; exit}')
    if [ -z "$BACKBONE" ]; then
        BACKBONE="eth0"
    fi
fi
echo "Using backbone interface: $BACKBONE"

# Pull and run OTBR Docker container
echo "Starting OTBR container..."
docker pull nrfconnect/otbr:latest 2>/dev/null || docker pull openthread/otbr:latest

docker run -d \
    --name otbr \
    --restart unless-stopped \
    --network host \
    --privileged \
    -v /dev:/dev \
    -v otbr-data:/var/lib/thread \
    -e RADIO_URL="spinel+hdlc+uart://${DONGLE_DEV}?uart-baudrate=${BAUD_RATE}" \
    -e BACKBONE_INTERFACE="${BACKBONE}" \
    openthread/otbr:latest

# Wait for OTBR to start and verify
echo "Waiting for OTBR to start..."
sleep 5

OT_STATE=$(docker exec otbr ot-ctl state 2>/dev/null | tr -d '[:space:]')
BACKUP_DIR="$HOME/.thread"
BACKUP_FILE="$BACKUP_DIR/dataset-backup.txt"

if [ -n "$OT_STATE" ] && [ "$OT_STATE" != "disabled" ]; then
    echo ""
    echo "OTBR is running! Thread state: $OT_STATE"

    # Back up the active dataset for disaster recovery
    echo "Backing up active dataset..."
    mkdir -p "$BACKUP_DIR"
    docker exec otbr ot-ctl dataset active -x | tr -d '[:space:]' > "$BACKUP_FILE"
    chmod 600 "$BACKUP_FILE"
    echo "Dataset backed up to $BACKUP_FILE"
elif [ "$OT_STATE" = "disabled" ] && [ -f "$BACKUP_FILE" ]; then
    # Fresh container with no network — attempt to restore from backup
    echo ""
    echo "Thread state is 'disabled' and a dataset backup exists."
    echo "Restoring dataset from $BACKUP_FILE..."
    DATASET=$(cat "$BACKUP_FILE" | tr -d '[:space:]')
    if [ -n "$DATASET" ]; then
        docker exec otbr ot-ctl dataset set active "$DATASET"
        docker exec otbr ot-ctl ifconfig up
        docker exec otbr ot-ctl thread start
        sleep 3
        OT_STATE=$(docker exec otbr ot-ctl state 2>/dev/null | tr -d '[:space:]')
        echo "Dataset restored. Thread state: $OT_STATE"
    else
        echo "WARNING: Backup file is empty. Skipping restore."
    fi
else
    echo ""
    echo "OTBR container started but Thread stack may still be initializing."
    echo "Check status with: docker exec otbr ot-ctl state"
    echo "Check logs with:   docker logs otbr"
fi

echo ""
echo "Useful commands:"
echo "  docker exec otbr ot-ctl state          # Check Thread state"
echo "  docker exec otbr ot-ctl dataset active  # View active dataset"
echo "  docker logs otbr                        # View container logs"
echo ""
echo "Next steps:"
echo "  1. Open the web GUI (http://localhost:80) and form a new Thread network"
echo "  2. Note the network credentials for device commissioning"
echo "  3. Run setup_ha.sh to install Home Assistant"
if [ -f "$BACKUP_FILE" ]; then
    echo ""
    echo "Dataset backup: $BACKUP_FILE"
    echo "  This file contains the Thread network key. Keep it secure (chmod 600)."
fi
