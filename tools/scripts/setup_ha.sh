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

# Run Home Assistant container
echo "Starting Home Assistant..."
docker run -d \
    --name homeassistant \
    --restart unless-stopped \
    --network host \
    -v "${HA_CONFIG_DIR}:/config" \
    -v /etc/localtime:/etc/localtime:ro \
    ghcr.io/home-assistant/home-assistant:stable

echo ""
echo "Home Assistant is starting!"
echo "  Web UI: http://localhost:8123"
echo ""
echo "First-time setup:"
echo "  1. Open http://localhost:8123 and create an account"
echo "  2. Go to Settings -> Devices & Services -> Add Integration"
echo "  3. Search for 'Smart Vent Control' and configure the hub"
