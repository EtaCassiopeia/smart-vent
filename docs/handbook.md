# smart-vent Handbook

This is the conceptual reference for the smart-vent system. It explains what every
component does, how Matter and Thread fit together, what's happening inside the
ESP32-C6 firmware, what a single "close the vent" command actually traverses, and
why specific design choices were made. When you want a step-by-step recipe instead,
go to **[runbook.md](runbook.md)** — sections in this handbook cross-reference to
runbook procedures using "see runbook §N".

Read top-to-bottom on the first pass. After that, use the section headings as
landing pads.

---

## 1. Introduction and non-goals

The hardware unit is one HVAC vent. A small XIAO ESP32-C6 board sits inside the
vent box. A hobby SG90 servo on the board's GPIO2 pin physically rotates the vent
louver between **90° (fully closed)** and **180° (fully open)**. The board exposes
itself on a Thread mesh as a Matter **Window Covering** device. Home Assistant
(HA) running in Docker on a Raspberry Pi is the user-facing controller and
automation engine.

A single Raspberry Pi can host an arbitrary number of vents — every additional
vent is one more ESP32-C6 board on the same Thread mesh, joined to the same Matter
fabric. There is no cloud dependency, no Wi-Fi on the device, no HTTPS/MQTT, no
controller other than HA.

**Non-goals** (deliberate, not deferred):

- **No Wi-Fi on the vent.** ESP32-C6 has a Wi-Fi radio, but we leave it
  uncompiled (`CONFIG_ESP_WIFI_ENABLED=n`). Co-existing Wi-Fi and 802.15.4 on the
  same radio caused interrupt-watchdog panics on our firmware. See §10.1.
- **No Google Home / Alexa / Apple Home support.** The Pi's OTBR is a third-party
  Thread border router. Google Nest fabric (and similar) only routes Matter
  traffic through their own first-party border routers. HA, however, talks
  directly to our OTBR; that's why the controller stack is HA-only.
- **No legacy CoAP/Python hub.** Earlier iterations of this project had a
  Python hub and a custom HA integration talking to vents over CoAP. Those
  were removed; the supported control plane is **only** Matter-over-Thread.

> See runbook §1 for the "I already have this set up, just give me the next
> flashing command" quick path.

---

## 2. System architecture at a glance

The system is three layers (UI, gateway, device) plus two radios (BLE for
commissioning, 802.15.4 for normal operation). Everything inside the Pi runs as a
Docker container with `--network host` so the containers share the Pi's IPv6
stack and BLE adapter directly.

```
        ┌───────────────────────────── Raspberry Pi (Linux host) ─────────────────────────────┐
        │                                                                                       │
        │  ┌──────────────────┐    WebSocket    ┌────────────────────────┐                      │
        │  │ Home Assistant   │ ──────────────► │   matter-server        │                      │
        │  │   (port 8123)    │  ws://...:5580  │ (python-matter-server) │                      │
        │  │ ─────────────    │ ◄────────────── │   (port 5580)          │                      │
        │  │ Matter integ.    │  notifications  └────────┬─────┬─────────┘                      │
        │  │ (HA WebSocket    │                          │     │                                │
        │  │  client of MS)   │                          │     │ BLE pairing                    │
        │  └──────────────────┘                          │     ▼ (commissioning only)           │
        │           ▲                                    │   BlueZ ── (host adapter, hci0) ── ▒ │
        │           │ user clicks                        │                                      │
        │           │ Close/Open                         │ Matter operational                   │
        │           │                                    │ (UDP over IPv6, port 5540)           │
        │           │                                    ▼                                      │
        │           │                            ┌─────────────────────┐                        │
        │           │                            │  OTBR container     │                        │
        │           │                            │  (openthread/otbr)  │                        │
        │           │                            │  /dev/ttyUSB0       │                        │
        │           │                            └─────────┬───────────┘                        │
        │           │                                      │ 802.15.4 (Thread) via SLZB-07      │
        └───────────┼──────────────────────────────────────┼───────────────────────────────────┘
                    │                                      │  ▲
                    │ HA UI / API in browser                BLE 2.4 GHz from host hci0 ─ ─ ─ ─ ─ ┐
                    │ on phone/laptop                      │  │                                  │
                                                           ▼  │                                  │
                                                  ┌───────────┴─────────────┐                    │
                                                  │   XIAO ESP32-C6 (vent)  │  ◄─────────────────┘
                                                  │   Rust firmware         │
                                                  │   esp-matter (C++)      │
                                                  │   OpenThread stack      │
                                                  │                         │
                                                  │   GPIO2 (D2) ──► SG90   │
                                                  │                  servo  │
                                                  └─────────────────────────┘
```

Two transport protocols matter here, on two different radios.

- **BLE (Bluetooth Low Energy)** is used **only during commissioning**. The
  ESP32-C6 advertises a Matter commissioning service over BLE; matter-server,
  using BlueZ on the Pi, connects to it, runs the Matter PASE/CASE handshake,
  and pushes the Thread network credentials to the device. After commissioning
  the device stops BLE advertising and never uses BLE again unless factory-reset.
- **802.15.4 / Thread** is the steady-state transport for everything else. The
  SLZB-07 dongle gives the Pi an 802.15.4 radio; the OTBR container drives it,
  bridges between the Thread mesh and the Pi's wlan0 IPv6 network, and forwards
  Matter UDP packets in both directions.

There is no other connectivity between the Pi and the vent. The vent does not
join your Wi-Fi network. The Pi's Wi-Fi (or wired Ethernet) only connects the
Pi itself to your LAN so you can reach HA from your phone/laptop.

> See runbook §3 for how to bring the three Pi containers up; runbook §5–§6 for
> how to flash and commission a vent.

---

## 3. The Raspberry Pi hub

The Pi runs three Docker containers, all in `--network host` mode:

| Container | Image | Role | Port |
|-----------|-------|------|------|
| `otbr` | `openthread/otbr:latest` | OpenThread Border Router. Drives the SLZB-07 radio, forms/joins the Thread mesh, bridges IPv6 between Thread and wlan0, runs the SRP server (see §5.6) | 80 (web GUI, optional) |
| `matter-server` | `ghcr.io/home-assistant-libs/python-matter-server:stable` | Matter controller. Holds the fabric credentials, NOC (Node Operational Certificate), ACLs. Talks Matter-over-IPv6 to commissioned devices. Exposes a WebSocket API for HA. Uses BlueZ for commissioning | 5580 (WS) |
| `homeassistant` | `ghcr.io/home-assistant/home-assistant:stable` | User-facing UI, automation engine, device registry. Its built-in **Matter (BETA)** integration is a WebSocket client of matter-server | 8123 (web) |

Using `--network host` is required for two reasons. First, OTBR has to assign and
route IPv6 prefixes on the host's actual interfaces; bridge networking would
isolate it. Second, Matter operational discovery uses mDNS over IPv6 link-local
multicast — that needs the host's real interface, not a docker0 bridge.

### 3.1 OTBR — OpenThread Border Router

OTBR has two jobs:

1. **Run the Thread network on the SLZB-07 radio.** The SLZB-07 is a "radio
   co-processor" (RCP) — a passive 802.15.4 transceiver with a serial protocol
   called Spinel. The dongle does the PHY/MAC; OTBR runs the entire Thread stack
   in software on the Pi and talks Spinel over `/dev/ttyUSB0` to the dongle.
   The dongle alone can't form a network.

2. **Bridge IPv6 between the Thread mesh and the Pi's wlan0.** A Thread mesh has
   its own IPv6 prefix (the **Mesh-Local ULA**, e.g. `fdf6:fb49:f2c1:1::/64`).
   For devices on wlan0 (matter-server, HA) to reach a Thread node, OTBR
   advertises an **Off-Mesh-Routable (OMR)** prefix into the Thread mesh, hands
   each mesh node an address from that prefix, and routes packets between
   mesh and wlan0. OMR addresses look like `fdbf:cc11:94a3:1e8c:…` on a typical
   setup. The "OMR" name is literally "addresses that are routable off the
   mesh" — i.e., reachable from the rest of the Pi.

OTBR exposes a CLI inside the container called **`ot-ctl`**. Useful commands:

- `docker exec otbr ot-ctl state` — `leader` / `router` / `child` / `disabled`.
  In a single-OTBR setup, the OTBR is always `leader`.
- `docker exec otbr ot-ctl child table` — list of end devices currently attached
  to this OTBR as their parent. Each row gives RLOC16 (short Thread address),
  age (seconds since last frame), RSSI, and Extended MAC (EUI-64). This is the
  canonical "is the vent on the mesh right now?" check. See §5.8.
