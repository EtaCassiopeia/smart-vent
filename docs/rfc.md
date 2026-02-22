# Smart Vent Control System — RFC

## 1. Overview

A smart HVAC vent control system using ESP32-C6 microcontrollers with SG90 servos, communicating over Thread (802.15.4) to a Raspberry Pi 4B hub running Home Assistant.

The system provides per-vent, per-room, and per-floor control of vent positions with permanent device identifiers, auto-discovery, deep sleep support, and local-network-only access.

## 2. Goals

- **Per-vent control**: Each vent independently controllable (90°=closed, 180°=open)
- **Grouping**: Vents organized by room and floor for batch operations
- **Permanent identity**: EUI-64 hardware identifier per device, survives reflash
- **Auto-discovery**: New devices discoverable via OTBR without manual IP config
- **Low power**: Optional battery operation with Thread SED deep sleep
- **Local only**: No cloud dependency; all communication on local Thread/IPv6 mesh
- **Home Assistant integration**: Custom component exposes vents as cover entities

## 3. Hardware

### 3.1 Vent Controller (per vent)
- **MCU**: ESP32-C6 (802.15.4 + WiFi + BLE, RISC-V)
- **Servo**: SG90 micro servo (90°–180° operating range)
- **Power**: USB-C (always-on) or 3×AA battery (deep sleep mode)
- **Radio**: Built-in 802.15.4 for Thread

### 3.2 Hub
- **SBC**: Raspberry Pi 4B
- **Thread radio**: Nordic nRF52840 USB dongle or SMLIGHT SLZB-07 (flashed with OT RCP firmware)
- **Software**: Home Assistant OS/Container + OTBR (Docker)

## 4. Architecture

![Architecture Overview](diagrams/architecture-simple.svg)

### 4.1 Communication Flow

1. ESP32-C6 joins Thread network as MTD (Minimal Thread Device)
2. Device registers multicast group and exposes CoAP resources
3. Hub discovers devices via OTBR REST API (`/node/rloc` endpoint)
4. Hub communicates with devices over CoAP/UDP/IPv6
5. Home Assistant polls hub service for state updates

### 4.2 Network Topology

- Thread mesh with OTBR as border router
- Devices are MTDs (or SEDs if battery-powered)
- All traffic stays on local IPv6 mesh — no internet required
- Hub accesses Thread mesh via OTBR's IPv6 bridge

## 5. Firmware (Rust, ESP32-C6)

### 5.1 Modules

| Module | Responsibility |
|--------|---------------|
| `main.rs` | Task orchestration, startup sequence |
| `servo.rs` | LEDC PWM control for SG90 (90°–180°) |
| `state.rs` | Vent state machine (Open/Closed/Partial/Moving) |
| `identity.rs` | EUI-64 from eFuse, NVS config storage |
| `thread.rs` | OpenThread init, network join, credential storage |
| `coap.rs` | CoAP server with resource handlers |
| `power.rs` | Deep sleep, SED configuration |

### 5.2 Servo Control

- PWM via LEDC peripheral at 50 Hz
- Duty cycle mapping: 90° (closed) = ~1ms pulse, 180° (open) = ~2ms pulse
- Gradual movement (1° per 15ms) to prevent current spikes
- Position persisted in NVS for recovery after reboot

### 5.3 State Machine

![State Machine](diagrams/state-machine.svg)

### 5.4 Device Identity

- Primary ID: EUI-64 read from ESP32-C6 eFuse (permanent, unique)
- User config (room, floor, name) stored in NVS flash
- First boot detected by absence of NVS `initialized` key
- Power mode persisted in NVS: `pwr_mode` key (`"always_on"` or `"sed"`), `poll_ms` key (u32 LE bytes)
- On boot, power mode is read from NVS to configure SED behavior (defaults to always-on if unset)

## 6. Hub Service (Python)

### 6.1 Components

| Component | Responsibility |
|-----------|---------------|
| `models.py` | VentDevice, Room, Floor data models |
| `coap_client.py` | Async CoAP GET/PUT via aiocoap |
| `device_registry.py` | SQLite CRUD for device inventory |
| `group_manager.py` | Room/floor grouping, batch ops |
| `discovery.py` | OTBR REST API device discovery |
| `scheduler.py` | Time-based automation rules |
| `config.py` | YAML hub configuration |
| `cli.py` | Click CLI for manual control |

### 6.2 Device Registry

SQLite database storing:
- Device EUI-64 (primary key)
- IPv6 address (from Thread)
- Room and floor assignment
- Last seen timestamp
- Current vent position
- Firmware version

### 6.3 Discovery

Periodically queries OTBR REST API for Thread device list, correlates with known devices, and adds new ones to registry.

## 7. Home Assistant Integration

- Custom component `vent_control`
- Each vent exposed as a `cover` entity (position 0-100%)
- Position mapping: 0% = closed (90 deg), 100% = open (180 deg)
- Devices auto-assigned to HA areas based on room config
- Data update coordinator polls devices every 30s (configurable): position, identity, config, and health
- Cover entity exposes rssi, power_source, free_heap, battery_mv as extra state attributes
- `is_opening`/`is_closing` reflect movement direction (current angle vs coordinator-tracked target)

## 8. Testing Strategy

1. **Firmware unit tests**: `cargo test` on host (state machine, protocol)
2. **Firmware integration**: Flash to ESP32-C6, test via serial monitor
3. **Hub unit tests**: pytest with mocked CoAP responses
4. **Simulator**: Python CoAP server mimicking N vent devices
5. **Integration tests**: Hub CLI → CoAP → Simulator end-to-end
6. **HA testing**: Simulator provides fake devices to HA component

## 9. Security Considerations

- Thread provides AES-128 encryption at network layer
- No internet access required or configured
- OTBR commissioning requires physical proximity (Thread joining)
- No authentication on CoAP (Thread network membership = trust)
- Future: DTLS for CoAP if multi-tenant scenarios arise

## 10. Power Modes

| Mode | Thread Role | Wake | Use Case |
|------|------------|------|----------|
| Always-on | MTD | N/A | USB-powered vents |
| SED | SED | Poll period (configurable) | Battery-powered vents |

SED poll period default: 5 seconds. Persisted in NVS as `poll_ms` (u32, little-endian). Power mode is set by writing the `pwr_mode` NVS key (`"always_on"` or `"sed"`). Changes take effect on next reboot.
