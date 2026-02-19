# Smart Vent Control System

Per-room HVAC vent control using ESP32-C6 + SG90 servos over Thread, managed by a Raspberry Pi 4B hub running Home Assistant.

## Architecture

```
RPi 4B (Hub)                           Thread Mesh (802.15.4)
+---------------------------+          +---------------------+
| Home Assistant            |   CoAP   | [Vent 1] -- Servo  |
|   +-- Vent Control      <----------->| [Vent 2] -- Servo  |
| OTBR (Docker)             |  (IPv6)  | [Vent N] -- Servo  |
|   +-- nRF52840 USB -------|--------->| (ESP32-C6 MTD/SED) |
| Hub Service (Python)      |          +---------------------+
+---------------------------+
```

## Quick Start

### Development (no hardware)

```bash
# 1. Start the simulator
cd tools/simulator && pip install -e .
vent-sim start --count 3

# 2. Install and use the hub CLI
cd hub && pip install -e ".[dev]"
vent-hub --help
vent-hub list

# 3. Run tests
pytest hub/tests/
pytest tests/integration/
```

### Hardware Setup

1. [Set up Raspberry Pi + OTBR](docs/guides/setup-rpi.md)
2. [Set up development environment](docs/guides/setup-dev-env.md)
3. [Wire ESP32-C6 + SG90](docs/hardware/wiring.md)
4. [Flash firmware](docs/guides/flash-firmware.md)
5. [Commission devices](docs/guides/commissioning.md)

## Project Structure

```
firmware/           Rust ESP32-C6 firmware
  vent-controller/  Main firmware application
  shared-protocol/  CBOR message types (shared crate)
hub/                Python hub service
  src/vent_hub/     CoAP client, device registry, group manager
  tests/            Unit tests
homeassistant/      Home Assistant custom component
tools/
  simulator/        Virtual vent devices for testing
  scripts/          Setup automation scripts
docs/               Architecture, protocol, and guides
tests/integration/  End-to-end tests (hub + simulator)
```

## Key Features

- **Per-vent control**: 90° (closed) to 180° (open)
- **Room/floor grouping**: Batch operations on groups of vents
- **Permanent device ID**: EUI-64 from ESP32-C6 eFuse
- **Auto-discovery**: New devices found via OTBR
- **Battery support**: Optional deep sleep (Thread SED mode)
- **Local only**: No cloud — all traffic stays on Thread mesh
- **Home Assistant**: Vents appear as cover entities

## Protocol

CoAP over IPv6/Thread with CBOR payloads:

| Resource | Methods | Purpose |
|----------|---------|---------|
| `/vent/position` | GET | Current position |
| `/vent/target` | PUT | Set position |
| `/device/identity` | GET | Device info |
| `/device/config` | GET, PUT | Room/floor config |
| `/device/health` | GET | Health telemetry |

See [communication-protocol.md](docs/communication-protocol.md) for full details.