- `docker exec otbr ot-ctl srp server host` and `ot-ctl srp server service` —
  what the OTBR's SRP server has stored for end devices that registered service
  records. See §5.6.
- `docker exec otbr ot-ctl dataset active -x` — dump the active Thread dataset
  (network key, channel, PAN ID, …) as a hex blob. The setup script backs this
  up to `~/.thread/dataset-backup.txt` for disaster recovery; if the OTBR
  container is wiped, restoring that blob recreates the same Thread network
  rather than forming a new one (which would orphan every commissioned vent).

OTBR needs two host-kernel modules loaded before it can route IPv6 properly:
`ip6table_filter` and `ip6_tables`. Without them, packets cross the mesh but
can't traverse OTBR's iptables rules into wlan0. Loading them is part of the
Pi setup (runbook §2.1).

### 3.2 matter-server — the Matter controller

`python-matter-server` is a small Python wrapper around the CHIP (Connected Home
over IP) SDK's controller library. It owns the **fabric** — the set of
commissioned devices that share trust roots — and the **NOC** (Node Operational
Certificate) that authenticates the controller to each device.

Once a device is commissioned, matter-server:

- Discovers it via mDNS (the device advertises `_matter._tcp.local`). See §5.5.
- Establishes a **CASE** (Certificate Authenticated Session Establishment)
  session — a TLS-like handshake over UDP that uses the fabric certificates.
- Subscribes to attribute reports so it sees state changes pushed by the device.
- Sends Invoke commands when HA or another client requests an action.

The WebSocket API on port 5580 lets HA (or any other client, like the Python
test scripts in `/tmp/` we used during commissioning sessions) read attributes,
invoke commands, and receive subscription pushes without speaking the Matter
wire protocol directly.

We deliberately run matter-server as a separate container rather than letting
HA Container's bundled matter-server handle it. The reasons are practical: it's
easier to debug (`docker logs matter-server`), easier to restart without
restarting HA, and the BLE permissions are scoped cleanly to one container.

matter-server gets the host BLE adapter via `-v /run/dbus:/run/dbus:ro` and the
`--bluetooth-adapter 0` flag (= `hci0`). That's the link to BlueZ; see §3.4.

### 3.3 Home Assistant — the user-facing controller

HA is what you actually use. The **Matter (BETA)** integration in HA does not
have its own Matter stack — it is a client of matter-server. You add it once,
pointing at `ws://localhost:5580/ws`, and from then on every commissioned
device shows up as one or more HA entities, with type derived from the device's
Matter cluster (a Window Covering becomes an HA `cover.*` entity).

For our vent, the entity exposes Open, Close, Stop, and a position slider.
"Open" sends Matter command `UpOrOpen`. "Close" sends `DownOrClose`. "Stop"
sends `StopMotion`. The slider sends `GoToLiftPercentage(value)`. Those
percentages are **percent100ths**: 0 = fully open, 10000 = fully closed. See
§4.4 for what the firmware does on the device side, and §7 for the full
command path.

> See runbook §3.3 for adding the Matter integration to HA. See runbook §7 for
> assigning the entity to a HA Area (room).

### 3.4 Host dependencies — BlueZ, kernel modules, USB layout

A few host-side details matter for reliability:

- **BlueZ** is the Linux Bluetooth daemon. It owns `hci0` (the Pi's onboard BT
  controller). matter-server speaks to BlueZ over D-Bus via the bind-mounted
  `/run/dbus` socket, and uses it to scan for and connect to commissioning
  advertisements. If BlueZ is unhappy — wedged connection, stale advertising
  cache — commissioning fails with `le-connection-abort-by-local` or silent
  timeouts. `sudo systemctl restart bluetooth` is the brute-force fix.
- **Kernel modules** `ip6table_filter` and `ip6_tables` need to be present;
  OTBR loads its iptables ruleset at startup and silently can't route without
  them. Persist via `/etc/modules-load.d/otbr.conf` (runbook §2.1).
- **USB layout** — both the XIAO and the SLZB-07 must plug into the Pi
  directly. A USB hub on the desk (we've identified a VIA Labs 2109:3431 +
  TI 0451:8442 chain that does this) will give the XIAO 5 V but no USB data,
  so it shows a power LED but no `/dev/ttyACM0`. Confirm with
  `lsusb -d 303a:` — the XIAO should appear as `Espressif USB JTAG/serial
  debug unit`. See runbook §5.1.

---

## 4. The ESP32-C6 vent controller

### 4.1 Hardware

The board is a **Seeed XIAO ESP32-C6** — a thumbnail-sized RISC-V module with
4 MB flash, 802.15.4 (for Thread) and BLE 5 (for commissioning) radios, and a
USB Type-C port wired to the chip's built-in USB Serial/JTAG.

Wiring:

| Function | Pin (XIAO label) | Pin (ESP32-C6 GPIO) | Wire | Notes |
|---------|------------------|---------------------|------|-------|
| Servo signal | D2 | GPIO2 | yellow / orange | LEDC PWM @ 50 Hz, 14-bit resolution |
| Servo power | 5V | — | red | SG90 prefers ~5 V; XIAO's 5V pin is USB Vbus passthrough |
| Servo ground | GND | — | brown / black | shared with XIAO ground |
| USB | Type-C connector | — | USB cable | Power + serial + flashing path |

The XIAO's onboard USB Serial/JTAG enumerates as `/dev/ttyACM0` (vendor:product
`303a:1001`, "Espressif USB JTAG/serial debug unit"). espflash uses the same
port — no separate UART adapter needed.

This is the USB-powered wiring. For a battery-powered build (4-cell NiMH pack,
no USB tether), see [battery-carrier-board.md](battery-carrier-board.md) for
the carrier PCB design, BOM, and firmware integration notes — it's a separate
power path, not a replacement for the wiring above.

The USB-hub gotcha is one of the more annoying ones in this project: the chain
provides power but not data. Always plug the XIAO directly into a Pi USB port.
`lsusb -d 303a:` will return blank if it's going through the hub.

### 4.2 Firmware stack

The firmware is a Rust binary that links against the entire ESP-IDF v5.2.3 C
SDK plus Espressif's `esp-matter` SDK (which itself wraps the CHIP SDK in C++).
Conceptually:

```
   ┌────────────────────────────────────────┐
   │ vent-controller (Rust)                 │  src/*.rs — our code
   │   main.rs, matter.rs, servo.rs,        │
   │   state.rs, identity.rs, power.rs      │
   ├────────────────────────────────────────┤
   │ esp_matter_bridge (C++)                │  components/esp_matter_bridge/
   │   matter_bridge.cpp                    │  thin C++ shim — our code
   ├────────────────────────────────────────┤
   │ esp-matter (Espressif)                 │  cluster definitions, attribute
   │                                        │  store, endpoint factories
   ├────────────────────────────────────────┤
   │ CHIP SDK (Matter, C++)                 │  protocol-level Matter
   │                                        │  (PASE/CASE, IM, mDNS, BLE GATT)
   ├────────────────────────────────────────┤
   │ ESP-IDF v5.2.3                         │  FreeRTOS, OpenThread, NimBLE,
   │   FreeRTOS / OpenThread / NimBLE       │  NVS, LWIP, LEDC, drivers
   ├────────────────────────────────────────┤
   │ ESP32-C6 silicon                       │  RISC-V, 802.15.4, BLE radio
   └────────────────────────────────────────┘
```

The C++ shim exists because esp-matter is heavily C++ (templates, classes,
overloaded operators) and bridging it to Rust through bindgen would be brittle.
Instead, the shim exposes a small **C** API in
`components/esp_matter_bridge/include/matter_bridge.h`:

```c
int  matter_bridge_init(matter_position_cb_t pos_cb,
                        matter_identify_cb_t id_cb,
                        void *ctx);
int  matter_bridge_start(void);
void matter_bridge_update_position(uint16_t percent100ths);
void matter_bridge_update_operational_status(uint8_t status);
bool matter_bridge_is_commissioned(void);
int  matter_bridge_get_pairing_code(char *buf, size_t len);
int  matter_bridge_get_qr_payload(char *buf, size_t len);
void matter_bridge_factory_reset(void);
```

The Rust side (`src/matter.rs`) declares these `extern "C"` and wraps them in
safe Rust functions. Inbound callbacks (position change, identify) get a `*mut
c_void` user context that we leave null; instead, the callbacks reach into our
global app state (`with_app_state(|s| …)`).

### 4.3 Source module tour

