# Battery carrier board — v1 assets

Generated assets for the NiMH battery carrier PCB. See
[`docs/battery-carrier-board.md`](../../../docs/battery-carrier-board.md) for
the design writeup, BOM, layout rules, and current status (schematic/netlist
stage — not yet routed).

**Two variants**: the status LED is optional (see the doc's §2a for the
tradeoff — locate/status feedback vs. a small continuous idle draw on the
3V3 rail plus a tighter placement). Both are generated from the same
`smart_vent_board.py`; pick whichever matches your build.

| File | What it is |
|---|---|
| `smart_vent_board.py` | Circuit as code (SKiDL). Source of truth — edit this, re-run, re-import. `python3 smart_vent_board.py` regenerates `smart_vent.net` (with LED); `SMART_VENT_LED=0 python3 smart_vent_board.py` regenerates `smart_vent_no_led.net` (without). Requires `pip install skidl`. |
| `smart_vent.net` | KiCad netlist, with-LED variant. Import via Pcbnew → File → Import → Netlist. |
| `smart_vent_no_led.net` | KiCad netlist, no-LED variant. |
| `smart_vent_floorplan.svg` | Placement plan diagram (component zones, power-loop routing, ground star point) — drawn for the with-LED variant; the no-LED variant just leaves the LED corner empty. |
| `place_smart_vent.py` | Run from KiCad's Pcbnew scripting console (after netlist import + footprint assignment) to auto-place all footprints per the floorplan, draw the 45×34 mm board outline, and add mounting holes. Works for either variant — it skips refs that aren't present (D1/R7/C5 on the no-LED import). |
| `smart_vent_bench_sheet.pdf` | One-page printable BOM + assembly order + smoke test, for the with-LED bench build. |
| `firmware-reference/power_indicator.rs` | Reference Rust module (power-gated servo, battery sense, status LED) — not yet integrated into `firmware/vent-controller`. The `indicator` module only applies if you're building the with-LED variant; `servo`/`battery` apply either way. |
| `kicad-project/` | Placement-checked `.kicad_pcb` + DRC reports for both variants — see its own README. |
