# smart-vent

Per-room HVAC vent control. Each vent has a small XIAO ESP32-C6 board driving an SG90
hobby servo that opens or closes a louver. The board joins a Thread mesh hosted by a
Raspberry Pi and exposes itself as a Matter **Window Covering** device. Home Assistant
runs on the same Pi and is the user-facing controller — you toggle the vent in the HA UI
or in a HA automation, and the command travels over Matter-over-Thread to the device,
which moves the servo.

The project is **Matter-over-Thread only**. There is no Wi-Fi path on the device, and no
cloud dependency. The Pi is the entire backend.

## Hardware

| Role | Part | Notes |
|------|------|-------|
| Hub | Raspberry Pi (any model with USB) | Runs three Docker containers: OTBR, matter-server, Home Assistant |
| Thread radio | SMLIGHT SLZB-07 USB dongle | CP210x USB-UART (`10c4:ea60`), enumerates as `/dev/ttyUSB0`. Used by OTBR as the Thread Radio Co-Processor |
| Vent MCU | Seeed XIAO ESP32-C6 | RISC-V chip with built-in 802.15.4 and BLE radios. Enumerates as `/dev/ttyACM0` (`303a:1001`) when plugged **directly** into the Pi — not through a USB hub |
| Actuator | SG90 servo | Signal on GPIO2 (XIAO D2 pin). 90° = vent closed, 180° = vent open |

## Architecture at a glance

```
   ┌─────────────────────── Raspberry Pi ──────────────────────────┐
   │                                                                │
   │  Home Assistant ── (WebSocket) ──► matter-server               │
   │       (:8123)                       (:5580)                    │
   │                                        │ BLE pairing           │
   │                                        ▼                       │
   │                                     BlueZ ─── (host BT)        │
   │                                        │                       │
   │                                        │ Matter ops over IPv6  │
   │                                        ▼                       │
   │                                     OTBR (OpenThread Border    │
   │                                           Router container)    │
   │                                        │                       │
   │                                        │ Thread (802.15.4)     │
   └────────────────────────────────────────┼───────────────────────┘
                                            │  ▲
                                  via SLZB-07 USB dongle
                                            │  │
                              ┌─────────────▼──┴────────────┐
                              │   XIAO ESP32-C6 (vent N)    │
                              │   Rust firmware + esp-matter│
                              │   GPIO2 ─► SG90 servo       │
                              └─────────────────────────────┘
```

## Where to look

- **[docs/handbook.md](docs/handbook.md)** — what the system is, how it works, why
  it's built the way it is. Read this top-to-bottom once. Covers Matter, Thread,
  the Pi services, the firmware internals, what happens during commissioning and
  on every replug.
- **[docs/dev-setup.md](docs/dev-setup.md)** — what to install on your own dev
  machine (Linux x86_64 recommended, Pi for deployment/validation, macOS as
  a secondary option) before touching firmware, the SD image, the Pi hub
  stack, the provisioning CLI, or the PCB tooling.
- **[docs/runbook.md](docs/runbook.md)** — step-by-step procedures for **developers**.
  How to set up the Pi from scratch, build the firmware, flash a new vent, commission
  it via HA, assign it to a room. Plus a symptom-driven troubleshooting matrix.
- **[docs/provider-runbook.md](docs/provider-runbook.md)** — step-by-step for
  **providers** assembling kits to ship to clients. Uses the
  `smart-vent-provision` CLI end-to-end: bake the SD card, flash + capture N
  vents, print stickers + quick-start, pack and ship. No source builds.
- **[docs/mobile-api.md](docs/mobile-api.md)** — API contract the smart-vent mobile
  app builds against (matter-server WS, HA REST, mDNS).
- **[docs/mobile-app-spec.md](docs/mobile-app-spec.md)** — screen-by-screen spec
  the Flutter team works from.

## Repo layout

```
firmware/
  vent-controller/                 ESP32-C6 firmware (Rust + ESP-IDF v5.2.3)
    src/                           Rust modules: main, matter, servo, state, identity, ...
    components/esp_matter_bridge/  C++ shim over esp-matter SDK
    sdkconfig.defaults             Non-default ESP-IDF kconfig
    partitions.csv                 nvs / phy_init / 3 MB factory app layout
  shared-protocol/                 vent-protocol crate (CBOR types, angle constants)
docs/
  handbook.md                      Conceptual reference
  runbook.md                       Step-by-step procedures
homeassistant/                     Example HA configs (scripts, automations,
                                   schedule helpers, Lovelace dashboard) for
                                   room/floor grouping and scheduling. Copy
                                   into ~/homeassistant/. See runbook §7.5.
tools/
  scripts/                         setup_otbr.sh, setup_ha.sh — reference Pi bring-up
  qr-generator/                    Renders printable QR PNGs from the boot-logged Matter payload
```

## Status

All firmware code lives on the `feature/matter-over-thread` branch. One vent has been
fully commissioned and verified end-to-end (HA → Close button → servo turns to 90°,
HA → Open → servo turns to 180°). The same firmware image can be flashed onto any
number of XIAO ESP32-C6 boards to add more vents — see the runbook.