```
firmware/vent-controller/src/
├── main.rs       Boot orchestrator: init logging, NVS, identity, WAL recovery,
│                 LEDC PWM, Matter, CoAP (legacy), then enter main loop.
├── matter.rs     Rust ↔ matter_bridge FFI; servo-angle ↔ percent100ths math;
│                 callbacks from CHIP into Rust.
├── thread.rs     `ThreadManager` — small query layer over OpenThread state
│                 (used for /device/health reports).
├── servo.rs      `ServoDriver` over `LedcDriver`. 50 Hz PWM, 500–2500 µs pulse
│                 for 0°–180°, step delay 15 ms.
├── state.rs      `VentStateMachine` (current/target angle + step) and
│                 `AppState` (singleton accessed via `with_app_state`).
├── identity.rs   `DeviceIdentity` — reads EUI-64 from eFuse, writes/reads
│                 NVS keys for room/floor/name/power_mode + the angle WAL.
├── power.rs      `PowerManager` / `PowerMode` (AlwaysOn vs Sed). Currently
│                 always-on; SED is a stub for future battery operation.
└── coap.rs       Legacy CoAP resources (`/vent/position`, `/vent/target`,
                  `/device/{identity,config,health}`). Still compiled in but
                  not on the supported control path; ignore in normal use.
```

**Boot sequence** (see `main.rs`):

1. `esp_idf_svc::sys::link_patches()` and `esp_idf_logger::init()` — set up logging.
2. `Peripherals::take()` and `EspDefaultNvsPartition::take()` — claim hardware.
3. `DeviceIdentity::new()` — read EUI-64 from eFuse, open NVS namespace `vent_cfg`.
4. `is_first_boot()` — read NVS key `init`; if missing, mark first boot.
5. **WAL (Write-Ahead Log) recovery.** Read NVS keys `wal` (commit flag),
   `angle` (last committed angle), `target` (pending target). If `wal == 0`,
   the previous move was interrupted by power loss; restore checkpoint angle
   and queue the pending target as the new target so the move replays. See
   §4.6 for the WAL design.
6. Configure LEDC timer (50 Hz, 14-bit), create `LedcDriver` on GPIO2, wrap in
   `ServoDriver`, call `set_angle(initial_angle)` to push the servo to its
   last-known-good position.
7. Build the `VentStateMachine` at the restored angle. If there's a pending
   WAL target, call `set_target(pending)` so the main loop will move there.
8. `matter::init()` — calls `matter_bridge_init()`. This creates the Matter
   node, the Window Covering endpoint at endpoint id 1, registers attribute-
   and identify-update callbacks. Notably it does **not** yet register the
   delegate (see §4.4).
9. `matter::start()` — calls `matter_bridge_start()`. This configures the
   OpenThread platform (the SLZB-07 on the device side is replaced by the
   C6's built-in 802.15.4 radio, `RADIO_MODE_NATIVE`), then calls
   `esp_matter::start()` which boots the CHIP server, mDNS responder, BLE
   GATT advertiser, and OpenThread stack. **After** `esp_matter::start()`
   returns, the delegate is registered.
10. `matter::log_pairing_info()` — log the manual pairing code and the QR
    payload to serial. You read these to commission the device (runbook §6.1).
11. Build the `AppState` aggregate and stash it in the global slot via
    `register_coap_resources(app_state)` (despite the name, that call is the
    one that publishes `AppState` to the callbacks; the CoAP side effects are
    incidental on the Matter path).
12. Enter the main loop: while `vent.is_moving()`, `step()` (advance current
    angle by 1° toward target), `servo.set_angle(current)`, sleep
    `STEP_DELAY_MS` (15 ms). When the move completes, `identity.commit(final_angle)`
    and `matter::report_position(final_angle)` / `report_operational_status(false)`.

### 4.4 The Window Covering cluster

Matter models a window covering (or vent louver, or roller shade) using the
**Window Covering** cluster, ID `0x0102`. The cluster has six relevant
attributes for our use:

| Attribute | ID | Type | Meaning |
|-----------|----|------|---------|
| `Type` | 0x0000 | enum | What kind of covering — we use `Rollershade` |
| `CurrentPositionLiftPercent100ths` | 0x000E | u16 | Where the louver actually is, 0..10000 (0 = open) |
| `TargetPositionLiftPercent100ths` | 0x000B | u16 | Where we're moving to |
| `OperationalStatus` | 0x000A | bitmap | Bits for global/lift/tilt motion (opening/closing/stopped) |
| `ConfigStatus` | 0x0007 | bitmap | Reports cluster capabilities |
| `FeatureMap` | 0xFFFC | bitmap | Which Window Covering features are enabled |

And four commands:

| Command | ID | What it does |
|---------|----|--------------|
| `UpOrOpen` | 0x00 | Move to fully open (Target = 0) |
| `DownOrClose` | 0x01 | Move to fully closed (Target = 10000) |
| `StopMotion` | 0x02 | Halt; cluster sets Target = Current |
| `GoToLiftPercentage` | 0x05 | Set Target to a specific percent100ths |

The Window Covering cluster is **heavily feature-gated**. Three things must be
true at the same time for incoming commands to actually fire callbacks into our
firmware:

1. **A `WindowCovering::Delegate` must be registered.** The cluster server, on
   receiving any of the four commands, validates the command and then calls
   the delegate's `HandleMovement` (for Up/Down/GoTo) or `HandleStopMotion`
   (for Stop). Without a delegate, CHIP logs `WindowCovering has no delegate
   set for endpoint:1` and silently drops Up/Down/GoTo. Only Stop has a
   default no-op handler.
2. **The delegate must be registered AFTER `esp_matter::start()`** — not before.
   The cluster server gets initialized inside `esp_matter::start()`; calling
   `WindowCovering::SetDefaultDelegate()` earlier doesn't stick. Our code does
   the registration as the last step of `matter_bridge_start()`.
3. **The `PositionAwareLift` feature must be added to the cluster's
   FeatureMap.** The cluster has an internal `HasFeature(endpoint, kPositionAwareLift)`
   guard around setting Target and calling HandleMovement. Without it, commands
   arrive at the cluster but skip the delegate path. Our code adds the feature
   in `matter_bridge_init` (right after creating the endpoint) by calling
   `cluster::window_covering::feature::lift::add()` and `position_aware_lift::add()`.

Missing any one of those three produces the same observable symptom: HA's
Close button does nothing, no logs on the device, no errors. This was one of
the harder bugs to find. See runbook §10.7 for the diagnostic.

### 4.5 percent100ths ↔ servo angle, and why u32

The conversion between Matter's percent100ths (0..10000, where 0 = fully open)
and our servo angle (90..180, where 180 = fully open) is in `src/matter.rs`:

```rust
pub fn angle_to_percent100ths(angle: u8) -> u16 {
    let clamped = angle.clamp(ANGLE_CLOSED, ANGLE_OPEN);
    let range = (ANGLE_OPEN - ANGLE_CLOSED) as u32; // 90
    let from_open = (ANGLE_OPEN - clamped) as u32;
    ((from_open * 10000) / range) as u16
}

pub fn percent100ths_to_angle(pct: u16) -> u8 {
    let clamped = pct.min(10000) as u32;
    let range = (ANGLE_OPEN - ANGLE_CLOSED) as u32; // 90
    let from_open = (clamped * range) / 10000;
    ANGLE_OPEN - from_open as u8
}
```

The **u32 promotion** matters. An older version computed `(clamped * range) /
10000` in u16. For `percent100ths_to_angle(10000)`: `10000 * 90 = 900000`,
which wraps the u16 to `900000 % 65536 = 48032`. Divided by 10000 that gives
4. `180 − 4 = 176`. So pressing Close in HA moved the servo to 176° (almost
fully open) instead of 90° (fully closed). The bug was silent because the
unit tests in the same file never ran — `vent-controller` is a binary-only
crate, so `cargo test` errors with "no library targets found" and exits zero.

Rule of thumb for any future arithmetic in this code path: when multiplying
two values that can each reach a few thousand, cast to u32 first.

### 4.6 NVS and persistent state

ESP32 has a **Non-Volatile Storage (NVS)** partition — a small key/value store
on the SPI flash, log-structured and wear-leveled by the IDF NVS driver. Our
firmware uses NVS for everything that has to survive a reboot:

| Owner | Namespace / partition | What's stored |
|-------|----------------------|---------------|
| Our firmware | `vent_cfg` namespace | `room`, `floor`, `name`, `pwr_mode`, `poll_ms`, plus the WAL keys |
| Our firmware (WAL) | `vent_cfg` namespace | `angle` (last committed servo angle, 1 byte), `target` (pending target, 1 byte), `wal` (commit flag, 1 byte) |
| OpenThread | `nvs` partition (default) | Active dataset (network key, channel, PAN ID, ext PAN ID, …), node info, MLE counters |
| CHIP/Matter | `nvs` partition (default) | Fabric table (fabric ID, root cert, NOC, ICA, IPK), ACLs, group keys, mDNS instance name, subscription resumption records |
| ESP-IDF | `phy_init` partition | RF calibration data |

The partition layout is fixed by `partitions.csv`:

```
nvs       data nvs     0x9000  0x6000  (24 KB)
phy_init  data phy     0xf000  0x1000  (4 KB)
factory   app  factory 0x10000 0x300000 (3 MB)
```

The 24 KB NVS is shared among Matter, OpenThread, and our `vent_cfg`. That's
plenty.

**"Wiping NVS"** specifically means erasing this 24 KB partition. After a wipe
the device looks like a fresh-from-the-factory unit: no fabric credentials, no
Thread dataset, no servo checkpoint. It will boot, fail `is_commissioned()`,
start BLE advertising the matter commissioning service, and wait to be
commissioned again. The runbook calls for an NVS wipe in specific scenarios:

- **After a firmware reflash that changes the Matter datamodel.** If you add a
  new cluster or change feature gating, subscription resumption records from
  the old build can cause CHIP to crash or behave oddly. Wiping NVS clears
  them.
- **When the device is "commissioned but unreachable" for a long time.** If
  HA has the device in its registry but matter-server times out every
  re-subscribe attempt and there are no mDNS records being advertised, NVS
  state can be stale; wipe + re-commission is faster than debugging.
- **When you don't have the matter-server fabric anymore.** If the Pi got
  wiped and matter-server lost its fabric, the device still thinks it's
  commissioned but to a fabric nobody knows. Wipe → re-commission.

To wipe NVS without re-flashing the app, with the device in download mode:
`espflash erase-partition nvs`. See runbook §5.4.

**Write-Ahead Log (WAL) on the angle.** SG90 servos don't report position, so
when power is cut mid-move we need to know where the louver is when we wake
up. The strategy is in `identity.rs`:

- Before the servo starts moving, the firmware calls `write_ahead(target)`:
  set NVS `target = target`, set `wal = 0` (uncommitted).
- The servo moves. No NVS writes during the move.
- When `current == target`, the firmware calls `commit(target)`: set
  `angle = target`, set `wal = 1`.

On boot, if `wal == 1` (or unset), the previous move committed cleanly:
restore `angle`. If `wal == 0`, the previous move was interrupted: restore
`angle` (the last known-good position before the move) and **replay**
`target` (so the move completes after power restoration). The NVS keys are
**overwritten in place** — total flash wear is 4 small writes per command
cycle, well within the partition's effective lifetime (we estimate ~16 years
at 100 commands/day).

