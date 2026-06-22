# Battery carrier board — v1 assets

Generated assets for the NiMH battery carrier PCB. See
[`docs/battery-carrier-board.md`](../../../docs/battery-carrier-board.md) for
the design writeup, BOM, layout rules, and current status (schematic
validated, footprint placement collision-checked and fixed, routing not
yet done).

**Two variants**: the status LED is optional (see the doc's §2a for the
tradeoff — locate/status feedback vs. a small continuous idle draw on the
3V3 rail plus a tighter placement). Both are generated from the same
`smart_vent_board.py`; pick whichever matches your build.

| File | What it is |
|---|---|
| `smart_vent_board.py` | Circuit as code (SKiDL). Source of truth — edit this, re-run, re-import. `python3 smart_vent_board.py` regenerates `smart_vent.net` (with LED); `SMART_VENT_LED=0 python3 smart_vent_board.py` regenerates `smart_vent_no_led.net` (without). Requires `pip install skidl`. |
| `smart_vent.net` | KiCad netlist, with-LED variant. Import via Pcbnew → File → Import → Netlist. |
| `smart_vent_no_led.net` | KiCad netlist, no-LED variant. |
| `smart_vent_floorplan.svg` | Original placement *concept* diagram (component zones, power-loop routing, ground star point). The zoning (left=signal, right=power, bottom=connectors) is still accurate; the exact part positions drawn here are not — they predate fitting real footprint sizes and were superseded by the collision-free coordinates in `kicad-project/` and `place_smart_vent.py`. Treat this SVG as illustrating the *idea*, not the final layout. |
| `place_smart_vent.py` | Run from KiCad's Pcbnew scripting console (after netlist import + footprint assignment) to auto-place all footprints per the floorplan, draw the 45×34 mm board outline, and add mounting holes. Works for either variant — it skips refs that aren't present (D1/R7/C5 on the no-LED import). |
| `smart_vent_bench_sheet.pdf` | One-page printable BOM + assembly order + smoke test, for the with-LED bench build. |
| `firmware-reference/power_indicator.rs` | Mirror of `firmware/vent-controller/src/carrier_board.rs` — the real module now lives in the crate (behind the `battery-carrier-board`/`led-indicator` Cargo features) and is the source of truth; this copy is kept for browsing without cloning the firmware build. Verified building on `riscv32imac-esp-espidf` against the crate's pinned `esp-idf-hal`; not yet called from `main()` or flashed (see #47). |
| `kicad-project/` | Placement-checked `.kicad_pcb` (zero shorts/overlaps/clearance violations, not yet routed) + `.kicad_pro` projects + DRC reports + the `nudge_apart.py` solver, for both variants — see its own README. |
