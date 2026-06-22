# Battery carrier board (NiMH) — design notes

> **Status: schematic/netlist validated, board not yet routed.** This document
> covers an alternative power path for a vent: running off a 4-cell NiMH pack
> instead of USB, via a small carrier PCB. The circuit (parts, values, nets) is
> done and machine-verified; physical layout/routing/Gerbers are not. See
> [Current state](#current-state) for exactly what exists and what's left.

This is a variant of the wiring in [handbook.md §3](handbook.md) (XIAO +
SG90 over USB power). Use this doc instead of the handbook's wiring table when
building a battery-powered vent.

## 1. Why a carrier board, and why NiMH

The target battery is a 4.8 V, 2-cell-pack-of-2 (4-cell) **NiMH** RC pack,
1000 mAh, with an SM-2P plug. Two things made a custom PCB worth it over
hand-wiring:

- The XIAO ESP32-C6's onboard charge controller only charges a single-cell
  3.7 V **LiPo** on its `B+`/`B-` pads (4.2 V CC/CV termination). Feeding a
  4.8 V NiMH pack into those pads charges the wrong chemistry at the wrong
  voltage — **never wire this pack to `B+`/`B-`.** Also, per Seeed's docs,
  the `5V` pin carries no voltage when running off `B+`/`B-`, so that path
  can't power the servo either.
- NiMH in-circuit charging needs a real smart-charger IC (MAX712/713,
  LTC4060, BQ2002-class) with −ΔV/dT-dt/timer termination — not a $1
  TP4056-style part. Ready-made modules for this are rare and bulky.

Given the pack already ships with a swappable SM-2P plug, the pragmatic
design is: **charge externally on a NiMH/RC charger, make the pack
removable, and let the board do power distribution + battery monitoring
only.** No charge circuit on the board — that's what keeps it a trivial
2-layer job.

The NiMH voltage range (5.6 V fresh → 4.0 V empty) is actually a *better*
match for the SG90 servo (happy 4.0–6.0 V) than the LiPo path the handbook's
USB wiring implies — the servo runs directly off the battery rail, no boost
converter needed.

## 2. Power architecture

```
        SM-2P                 ┌───── SK6812 LED  (status + identify)
VBAT ──┤ in ├── master sw ──┬┴── XIAO 5V pin ── onboard LDO ── 3V3 ─→ C6 + LED Vdd
       └─────┘              │
                             ├── 2M/1M divider ──→ A1 (GPIO1)   [pack voltage sense]
                             │
                             └── P-FET (high-side) ──→ SG90 VCC  [gated by GPIO]
                                     ▲
                              2N7002 level-shift ← GPIO21 (servo_en)

GND ── common (star point at battery return)
GPIO2 ──────────────────────────────→ SG90 signal
```

Three decisions that depart from the handbook's USB wiring and from Seeed's
own reference design:

1. **A plain SPST master switch on VBAT, not a power-mux IC.** A
   freshly-charged "4.8 V" NiMH pack actually sits around 5.6 V — above USB's
   5 V and at the edge of most auto-switch ICs' (TPS2113/LTC4412) comfortable
   range. A slide switch in the VBAT line sidesteps that entirely: off to
   flash over USB (battery fully isolated), on to deploy. Zero quiescent loss,
   no edge cases.
2. **A 1:3 sense divider, not 1:2.** Seeed's reference divider assumes a
   4.2 V LiPo max (→2.1 V at the ADC). This pack hits 5.6 V, and the C6 ADC's
   linear range tops out around ~2.45 V. A 1:2 divider would clip at full
   charge; 2 MΩ (top) / 1 MΩ (bottom) keeps both ends (5.6 V→1.87 V,
   4.0 V→1.33 V) inside the linear range, at ~1.9 µA drain.
3. **The servo is power-gated**, not left continuously powered. This is the
   single biggest battery-life lever: an SG90 idles at ~10 mA, which alone
   would drain the 1000 mAh pack in ~4 days. A high-side P-FET (driven through
   a 2N7002 so the 3.3 V GPIO gets a full gate swing) cuts servo power to
   ~0 mA between moves; it only draws during the ~0.5 s travel. Combined with
   an on-demand LED and a tuned Thread SED poll period, expected runtime goes
   from days to roughly 2–3 weeks per charge.

If your louver back-drives under its own weight (i.e. it doesn't hold
position by friction alone once power is cut), leave `servo_en` asserted
instead — one line of firmware, at the cost of ~10 mA continuous draw.

## 3. Connection map

| XIAO pin | GPIO | Net | Purpose |
|---|---|---|---|
| 5V | VBUS | VBAT (via master switch) | board power in |
| 3V3 | — | V3V3 | SK6812 Vdd |
| GND | — | common / star ground | |
| D2 | GPIO2 | SERVO_SIG | servo signal (existing — same pin the handbook's USB build uses) |
| D1 / A1 | GPIO1 | VBAT_SENSE | divider tap, pack voltage sense |
| D3 | GPIO21 | SERVO_EN | → 2N7002 gate (via 1k) |
| D4 | GPIO22 | LED_DIN | → SK6812 data (via 470Ω) |

GPIO2 matches the existing firmware's servo pin
(`firmware/vent-controller/src/main.rs`); GPIO1/21/22 are unused by the
current build, so this slots in without conflicts.

## 4. Bill of materials

| Ref | Value / part | Footprint | Note |
|---|---|---|---|
| U1 | XIAO ESP32-C6 | Seeed XIAO module, 14-pin | socketed (female headers), not soldered down; **verify pad order against the official Seeed footprint before routing** |
| J1 | SM-2P battery header | JST-SH-compatible 2-pin | battery in |
| J2 | 1×3 pin header, 2.54 mm | — | SG90: SIG · VCC · GND |
| SW1 | SPST slide switch, ≥1 A | — | master power |
| Q1 | AO3401A (P-MOSFET, −30 V) | SOT-23 | servo high-side gate; **verify G/S/D = 1/2/3 against the datasheet** |
| Q2 | 2N7002 (N-MOSFET) | SOT-23 | gate level-shift; same pinout caveat |
| R1, R3 | 100 kΩ ×2 | R_0603 | P-FET gate pullup / N-FET gate pulldown |
| R2 | 1 kΩ | R_0603 | GPIO → N-FET gate series |
| R4 | 2 MΩ | R_0603 | divider top |
| R5 | 1 MΩ | R_0603 | divider bottom (1:3 → A1) |
| R6 | 330 Ω | R_0603 | servo signal series |
| R7 | 470 Ω | R_0603 | LED data series |
| C1, C3, C5 | 100 nF ×3, X7R | C_0603 | sense tap / servo decouple / LED decouple |
| C2 | 470 µF, 10 V, electrolytic (polarized) | CP_Elec_6.3×5.4 | servo bulk cap — mount physically at J2, not at the XIAO |
| C4 | 10 µF, X5R | C_0805 | VBAT bulk |
| D1 | SK6812 RGB LED (5050), **not WS2812B** | SK6812 PLCC4 | locate + battery-state indicator; WS2812B's logic threshold is marginal at 3.3 V, SK6812 is reliable; **verify VDD/DOUT/GND/DIN = 1/2/3/4** |
| — | 2× 1×7 female header, 2.54 mm | — | XIAO socket |
| — | 2× M2.5 screws + standoffs | Ø2.7 mm cutouts | mounting |
| ext | NiMH 4.8 V 1000 mAh pack (SM-2P) + SG90 | — | not on board |

The three "verify" callouts above are the only things that need eyes before
routing — a wrong pin order on any of them silently miswires the board.

## 5. Board layout rules

The board is 45×34 mm, 2-layer, 1.6 mm. Floorplan: analog/signal cluster on
the left (near the XIAO's D1–D4 pins), high-current power cluster on the
right (near 5V/GND), servo connector on the bottom edge, LED in the corner
facing outward (so "find this vent" is visible through the enclosure). See
`hardware/pcb/carrier-board-v1/smart_vent_floorplan.svg` for the diagram.

Five rules that matter more than exact placement:

1. **Keep the servo loop short and fat.** The path battery+ → SW1 → Q1
   (source→drain) → C2 → servo VCC, and back via GND to the star point, is
   the only place real current flows (SG90 stall ≈ 650 mA plus inrush into
   C2). Use 0.8–1.0 mm traces here; everything else can be thin (0.25 mm).
2. **Single star ground at the battery negative.** Route the servo's GND
   return and the divider/LED GND back as separate runs that meet only at
   the star point. If they share copper, servo current spikes corrupt the
   ADC reads.
3. **Keep the sense node compact and quiet.** R4/R5/C1 and the GPIO1 tap
   should sit as a tight cluster over solid ground pour, physically away
   from Q1/C2.
4. **C2 belongs at the servo connector, not near the XIAO.** That's what
   absorbs the SG90's stall-current spike before it sags the rail and
   browns out the C6.
5. **Keep the USB edge and the master switch accessible** — USB-C for
   flashing, the switch reachable without opening the vent enclosure.

Layer plan: parts + signal on top, one uninterrupted GND pour on the
bottom, stitched with vias. Don't let a top-layer trace cut a slot through
the bottom pour under the sense node. Net classes: Power (VBAT, VBAT_RAW,
SERVO_VCC, GND) at 0.9 mm track / 0.6-0.3 mm via; Default (signals) at
0.25 mm track / 0.5-0.3 mm via.

## 6. Fab settings (JLCPCB)

- Layers: 2 · Dimensions: 45×34 mm (from Edge.Cuts) · Thickness: 1.6 mm
- Gerbers: `F.Cu`, `B.Cu`, `F.SilkS`/`B.SilkS`, `F.Mask`/`B.Mask`,
  `Edge.Cuts` — "Protel filename extensions" off
- Drill: Excellon, single file, PTH+NPTH merged
- Surface finish: HASL (free, sufficient — no need for ENIG on this board)
- JLCPCB's defaults (min trace/space 0.127 mm, min hole 0.3 mm, min annular
  ring 0.13 mm) are well inside this design's margins
- Assembly is optional and probably not worth it: ~13 small passives plus 2
  SOT-23s hand-solder faster than dealing with JLCPCB's part-library
  matching for a one-off. Only the XIAO headers and the SM-2P connector are
  through-hole regardless.

## 7. Assembly order and smoke test

Assembly order: flattest SMD passives first (R1–R7, C1, C3, C4, C5) → SOT-23s
(Q1, Q2 — double-check G/S/D) → D1 (watch corner orientation) → C2
electrolytic (stripe = −) → through-hole parts (J1, J2, SW1) → solder the two
female headers → socket the XIAO last (don't solder it down).

Before powering with the XIAO socketed, with just the bare board + battery:

1. DMM check: no short VBAT↔GND.
2. Pack on, SW1 on → 5V pad reads 4.0–5.6 V; servo-VCC pad reads ≈0 V
   (P-FET off by default — confirms the gate pulldown is working).
3. Insert XIAO → 3V3 pad reads 3.3 V.
4. Flash firmware → expect an identify blink, one servo move, one battery
   read.

A full one-page version of this (with the BOM table) is at
`hardware/pcb/carrier-board-v1/smart_vent_bench_sheet.pdf` — print it for the
bench.

## 8. Firmware integration

`hardware/pcb/carrier-board-v1/firmware-reference/power_indicator.rs` is a
**reference implementation**, not yet wired into `vent-controller`. It adds
three pieces, written against `esp-idf-hal` ~0.44/0.45 (matching the
firmware crate's current `0.45` pin in `Cargo.toml`):

- `servo` — replaces a bare PWM write with power-gated moves: energize VCC,
  settle 50 ms, command position, wait out travel, cut VCC. Drop the final
  `power_off()` call if the louver back-drives.
- `battery` — reads the 1:3 divider on GPIO1/A1, maps pack voltage to
  `Good`/`Ok`/`Low`/`Critical`. Thresholds stop at ~4.0 V (1.0 V/cell) to
  avoid cell reversal. NiMH's flat discharge curve makes this a coarse
  "roughly where am I" gauge, not a percentage fuel gauge — a coulomb
  counter would be the honest upgrade if more precision is needed later.
- `indicator` — drives the SK6812 as a small priority-ordered event
  dispatcher, since one LED ends up doing several jobs once more than one
  vent is installed:
  1. **Identify** — "find this vent," the primary use case. Blue blink,
     triggered from the app via the `/device/identity` handler (or the
     Matter Identify cluster). Always wins over the other events below —
     it's the one a person is actively looking at the hardware for.
  2. **Install** — pairing/commissioning feedback (`AwaitingCommission`,
     `Pairing`, `Commissioned`, `Error`). Only relevant pre-deployment, so
     it's allowed to be more liberal about on-time than the runtime events.
  3. **CommandResult** — a brief green/red blink confirming a command
     landed on *this* physical vent, useful for telling several vents
     apart while operating them from the app.
  4. **Battery** — the existing battery-state colour, shown after a move
     or an explicit query, not continuously.

  Nothing is ever left lit continuously regardless of event — that's the
  on-demand LED budget from §2. See the `Event`/`InstallState` enums in
  `indicator.rs` for the full state list.

Two spots are flagged `// VERSION:` in the file because the relevant crate
APIs (the ADC oneshot config, and `Ws2812Esp32Rmt::new`'s signature) have
churned across `esp-idf-hal`/`ws2812-esp32-rmt-driver` versions — confirm
against whatever version is pinned in `Cargo.lock` before integrating. It
also requires adding `smart_leds` and `ws2812-esp32-rmt-driver` as
dependencies, which are not currently in `firmware/vent-controller/Cargo.toml`.

The module compiles against the logic described above but has not been
built or flashed — treat it as a starting point, not drop-in code.

## 9. Current state

What's done and machine-verified:

- **Circuit topology** — captured as a SKiDL script
  (`smart_vent_board.py`), 19 parts / 13 nets, re-running it regenerates a
  byte-identical netlist (modulo random tags/timestamps), 0 errors.
- **Connectivity** — manually audited net-by-net: GND collects all returns,
  VBAT correctly feeds the 5V pin / P-FET source / divider / pullup, the
  gate chain is right, the sense divider lands on GPIO1.
- **KiCad netlist** (`smart_vent.net`) — importable into Pcbnew via
  File → Import → Netlist.
- **Floorplan** (`smart_vent_floorplan.svg`) — a placement plan, not yet
  applied to a real board file.
- **Placement script** (`place_smart_vent.py`) — a `pcbnew` scripting-console
  script that, run inside an actual KiCad PCB editor session after netlist
  import, positions all 19 footprints per the floorplan and draws the board
  outline + mounting holes. Written against the KiCad 7/8/9 API; not run
  against a live board in this pass (no `pcbnew` outside the KiCad GUI).

Since the first pass at this doc, a placement-verified (but unrouted)
`.kicad_pcb` has been generated against KiCad 10.0.4 and machine-checked —
see `hardware/pcb/carrier-board-v1/kicad-project/`. That run confirmed two
of the three footprint pinouts flagged below against real stock-library
parts (SOT-23 pad geometry and the SK6812 PLCC4 pad order both match what
the netlist assumed), and surfaced findings the original sketch couldn't
catch:

- **No KiCad stock footprint exists for the Seeed XIAO module, the
  hobby-RC "SM-2P" battery connector, or the exact `CP_Elec_6.3x5.4` cap
  footprint.** All three need sourcing (or a substitute part) before
  routing — see the placeholder table in
  `kicad-project/README.md`.
- **The floorplan coordinates are too tight at real footprint sizes.**
  DRC found 3 actual copper-to-copper shorts and 8 courtyard overlaps
  around the LED/servo-cap cluster (D1/C2/C3/C5/R7) and a few other pairs
  (R1/R2, SW1/J1, Q1/Q2) — the floorplan's left/right/bottom *zoning* is
  still correct, the exact coordinates just need spreading apart. Full
  details in `kicad-project/drc_report.json`.
- **The Gerber/drill export pipeline is confirmed working** against this
  unrouted board — the JLCPCB-compatible layer set in §6 plots correctly.

What's still **not** done — this is placement-verified, not fab-ready:

- No routing. Trace widths and the five layout rules (§5) are specified
  but not laid out on copper.
- No final DRC pass (the one in `kicad-project/drc_report.json` is against
  the unrouted placeholder placement, not a routed board).
- The XIAO pad-order pinout still needs confirming once a real footprint is
  sourced (it's the one of the three "verify" callouts in §4 that couldn't
  be checked against a stock part).

Follow-up work is tracked as GitHub issues (footprint sourcing, placement
re-spacing + routing, firmware integration of `power_indicator.rs`).

Next concrete step: open
`hardware/pcb/carrier-board-v1/kicad-project/smart_vent_v1.kicad_pcb` in
KiCad, source/swap in the three missing footprints, spread out the
overlapping parts per the DRC report, route to the rules in §5, run DRC
again, then plot Gerbers per §6.