> See runbook §5.4 for the wipe command, §9.3 for re-pair-after-wipe.

---

## 5. Matter and Thread, end-to-end

This section explains the protocol stack from the bottom up: the 802.15.4
radio, the Thread mesh, IPv6 routing, mDNS, SRP, Matter commissioning, Matter
operational. If you already know the protocols, skim — most subsections are
focused on the **smart-vent-specific** details (what addresses are involved,
what commands to use, what the failure modes look like).

### 5.1 What Matter is

**Matter** (formerly Project CHIP) is an application-layer protocol that runs
on top of IPv6. It is *transport-agnostic*: a Matter node can sit on Wi-Fi
(Matter-over-Wi-Fi), Ethernet, or Thread (Matter-over-Thread, what we use).
The semantics are the same; only the link layer differs.

A Matter device exposes:

- One or more **endpoints** (logical components). Endpoint 0 is always the
  "root endpoint" hosting administrative clusters (Basic Information, Network
  Commissioning, Operational Credentials, etc.). Other endpoints are
  app-specific. Our vent has endpoint 1 = Window Covering.
- A set of **clusters** per endpoint. A cluster is a typed bundle of
  **attributes** (state), **commands** (actions), and **events** (signals
  from the device to the controller). Window Covering is one cluster; an
  endpoint can host many.
- A **fabric** membership. Every commissioned controller-device pair belongs
  to one or more fabrics. Each fabric has a root certificate, and each node
  on the fabric is issued a **NOC (Node Operational Certificate)** signed by
  that root.

Matter wire traffic during operation is UDP on port **5540**, encrypted under
session keys derived from the NOC and the controller's certificate via
**CASE (Certificate Authenticated Session Establishment)**. CASE looks much
like TLS 1.3 — it's an X.509-based, mutually-authenticated key exchange that
produces a per-session symmetric key.

The protocol layer above CASE is the **Interaction Model (IM)**, which
defines `ReadRequest`, `WriteRequest`, `InvokeRequest`, `SubscribeRequest`,
and their responses. When HA pushes the Open button, that's an
`InvokeRequest` carrying a Window Covering `UpOrOpen` command, traveling over
a CASE session, riding on a UDP packet, hopping through the Thread mesh.

### 5.2 What Thread is

**Thread** is a low-power IPv6 mesh network on IEEE 802.15.4 (the same PHY
that Zigbee uses, but with very different upper layers). A Thread network has:

- **Routers** (and one **Leader** elected from the routers). They route
  packets through the mesh and accept new attachments.
