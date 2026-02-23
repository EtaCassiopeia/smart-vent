# Smart Vent Control System

Per-room HVAC vent control using ESP32-C6 + SG90 servos over Thread. Supports **Matter** for Google Home, Alexa, and Apple Home, plus a CoAP protocol for the custom Python hub and Home Assistant integration.

## Architecture

![Architecture Overview](docs/diagrams/architecture-simple.svg)

See [docs/architecture.md](docs/architecture.md) for the full architecture reference, including data flow diagrams, device lifecycle, power management, security model, and a glossary of all technologies used.

## Quick Start

> **First time?** Start with the [development environment setup guide](docs/guides/setup-dev-env.md) to install Python, Rust, and IDE configuration.

### Development (no hardware)

The simulator creates virtual vent devices on localhost that respond to CoAP requests, replacing real ESP32 hardware for testing.

```bash
# Run all tests (hub unit tests + integration tests against the simulator)
pytest hub/tests/
pytest tests/integration/
```

The integration tests automatically start and stop the simulator. You can also run it manually to explore the CLI:

```bash
# Terminal 1: start 3 virtual vents (runs in foreground, Ctrl+C to stop)
vent-sim start --count 3

# Terminal 2: explore hub commands
vent-hub --help
```

> **Note:** `vent-hub discover` requires a Thread Border Router and won't find simulator vents. The simulator is for integration tests and direct CoAP interaction.

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

- **Matter support**: Works with Google Home, Alexa, Apple Home, and HA Matter integration
- **Per-vent control**: 90° (closed) to 180° (open)
- **Room/floor grouping**: Batch operations on groups of vents
- **Permanent device ID**: EUI-64 from ESP32-C6 eFuse
- **BLE commissioning**: Scan a QR code to add devices to any ecosystem
- **Multi-admin**: Control from multiple ecosystems simultaneously
- **Auto-discovery**: New devices found via OTBR (legacy CoAP) or Matter commissioning
- **Battery support**: Optional deep sleep (Thread SED mode)
- **Local only**: No cloud — all traffic stays on Thread mesh
- **Home Assistant**: Vents appear as cover entities (via Matter or custom component)

## Protocol

The firmware runs two protocols simultaneously over Thread:

**Matter** (Window Covering cluster) — Industry standard, used by Google Home/Alexa/Apple Home/HA:

| Cluster | Commands | Purpose |
|---------|----------|---------|
| Window Covering | UpOrOpen, DownOrClose, GoToLiftPercentage | Position control |
| Window Covering | CurrentPositionLiftPercent100ths | Position reporting |
| Identify | Identify | Servo wiggle for identification |

**CoAP + CBOR** — Custom protocol for the Python hub:

| Resource | Methods | Purpose |
|----------|---------|---------|
| `/vent/position` | GET | Current position |
| `/vent/target` | PUT | Set position |
| `/device/identity` | GET | Device info |
| `/device/config` | GET, PUT | Room/floor config |
| `/device/health` | GET | Health telemetry |

See [communication-protocol.md](docs/communication-protocol.md) for full details.
