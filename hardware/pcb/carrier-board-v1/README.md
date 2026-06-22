# Battery carrier board — v1 assets

Generated assets for the NiMH battery carrier PCB. See
[`docs/battery-carrier-board.md`](../../../docs/battery-carrier-board.md) for
the design writeup, BOM, layout rules, and current status (schematic/netlist
stage — not yet routed).

| File | What it is |
|---|---|
| `smart_vent_board.py` | Circuit as code (SKiDL). Source of truth — edit this, re-run, re-import. `python3 smart_vent_board.py` regenerates `smart_vent.net`. Requires `pip install skidl`. |
| `smart_vent.net` | KiCad netlist generated from the script above. Import via Pcbnew → File → Import → Netlist. |
| `smart_vent_floorplan.svg` | Placement plan diagram (component zones, power-loop routing, ground star point). |
| `place_smart_vent.py` | Run from KiCad's Pcbnew scripting console (after netlist import + footprint assignment) to auto-place all footprints per the floorplan, draw the 45×34 mm board outline, and add mounting holes. |
| `smart_vent_bench_sheet.pdf` | One-page printable BOM + assembly order + smoke test, for the bench. |
| `firmware-reference/power_indicator.rs` | Reference Rust module (power-gated servo, battery sense, status LED) — not yet integrated into `firmware/vent-controller`. |