- **End devices** — children of a router. They don't route. There are three
  flavors: **REED** (router-eligible end device, can promote to router),
  **MED** (minimal end device, RX-on-when-idle, doesn't sleep), and
  **SED** (sleepy end device, polls parent, sleeps between polls). Our vent
  is configured as MTD = "minimal Thread device" which presents as MED.

Every Thread node has at least three IPv6 addresses:

- A **link-local address** (`fe80::…`) used for MLE (mesh link establishment)
  and one-hop neighbor traffic.
- A **mesh-local ULA** in the Thread mesh-local prefix (e.g.,
  `fdf6:fb49:f2c1:1::/64`) used for routing inside the mesh.
- One or more **OMR (Off-Mesh-Routable)** addresses, derived from the OMR
  prefix the OTBR delegates. These are how off-mesh hosts (matter-server,
  HA) reach the device.

The OTBR is a Thread router (specifically a **Border Router**). Off-mesh
traffic gets to the device via:
`matter-server (on wlan0) → wlan0 (Pi) → OTBR netfilter rules →
wpan0 (OTBR's Thread NIC) → Thread mesh → vent`.

The vent's **EUI-64** (extended MAC) is its permanent identifier on Thread.
On ESP32-C6 it's burned into eFuse at the factory. Our firmware reads it
with `esp_efuse_mac_get_default()` (see `identity.rs:read_eui64`) and uses
it both for logging and as the IEEE 802.15.4 extended address.

### 5.3 What a Thread Border Router actually does

A Thread Border Router (TBR) sits with one foot in the Thread mesh and one
foot on a "backbone" network (Wi-Fi or Ethernet). It does five things:

1. **Joins the Thread mesh as a router.** OTBR participates in the routing
   protocol like any other router.
2. **Advertises an OMR prefix** into the mesh. Devices on the mesh learn
   they can reach the rest of the world via this prefix. They configure an
   OMR address using SLAAC and announce it.
3. **Routes IPv6 packets between the mesh and the backbone.** Forward
   path: backbone → OTBR → Thread mesh. Reverse path: mesh → OTBR →
   backbone. The OTBR's netfilter ruleset handles NAT66/forwarding details.
4. **Reflects mDNS between the two sides.** The Thread mesh has its own
   multicast group; mDNS announcements from a Thread node have to be
   re-emitted on wlan0 to reach controllers there. OTBR does this via its
   SRP server (see §5.6) plus its mDNS proxy.
5. **Runs the SRP server.** End devices push their service records to OTBR
   over the mesh; OTBR re-advertises them via Avahi on the backbone.

When `ot-ctl state` reports `leader`, OTBR is also the network leader, which
adds the responsibility of generating the routing locator (RLOC16) and
network-wide configuration. In a single-OTBR setup the leader role is
unremarkable.

### 5.4 The Thread Dataset and credential push

A Thread network is identified by its **Active Operational Dataset**: a
binary structure containing the **network key** (the symmetric key for all
802.15.4 MAC-layer encryption), **channel** (e.g. 15), **PAN ID** (16-bit
network ID), **extended PAN ID** (64-bit), **mesh-local prefix**, **security
policy**, and a timestamp. Any device with this dataset can join the network.

Two relevant facts:

- The dataset is the secret. If you compromise it, you can sniff all Thread
  traffic in that network.
- A device that doesn't have the dataset cannot communicate on the mesh at
  all (not even to MLE-discover its parent).

**Credential push** during commissioning is the moment when matter-server
takes the active dataset from OTBR (via `ot-ctl dataset active -x`) and
sends it to the device over the BLE PASE session. The device stores the
dataset in NVS (under the OpenThread partition keys), attaches to the mesh,
and from then on it's a regular Thread end device. We never send the dataset
over Wi-Fi or any unsecured link — it always travels inside the encrypted
PASE channel.

If you wipe the device's NVS, the dataset is gone with it. The device will
boot, find no dataset, advertise BLE for re-commissioning.

### 5.5 mDNS and `avahi-browse`

**mDNS** (Multicast DNS) is the discovery protocol Matter uses on the local
link. Devices advertise records under `_matter._tcp.local` for operational
(commissioned) services and `_matterc._udp.local` for commissioning
(pre-fabric) services. The records contain:

- The Matter operational name (a 16-byte hex tag: 8-byte Compressed Fabric
  ID + 8-byte Node ID, hyphenated), e.g. `9C7219E1805D505D-000000000000000E`.
- An A/AAAA record giving the device's IPv6 address.
- TXT records with capabilities, retry intervals, etc.

When matter-server wants to talk to a commissioned device, it doesn't have
the device's IP cached — it does `_matter._tcp.local PTR` lookups, finds
the record, resolves the AAAA, and opens a CASE session. Subscriptions
re-resolve when they renew (every 30–60 s).

You can inspect the mDNS records the Pi sees with `avahi-browse`:

```
avahi-browse -art _matter._tcp _matterc._udp
```

This lists every record currently advertised on any interface. If the vent
has registered its `_matter._tcp` record (via SRP, see next section), it'll
appear here with its IPv6 address. If it doesn't, mDNS-based discovery
won't work — that's the "device looks alive but matter-server can't reach
it" failure mode.

### 5.6 SRP server and service registration

A Thread device cannot directly emit mDNS multicast on the Wi-Fi/Ethernet
side — it's on the Thread mesh, the multicast scope is different. The
**Service Registration Protocol (SRP)** solves this. SRP is, conceptually,
"DNS UPDATE over UDP, sent from a Thread end device to the OTBR." The OTBR
runs an SRP server; end devices use the OpenThread SRP client.

Workflow:

1. The CHIP mDNS responder on the device decides it wants to advertise
   `_matter._tcp._fabric=01_node=0E.local`.
2. The OpenThread SRP client packages that record as an SRP update message.
3. The message is sent over the mesh to the SRP server (running inside
   OTBR; configured via the active dataset).
4. OTBR's SRP server accepts the update, stores the record under the
   device's host name, and re-emits it as a regular mDNS record on wlan0
   via Avahi.
5. matter-server, listening on wlan0, sees the record and learns the
   device's address.

You can list what the SRP server currently holds with:

```
docker exec otbr ot-ctl srp server host
docker exec otbr ot-ctl srp server service
```

`host` shows the registered host names + IPv6 addresses (one host per
device). `service` shows the service instances under those hosts. Empty
output means no end device has currently registered — either the device
isn't on the mesh, or its CHIP mDNS responder isn't trying, or the SRP
update is failing.

**SRP registration drops** are a known instability with our firmware. The
CHIP mDNS responder advertises at startup, then re-advertises on a
schedule. If the responder hits a transient OpenThread packet-queue-full
condition during the re-advertise (which it has, during heavy MLE traffic),
the SRP record can expire on the server without being renewed. Symptom:
`ot-ctl srp server host` goes from "shows the device" to "empty" while the
device is still on the mesh (you can see its child entry in
`ot-ctl child table`). matter-server then loses operational reachability
even though the device is fine. Power-cycling the device usually restores
the SRP record within a minute (because boot triggers a fresh advertise).

### 5.7 OMR IPv6

The **Off-Mesh-Routable (OMR)** address is the address an off-mesh host
uses to reach a Thread device. OTBR advertises an OMR prefix into the mesh
(typically a /64 like `fdbf:cc11:94a3:1e8c::/64`). Thread devices auto-
configure an OMR address from this prefix using SLAAC: prefix + 64 bits
derived from the device's MAC.

Three useful operations:

- **Find a device's OMR addresses**: in the device's serial log on boot,
  it logs every IPv6 address it gets; alternatively, use matter-server's
  `ping_node` API which returns all known addresses for a node id and
  whether each currently pings (we used this several times during
  debugging — see the python scripts under `/tmp/` from previous sessions
  if you need a template).
- **Ping an OMR address from the Pi**: `ping6 -c 3 <omr-address>`. This
  proves IPv6 reachability without involving Matter / CASE / mDNS at all.
- **Direct-IP commissioning**: matter-server can be handed an explicit
  IPv6 address to commission against, bypassing mDNS entirely. Useful
  when SRP isn't working (see §6.5).

### 5.8 The OTBR child table

`docker exec otbr ot-ctl child table` is the canonical "is the device on
Thread right now?" check. Sample output:

```
| ID  | RLOC16 | Timeout | Age | LQ In | C_VN |R|D|N|Ver|CSL|QMsgCnt|Suprvsn| Extended MAC     |
+-----+--------+---------+-----+-------+------+-+-+-+---+---+-------+-------+------------------+
|   1 | 0x3801 |     240 |  34 |     3 |  199 |1|0|0|  4| 0 |     0 |   129 | 366c8ec439fa22b1 |
```

- **ID** — short local id used by OTBR for this child.
- **RLOC16** — 16-bit routing locator; the child's short Thread address.
- **Timeout** — seconds the parent waits before evicting; default 240.
- **Age** — seconds since the parent last heard a frame from this child.
  Low (<30 s for MED) means the device is currently active.
- **Extended MAC** — the child's 8-byte EUI-64. This is the **device-side
  EUI**, equal to what `esp_efuse_mac_get_default()` returns. It's how you
  correlate the child entry with a specific vent.

If the device is on Thread you'll see a row. If not — the row is missing
or "Age" climbs toward 240 — the device is either powered off, out of
range, or has lost its Thread credentials.

### 5.9 "Device on Thread" — the operational checklist

"Is the vent on Thread?" decomposes into four checks, top to bottom:

1. **Is it powered and running?** Serial log emits new lines.
2. **Has it joined the mesh?** `ot-ctl child table` shows a row whose
   Extended MAC matches the vent's EUI-64, with low Age.
3. **Has it advertised SRP?** `ot-ctl srp server host` lists a host whose
   name contains the device's CHIP fabric/node tag, and `srp server
   service` lists a `_matter._tcp` instance for that host.
4. **Is matter-server seeing it via mDNS?** `avahi-browse -art _matter._tcp`
   shows the same instance. matter-server logs show
   `Re-Subscription succeeded` or equivalent.

If 1–3 are green but 4 is red, the issue is on the Pi side (Avahi, OTBR's
mDNS proxy, matter-server). If 3 is red but 2 is green, the device's CHIP
mDNS / SRP layer is stuck — power-cycle the device. If 2 is red but 1 is
green, the device hasn't joined — check the Thread credentials (was it
commissioned to a different network?). If 1 is red, plug it in.

> Runbook §6.3 has these as copy-paste verification commands.

---

## 6. Commissioning deep dive

Commissioning is the multi-step handshake that turns an out-of-the-box
ESP32-C6 into a member of your Matter fabric on your Thread mesh. It's
also where most of the time-consuming failures happen. This section
explains what's happening so the symptom-driven recipes in the runbook
make sense.

### 6.1 BLE commissioning

A fresh device (no NVS commissioning state) wakes up, fails
`matter_bridge_is_commissioned()`, and starts the NimBLE GATT server
advertising a Matter commissioning service. The advertisement contains:

- Vendor ID and Product ID (we use `0xFFF1` / `0x8001` — Matter test
  vendor/product, fine for a private hub).
- **Discriminator** — a 12-bit number used to disambiguate multiple
  devices advertising at once. Our firmware derives it from the lower
  12 bits of `EUI-64[6..8]`, so it's unique per board without manual
  config.
- **Passcode**-derived data (a SPAKE2+ verifier) used in PASE.

matter-server, via BlueZ, scans for advertisements, recognizes the
Matter service UUID, and connects. It then runs **PASE (Passcode
Authenticated Session Establishment)** with the device using the
manual pairing code or QR payload you provided. The pairing code
contains the discriminator (so matter-server knows which advertisement
to talk to) and the SPAKE2+ passcode.

After PASE succeeds, both sides share a session key. Over that key
matter-server:

1. Sends the **Operational Credentials** cluster commands to issue
   the device its NOC (Node Operational Certificate) and the fabric
   root cert.
2. Sends the **Network Commissioning** cluster commands carrying the
   **Thread dataset** (network key, channel, PAN ID, etc., gathered
   from OTBR via `ot-ctl dataset active -x`).
3. Tells the device to **CommissioningComplete**, which closes PASE.

The device now stores its NOC + fabric cert + thread dataset in NVS,
brings up OpenThread with the dataset, attaches to the mesh, and
starts the CHIP mDNS responder.

Symptoms of BLE failures and what they mean:

- **`le-connection-abort-by-local` in matter-server logs.** BlueZ-side
  hiccup. Restart `bluetooth.service`, retry.
- **No advertisements seen at all.** Either the device's BLE adv
  window has expired (next subsection), or the host's BlueZ adapter is
  in scan-blocked state. Power-cycle the device first; if that doesn't
  help, restart `bluetooth.service`.
- **Advertisements seen, connect fails or hangs.** Could be an old
  cached pairing in BlueZ's bookkeeping. `bluetoothctl > remove
  <addr>` for the device's BLE address, retry.

### 6.2 Fast-adv vs slow-adv windows

The CHIP SDK doesn't BLE-advertise forever — that would be a battery
drain on real battery devices, and on USB-powered devices it pollutes
the air for everyone. The pattern is:

- **Fast advertising window**: roughly **15 minutes** after the device
  boots into commissioning mode (i.e., uncommissioned, fresh boot or
  factory-reset). During this window the BLE adv interval is short
  (~30 ms typical), and matter-server picks the device up promptly.
- **Slow advertising**: after the fast window, the device keeps
  advertising at a much longer interval (~1 s) for some hours.
  Discoverable but slower to find.
- **Off**: eventually, no advertising. The device is sitting there
  waiting for a manual prod.

This is why **the practical commissioning workflow is: flash → boot →
commission within ~10 minutes**. If you flash a board, then go make
coffee, then forget about it for an hour, then come back and try to
commission, you might still succeed (slow-adv), or you might find
matter-server timing out and need to **power-cycle the device first**
to restart the fast-adv window.

This is also why the runbook §5 emphasizes "have HA's Matter UI ready
on your phone before you replug the device."

### 6.3 Thread credential push, in detail

Inside the PASE channel, matter-server sends a sequence of cluster
commands. The relevant ones for getting the device onto Thread:

1. **NetworkCommissioning::ScanNetworks** (optional) — ask the device
   to scan for networks. For Thread, this returns the channels it's
   listening on, but it's not required if matter-server already knows
   which dataset to push.
2. **NetworkCommissioning::AddOrUpdateThreadNetwork** — payload is the
   active dataset (the same hex blob you'd get from `ot-ctl dataset
   active -x`). The device stores it in NVS but doesn't activate yet.
3. **NetworkCommissioning::ConnectNetwork** — the device activates
   the dataset, calls `otThreadSetEnabled(true)`, and reports back
   over PASE whether it joined.
4. **Once the device confirms attached**, matter-server proceeds to
   the operational handoff: PASE closes, device starts CHIP mDNS,
   matter-server discovers via mDNS and opens CASE.

If you see in the serial log:

```
chip[NWPROV]: Setting Thread provision
chip[DL]: OpenThread started: OK
chip[DL]: Setting OpenThread device type to MINIMAL END DEVICE
```

…you're past step 2.

### 6.4 mDNS-based operational discovery

After PASE closes, the device is a regular commissioned node. matter-server
needs to find it again via mDNS to open the operational CASE session.

Two ways this can work:

- **Via SRP + Avahi (the normal path).** Device → SRP client → OTBR's SRP
  server → Avahi → wlan0 mDNS → matter-server. This is the "happy path"
  and is what runbook §6.3 verifies.
- **Via the device's own mDNS responder on the mesh-local prefix**, which
  OTBR's mDNS proxy then bridges to wlan0. This is a fallback when SRP
  fails for whatever reason; it's less reliable.

When mDNS discovery succeeds, matter-server logs:

```
<Node:14> Discovered on mDNS
<Node:14> Setting-up node...
<Node:14> Establishing CASE session...
<Node:14> Re-Subscription succeeded
```

### 6.5 Direct IP commissioning (bypassing mDNS)

When SRP isn't registering and mDNS-based discovery times out, you can
bypass mDNS entirely by handing matter-server an explicit IPv6 address —
typically the device's OMR address.

There are two flavors:

- **Initial commissioning over IP.** Less common; only used if the
  device is already on the Thread mesh from a previous commissioning
  attempt but the BLE-based path keeps failing. matter-server's
  `commission_with_code` command accepts an `ip_addr` parameter; pass
  the OMR address along with the setup code.
- **Operational reachability after losing mDNS.** Once the device is
  commissioned, matter-server caches the address from the last
  successful discovery. If you query a node attribute and the cached
  address is stale, matter-server returns
  `AddressResolve_DefaultImpl.cpp:124: Timeout`. There isn't a clean
  way to inject a new address via the public API — you have to either
  wait for the device to re-advertise (power-cycle it), or wipe
  matter-server's storage and re-commission.

Direct-IP commissioning is the escape valve; SRP-driven mDNS is the
normal flow. If you find yourself reaching for direct IP often, the
device's SRP responder needs fixing, not a workaround.

### 6.6 Post-flash behavior

What happens immediately after `espflash` finishes depends on what was
in NVS when you flashed:

- **NVS preserved (the default, no `erase-partition` flag).** The
  device boots with whatever state it had: if it was commissioned to a
  fabric, it's still commissioned; if it had a checkpoint angle, that
  angle is restored; if there was a pending WAL move, it replays.
  No BLE advertising unless the device fails to attach to its old
  Thread network. This is the **fast path** for iterating on firmware
  without losing commissioning state.
- **NVS wiped (`espflash erase-partition nvs`).** First boot, no fabric,
  no dataset. BLE fast-adv starts. The device is ready for a fresh
  commission via HA. Use this when you've changed Matter cluster
  configuration, when the device is stuck in some bad state, or when
  you want to commission to a different fabric.

> Runbook §5.4 documents when to wipe; §6 covers re-commissioning after
> a wipe.

---

## 7. Anatomy of a "Close vent" command

A single click on HA's Close button traverses about eight layers. The
trace below is what actually happens — verified end-to-end on hardware.
Each step references the layer / module involved.

**0. User clicks Close in HA.**

The user has the vent's cover entity open in the HA UI. They tap the
down-arrows-converging icon ("close cover"). HA's frontend issues a
`cover.close_cover` service call to the entity.

**1. HA cover platform → HA Matter integration.**

The entity is implemented by HA's built-in `matter` integration. The
`async_close_cover()` method on the cover entity translates the service
call into a Matter command invocation: cluster `0x0102` (Window Covering),
command `0x01` (`DownOrClose`), endpoint `1`, no payload.

**2. HA Matter integration → matter-server WebSocket.**

The integration runs as a WebSocket client of matter-server. It sends a
JSON-RPC-style message over `ws://localhost:5580/ws`:

```json
{"message_id": "...", "command": "device_command",
 "args": {"node_id": 14, "endpoint_id": 1, "cluster_id": 258,
          "command_name": "DownOrClose", "payload": {}}}
```

(`258` = `0x102`.) matter-server's `client_handler` receives it.

**3. matter-server → CHIP SDK → CASE session.**

matter-server resolves the node's operational name to an IPv6 address
via cached mDNS (if cached, immediate; otherwise re-query). It locates
the existing CASE session in its session table; if absent or expired,
it opens a new one. CASE re-establishment takes ~1 s (a SIGMA1/SIGMA2/
SIGMA3 round trip) and involves NOC validation on both sides.

**4. UDP encrypted packet → wlan0 → OTBR → Thread mesh.**

The CHIP SDK wraps the InvokeRequest in IM framing, signs+encrypts under
the CASE session key, and emits a UDP/IPv6 packet to the device's
**operational IPv6 address** (typically OMR, sometimes mesh-local
link-local with %ot1 scope) on port 5540. The packet leaves matter-
server, hits wlan0, gets forwarded by the Pi's kernel into OTBR's
wpan0 (per OTBR's iptables rules), and OTBR puts it on the Thread mesh
addressed to the device's RLOC16.

**5. Device receives → CHIP IM dispatcher → cluster server.**

On the C6, the OpenThread stack delivers the packet to lwIP's UDP
listener on port 5540, which is the CHIP server's socket. The CHIP
secure channel decrypts under the session key, the IM dispatcher
identifies it as an `InvokeRequest` for endpoint 1 / cluster 0x102 /
command 0x01, and routes it to the Window Covering cluster server.

You'll see in the serial log:

```
chip[ZCL]: DownOrClose command received
```

**6. Cluster server → delegate → our `on_position_change` Rust callback.**

The cluster server validates the command, checks `HasFeature(endpoint,
kPositionAwareLift)` (it does — we added it in `matter_bridge_init`),
sets `TargetPositionLiftPercent100ths = 10000`, fires our attribute
update callback (`app_attribute_update_cb` in `matter_bridge.cpp`)
which forwards to `s_position_cb` (Rust's `on_position_change` in
`matter.rs`), and then calls the delegate's `HandleMovement`.

You'll see:

```
matter_bridge: Matter: target position set to 10000/10000
matter_bridge: Delegate: move to 10000/10000
Matter: position change -> 90° (pct100ths=10000)
```

`on_position_change`:

1. Converts 10000 → 90° via `percent100ths_to_angle` (the u32-promoted
   version — §4.5).
2. Calls `with_app_state(|s| ...)` to take the global state lock.
3. Persists the intent via `s.identity.write_ahead(90)` — NVS writes
   `target=90, wal=0`. WAL is now uncommitted.
4. Calls `s.vent.set_target(90)`, which updates the state machine's
   target. Returns the previous angle.
5. Releases the lock.

**7. Main loop steps the servo.**

The main loop in `main.rs` polls `vent.is_moving()` each iteration.
After step 6, that's true (current=180, target=90). For each step it:

1. Calls `vent.step()` which decrements current by 1.
2. Calls `servo.set_angle(current)`, which converts the angle to a
   pulse width (500 + angle * (2500-500) / 180 µs), converts that to
   an LEDC duty value, and writes it to the LEDC peripheral. The PWM
   output on GPIO2 updates within microseconds.
3. Sleeps 15 ms (`STEP_DELAY_MS`).

So a full open-to-close traverse (180° → 90°, 90 steps) takes
~90 × 15 ms = 1.35 s. The servo's mechanical inertia and 50 Hz update
rate smooth that into a continuous motion.

When `current == target`:

1. The main loop calls `identity.commit(90)` — NVS writes `angle=90,
   wal=1`. WAL committed.
2. Logs `Vent reached target: 90° (closed) — committed`.
3. Calls `matter::report_position(90)`, which converts back to
   percent100ths (10000) and calls `matter_bridge_update_position(10000)`.
4. Calls `matter::report_operational_status(false)`, which sets the
   `OperationalStatus` attribute to 0 (stopped).

**8. Attribute reports flow back to HA.**

`matter_bridge_update_position` calls `attribute::update(...)` on the
CurrentPositionLiftPercent100ths attribute. esp-matter publishes the
change to all subscribers. matter-server is subscribed (subscription
established post-commissioning, renewed every 60 s); CHIP IM emits a
`ReportData` message over the existing CASE session back to matter-
server. matter-server publishes the change over the WebSocket to HA.
HA updates the entity state to "closed" and any listening automations
fire.

End-to-end latency in the happy case: ~150 ms from HA click to first
PWM update, plus ~1.3 s mechanical traverse, plus ~50 ms for the
ReportData round trip to HA's UI. The click feels responsive even
though there's a Thread mesh and Matter handshake in the middle.

---

## 8. What happens when you unplug the ESP32

This is one of the questions you'll ask most often during dev. The
answer depends on three things: whether the device is commissioned,
whether the BLE fast-adv window is fresh, and whether matter-server
has a current cached address.

**Phase A — unplug (immediate).**

Power dies. PWM stops. The servo holds position via mechanical
friction (SG90s have no brake; they'll stay where they are barring
external force on the louver). All RAM state is lost. Nothing in NVS
is corrupted because we use NVS in a transactional way — partial
writes are atomic at the NVS-page level.

If a move was in progress, the WAL flag is `0` (we set it to 0 *before*
the move starts). On next boot, the firmware will detect that and
replay the move.

OpenThread on the OTBR side notices the child going silent. The
child's age increases. After 240 s the child entry times out and the
device is dropped from the mesh.

matter-server, on its next subscription poll (every ~60 s), gets a
retransmission failure: `Msg Retransmission to <Node>: failure (max
retries:4)`. After ~30 s it marks the node Unavailable. HA reflects
that in the UI within a few seconds.

**Phase B — replug (ROM, second-stage bootloader).**

The XIAO powers up. The ESP32-C6 ROM bootloader looks at the
strapping pins (BOOT is high = normal flash boot) and loads the
second-stage bootloader at flash offset 0x1000. The second-stage
bootloader picks the factory app partition (per `partitions.csv`),
loads the app at 0x10000, and jumps to it.

This is also where the **espflash bootloader gotcha** matters: if the
bootloader on flash is a different IDF version than the app, the
second-stage bootloader rejects the app with `Segment 0 load address
... doesn't match data` and resets (`rst:0x3 LP_SW_HPSYS`). See
runbook §10.1.

**Phase C — IDF/FreeRTOS init.**

Standard ESP-IDF boot. PSRAM (none here), heap, FreeRTOS scheduler,
NVS partition init.

**Phase D — our app starts.**

`main()` (in `main.rs`) runs the boot sequence from §4.3. Around
3–5 s after replug:

1. Identity init, NVS open, EUI-64 read.
2. WAL recovery: if `wal == 0`, replay; otherwise restore.
3. Servo init, set to checkpoint angle. The servo moves to its
   recorded position (with a quick 100–500 ms jerk to it; this is
   visible if the louver had been jostled while unpowered).
4. Matter init: creates the Window Covering endpoint, adds Lift +
   PositionAwareLift features, registers attribute callbacks.
5. Matter start: configures OpenThread (RADIO_MODE_NATIVE on the
   C6's internal 802.15.4), starts `esp_matter::start()` which
   boots the CHIP server, OpenThread stack, mDNS responder, BLE
   GATT advertiser. **Window Covering delegate is registered here.**

**Phase E — re-attach to Thread (commissioned device).**

If the device has a saved Thread dataset (commissioned previously),
OpenThread reads it from NVS and calls `otThreadSetEnabled(true)`.
The MLE stack starts:

1. Send Parent Request, listen for Parent Responses.
2. OTBR replies. The C6 sends Child ID Request, OTBR replies with
   Child ID Response. The device is now attached.
3. OpenThread assigns mesh-local + OMR addresses.

In the OTBR's `ot-ctl child table` you'll see the device's row
within ~5–15 s. RSSI populates, age reads 0–10.

**Phase F — SRP registration.**

CHIP's mDNS responder enumerates the services it wants to advertise:

- `_matter._tcp.local` for operational (since the device is
  commissioned to a fabric).

It hands the records to the OpenThread SRP client, which sends an
SRP update to the OTBR's SRP server. On success, `ot-ctl srp server
host` lists the device, and `ot-ctl srp server service` lists the
`_matter._tcp` instance. From there OTBR proxies to Avahi, and
matter-server sees the mDNS record.

This step **sometimes fails** for a few minutes after a fresh boot
(see §5.6, SRP registration drops). If it does, you'll see the device
in `child table` but not in `srp server host`, and matter-server
keeps showing "Unavailable". Either wait, or power-cycle again to
trigger a fresh advertise.

**Phase G — matter-server reconnects.**

When mDNS resolves, matter-server triggers a re-subscribe. CASE
session is re-established (~1 s, since the session table held the
NOC), and subscriptions resume. HA flips the entity from Unavailable
to its current state. Total time from replug to "controllable in HA":
typically 30–90 s with a healthy SRP; can be 2–5 min with SRP
flakiness.

**Phase E' — uncommissioned device.**

If the device's NVS has no Thread dataset (fresh flash + NVS wipe, or
out-of-the-box), Phase E doesn't run. Instead, BLE NimBLE starts
advertising the Matter commissioning service in fast-adv mode for
~15 minutes. The device is now waiting for HA to commission it.

> Runbook §5.5 lists the expected serial log markers in order so you
> can confirm each phase. §9.3 covers replug behavior post-NVS-wipe.

---

## 9. Scaling to many vents

The architecture is built for N vents. Adding a vent is a repeatable
procedure (runbook §5–7). A few design points worth understanding
before you scale:

### 9.1 One fabric, N devices

There's exactly one Matter fabric in this setup: the fabric
matter-server created the first time it was initialized. Every vent
gets commissioned **into that fabric**. The fabric's root certificate
authority is matter-server itself; the NOC issued to each device is
signed by matter-server's CA cert. If matter-server's storage is
wiped, the fabric is gone and **every device** has to be re-commissioned.

This is why `~/matter-server/` is bind-mounted into the container —
the fabric state persists across container restarts and Pi reboots
because it lives on the host filesystem.

A device can in principle join multiple fabrics (multi-admin) — for
example, one fabric for HA, another for Apple Home — but we explicitly
don't pursue that. See §10.2.

### 9.2 Naming and per-device identity

Each device has three identifiers that matter at different layers:

- **EUI-64 (8-byte MAC).** Read from eFuse via
  `esp_efuse_mac_get_default()`. Unique per chip, set at manufacture.
  Used as the IEEE 802.15.4 extended address. Visible in
  `ot-ctl child table` under "Extended MAC". This is the physical
  identity of the board.
- **Discriminator + passcode (commissioning).** The discriminator is
  the lower 12 bits of `EUI-64[6..8]` (derived in `matter_bridge_init`).
  The passcode is currently fixed in firmware to the SDK default
  (this is fine for a private home network — anyone in BLE range can
  attempt a SPAKE2+ handshake, but they need physical access to the
  device anyway). For a stricter setup, generate per-device passcodes
  and bake them into a per-device factory partition.
- **Node ID (within the fabric).** Assigned by matter-server when
  commissioning. Monotonically incremented (so node 1, 2, 3, …; we
  see node 14 in our current deployment because the dev fabric has
  some test entries). Used by matter-server in all subsequent
  references.

For HA users, the most useful identifier is the device's **name**,
which is set inside HA after commissioning. The runbook §7 walks
through naming + room assignment.

### 9.3 HA Areas, Floors, and group control

HA's organizational model is **Floors → Areas → Devices**:

- **Areas** are rooms ("Living Room", "Study"). Every device can be
  assigned to one Area.
- **Floors** (HA 2024.3+) group Areas. Each Area can belong to one
  Floor ("Main Floor", "Basement").
- **Devices** roll up through both — a vent's `cover.*` entity
  inherits its Area, and the Floor of that Area.

All of this is HA-side metadata; the firmware doesn't know or care
about rooms. Each device is an independent Matter endpoint; HA
orchestrates.

For multi-vent control, HA's standard `cover.*` services accept a
`target.area_id`, `target.floor_id`, or `target.entity_id`. That is
enough to express every grouping the user wants:

- Whole house: `target.entity_id: all` on the cover domain.
- One floor: `target.floor_id: main_floor`.
- One room: `target.area_id: study`.
- Specific vents: `target.entity_id: [cover.study_vent_1, cover.study_vent_2]`.

Scheduling is **Automations** (time triggers) plus **Schedule
helpers** (weekly calendar windows whose state changes trigger
automations).

Templates for scripts, automations, schedule helpers, and a Lovelace
dashboard ship in the repo at `homeassistant/`; the runbook §7.5
walks through installing them in the live HA config.

> Why no device-side grouping? The Matter spec actually has a
> Groups cluster (cluster ID 0x0004) for binding endpoints into
> group-cast targets. We don't use it. It's intended for direct
> device-to-device control without a controller in the loop (e.g. a
> wall switch talking to a group of lights). With HA always in the
> loop and orchestrating, controller-side grouping is strictly
> simpler — one source of truth, editable in the UI, no firmware
> rebuilds when the layout changes.

### 9.4 Mesh capacity and topology

Thread spec allows up to **32 routers** and a few hundred end devices
per network. Practical limit on our setup is much lower — the OTBR
handles all routing through itself (we have no auxiliary routers on
the mesh), so every packet hop goes via OTBR. RF range from the C6 to
the SLZB-07 dongle is the binding constraint.

For a single-floor home, one OTBR is plenty (we've seen 10+ Thread
devices on one OTBR with no trouble). If you scale to multiple floors
and start seeing high RSSI loss, the right move is to add a second
ESP32-C6 firmware variant configured as a **Thread Router** (FTD),
which will mesh-route packets to/from end devices in its vicinity.
That's out of scope for now.

### 9.5 Provisioning N devices efficiently

The runbook's "Add the next vent" loop (§8) is short because each
device is independent. With practice:

- Build firmware once (~22 minutes for a clean release build on the
  Pi).
- Flash takes ~10 s per device with the bootloader cached.
- Commission via HA takes 30–60 s once you have the QR/code.
- Room assignment is a few clicks.

So adding a vent is ~2 minutes of operator time. Most of the elapsed
time is the boot/BLE-adv/SRP cycle (~30–90 s) you wait for.

---

## 10. Known limitations and design constraints

### 10.1 Wi-Fi is disabled — and why

`CONFIG_ESP_WIFI_ENABLED=n` is set in `sdkconfig.defaults`. This
removes the ESP-WIFI driver from the build entirely (~150 KB heap
savings as a bonus).

We disabled it because, on ESP32-C6, Wi-Fi and 802.15.4 share the
same radio. With Wi-Fi enabled, the PHY-coex layer disables interrupts
for >300 ms during init/calibration. During Thread MLE re-attach
bursts (or heavy mDNS), this regularly tripped the **interrupt
watchdog timer**, panicking with:

```
Core 0 panic'ed (Interrupt wdt timeout on CPU0).
rst:0x7 (TG0_WDT_HPSYS)
```

The device would crash-loop every 30–200 seconds. Setting
`CONFIG_CHIP_DEVICE_CONFIG_ENABLE_WIFI_STATION=n` alone wasn't enough
— the ESP-WIFI driver was still compiled and calling PHY init.
Removing the driver entirely solved it.

We also raised `CONFIG_ESP_INT_WDT_TIMEOUT_MS` from 300 to 1000 as a
safety margin for the (much shorter, now-non-Wi-Fi) ISRs that still
exist.

If you ever need Wi-Fi on the device (e.g., for an OTA path that
doesn't go over Thread), you'll have to revisit the coex configuration
carefully.

### 10.2 No Google / Apple ecosystem support

The Pi's OTBR is a third-party Thread border router. Google, Apple,
and (currently) Amazon use a "preferred fabric / preferred border
router" model in which their controllers will only route Matter
traffic via border routers they recognize as belonging to their
ecosystem. Google specifically: Nest Hub (2nd gen), Nest Hub Max,
Nest Mini (2nd gen), Nest Wifi Pro. Google's controllers will see
the vent's Matter advertisement but refuse to commission it onto a
non-Google fabric routed via a non-Google border router.

HA, on the other hand, talks directly to our OTBR via matter-server.
It has no such restriction, which is why we target HA.

To support Google: you'd need to add a Google-branded Thread border
router and let it form the Thread network (replacing OTBR), then
commission the vents into Google's fabric. Out of scope here.

### 10.3 BlueZ reliability

BlueZ has rough edges around repeated commissioning sessions. Common
failure modes:

- Stale connection state after a failed commissioning leaves the next
  attempt with `le-connection-abort-by-local`.
- The Pi's onboard BT chip occasionally locks up after a power
  transient.
- `bluetoothctl` can show a paired device that no longer responds.

Restart `bluetoothd` (`sudo systemctl restart bluetooth`) when
anything BLE-related looks off. It's the most effective single
remedy. Runbook §10.4.

### 10.4 SRP registration drops

As documented in §5.6: the CHIP mDNS / OpenThread SRP path on our
firmware will occasionally fail to renew its SRP registration. When
that happens, the device is on the mesh but appears unreachable to
matter-server. Power-cycling the device usually restores the
advertisement within a minute.

The root cause is heavy MLE traffic colliding with mDNS re-advertise
in the OpenThread packet queue. We've mitigated it by disabling Wi-Fi
(removing one source of radio contention) and bumping the task
watchdog. The remaining drops are tolerable for a small mesh; if it
becomes a real annoyance at scale, the fix is in CHIP's mDNS responder
(retry on queue-full).

### 10.5 The USB-hub data trap

A specific USB hub on the dev desk (VIA Labs 2109:3431 paired with
TI 0451:8442) gives the XIAO 5 V but no USB data. Symptom: the XIAO's
power LED is on, but `lsusb -d 303a:` returns nothing and
`/dev/ttyACM0` doesn't exist. The XIAO **must** plug directly into
the Pi. Other hubs might work; this specific chain doesn't.

### 10.6 Bootloader version mismatch

`espflash flash` without `--bootloader` flashes its own bundled
bootloader (currently from ESP-IDF v5.5.1-838), which is incompatible
with our IDF v5.2.3-built app. Result: sub-100 ms boot loop with
`rst:0x3 (LP_SW_HPSYS)` and the device unreachable. Always pass
`--bootloader target/.../out/build/bootloader/bootloader.bin`. See
runbook §5.3 / §10.1 for the command and the fix.

### 10.7 The reflash ritual

The XIAO's USB Serial/JTAG, while running our Matter+Thread firmware,
doesn't reliably respond to espflash's soft-reset signals (RTS/DTR).
So every reflash needs:

1. Hold the BOOT button.
2. Briefly unplug + replug USB (or press the RESET button while
   holding BOOT).
3. Release BOOT.

This puts the chip into ROM-level download mode where espflash can
talk to the ROM USB driver directly. Runbook §5.2.

---

End of handbook. For "how do I do this in commands," go to
**[runbook.md](runbook.md)**.
