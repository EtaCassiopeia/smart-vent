#!/usr/bin/env bash
# Setup Home Assistant Container on Raspberry Pi 4B.
set -euo pipefail

echo "=== Home Assistant Setup for Vent Control System ==="

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker not installed. Run setup_otbr.sh first."
    exit 1
fi

HA_CONFIG_DIR="${HOME}/homeassistant"
mkdir -p "$HA_CONFIG_DIR"

# Copy custom component
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
COMPONENT_SRC="${PROJECT_DIR}/homeassistant/custom_components/vent_control"

if [ -d "$COMPONENT_SRC" ]; then
    mkdir -p "${HA_CONFIG_DIR}/custom_components/vent_control"
    cp -r "$COMPONENT_SRC/"* "${HA_CONFIG_DIR}/custom_components/vent_control/"
    echo "Vent Control component installed to ${HA_CONFIG_DIR}/custom_components/"
fi

# Locate the hub database for device discovery
HUB_DB="${HUB_DB:-${PROJECT_DIR}/devices.db}"
if [ ! -f "$HUB_DB" ]; then
    echo "WARNING: Hub database not found at $HUB_DB"
    echo "  Run 'vent-hub discover' first, or set HUB_DB to the correct path."
fi

# Create a shared data directory for the Matter server
MATTER_DATA_DIR="${HOME}/matter-server"
mkdir -p "$MATTER_DATA_DIR"

# Start the Matter Server container (required for HA Matter integration).
# HA Container installs do not include the Matter server — it must run as a
# separate container. The HA Matter integration connects to it via WebSocket
# on port 5580.
if docker ps -a --format '{{.Names}}' | grep -q '^matter-server$'; then
    echo "Matter server container already exists. Starting..."
    docker start matter-server 2>/dev/null || true
else
    echo "Starting Matter server..."
    docker run -d \
        --name matter-server \
        --restart unless-stopped \
        --network host \
        --security-opt apparmor=unconfined \
        -v "${MATTER_DATA_DIR}:/data" \
        -v /run/dbus:/run/dbus:ro \
        ghcr.io/home-assistant-libs/python-matter-server:stable \
        --storage-path /data --paa-root-cert-dir /data/credentials
fi

# Wait briefly for Matter server to be ready
echo "Waiting for Matter server to start..."
sleep 3

# Verify Matter server is listening
if curl -s -o /dev/null -w '%{http_code}' http://localhost:5580 2>/dev/null | grep -q '4\|2'; then
    echo "Matter server is running on port 5580"
else
    echo "WARNING: Matter server may still be starting. Check: docker logs matter-server"
fi

# Run Home Assistant container
echo "Starting Home Assistant..."
docker run -d \
    --name homeassistant \
    --restart unless-stopped \
    --network host \
    -v "${HA_CONFIG_DIR}:/config" \
    -v "${HUB_DB}:/config/devices.db" \
    -v /etc/localtime:/etc/localtime:ro \
    ghcr.io/home-assistant/home-assistant:stable

echo ""
echo "Home Assistant is starting!"
echo "  Web UI: http://localhost:8123"
echo "  Matter server WebSocket: ws://localhost:5580/ws"
echo ""
echo "First-time setup:"
echo "  1. Open http://localhost:8123 and create an account"
echo "  2. Go to Settings -> Devices & Services -> Add Integration"
echo "  3. Search for 'Matter (BETA)' and add it"
echo "     - Use WebSocket URL: ws://localhost:5580/ws"
echo "  4. Optionally add 'Smart Vent Control' for CoAP telemetry"
