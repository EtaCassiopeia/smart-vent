#!/usr/bin/env python3
"""
Auto-place the smart-vent carrier board to the floorplan.

HOW TO RUN (KiCad 7 / 8 / 9):
  1. Create the PCB, then Pcbnew -> File -> Import -> Netlist -> smart_vent.net
     (every footprint lands on top of each other at the origin)
  2. Assign footprints first if you haven't (esp. the official Seeed XIAO fp).
  3. Pcbnew -> Tools -> Scripting Console, then:
         exec(open('/path/to/place_smart_vent.py').read())
     Or set BOARD_PATH below and run it standalone with kicad-cli's python.

It positions parts by reference, draws a 45 x 34 mm Edge.Cuts outline, and adds
two M2.5 mounting holes as board cutouts.

These coordinates are the resolved, collision-free placement (see
kicad-project/nudge_apart.py and kicad-project/README.md for how they were
derived -- DRC against the original floorplan sketch found real shorts and
courtyard overlaps once real footprint sizes were dropped in; this is the
fix, not the original sketch). Re-running DRC after this script should come
back clean except for cosmetic silkscreen-text overlap.

The status LED (D1/R7/C5) is optional (see smart_vent_board.py /
docs/battery-carrier-board.md). If you imported smart_vent_no_led.net, those
three refs won't exist on the board — this script warns and skips them, which
is expected, not an error. (If you're on the no-LED netlist, the no-LED
variant's coordinates for SW1/Q1/Q2/R1/R2/R3/C2/C3 differ slightly from
this script's -- it uses the with-LED solve throughout; see
kicad-project/build_board.py's PLACE dicts if you want the exact per-variant
numbers instead.)

Coordinates are board-relative mm (origin = top-left of the outline), offset onto
the page by (ORIGIN_X, ORIGIN_Y). Y increases downward, matching the floorplan.
"""

import pcbnew

BOARD_PATH = ""          # leave "" to use the currently-open board
ORIGIN_X, ORIGIN_Y = 30.0, 30.0   # where the board's top-left sits on the page (mm)
BOARD_W, BOARD_H = 45.0, 34.0

# ref -> (x_mm, y_mm, rotation_deg)   [board-relative]
PLACE = {
    "U1":  (22.5, 11.5,   0),   # XIAO ESP32-C6, USB toward top edge

    # --- power cluster (right) ---
    "J1":  (36.49, 5.0,    0),   # SM-2P battery  (rotate so opening faces the edge)
    "SW1": (41.28, 12.91, 90),   # master slide switch -- rotated: unrotated it's
                                  # 10.37mm wide and sticks off the board's right edge
    "C4":  (32.67, 6.0,    0),   # 10uF VBAT bulk
    "Q1":  (37.82, 16.32,  0),   # P-FET servo high-side
    "Q2":  (42.02, 18.0,   0),   # 2N7002 gate level-shift
    "R1":  (34.82, 15.27, 90),   # 100k P-FET gate pullup
    "R2":  (33.01, 16.78, 90),   # 1k gate series
    "R3":  (42.12, 21.74,  0),   # 100k gate pulldown
    "C2":  (32.82, 22.86,  0),   # 470uF servo bulk  (keep hard against J2)
    "C3":  (43.23, 24.33, 90),   # 100n servo decouple

    # --- signal / analog cluster (left) ---
    "R6":  ( 6.0,  9.0,  90),   # 330R servo signal series
    "R4":  ( 4.0, 18.0,  90),   # 2M divider top
    "R5":  ( 4.0, 21.0,  90),   # 1M divider bottom
    "C1":  ( 7.5, 19.5,  90),   # 100n sense tap

    # --- connectors / LED (bottom) ---
    "J2":  (28.0, 27.5,   0),   # SG90 servo header -- shifted from directly under
                                 # U1 (whose placeholder footprint is an oddly tall,
                                 # unrepresentative shape, see kicad-project/README.md)
                                 # and up from the original anchor, whose last pad
                                 # otherwise landed past the board's bottom edge
    "D1":  (35.27, 30.2,   0),  # SK6812 — face OUT of the enclosure
    "R7":  (30.71, 29.68, 90),  # 470R LED data series
    "C5":  (39.93, 26.73, 90),  # 100n LED decouple
}

# M2.5 mounting holes (board-relative center mm), unplated cutouts
HOLES = [(3.0, 3.0), (42.0, 31.0)]
HOLE_R = 1.35  # ~2.7mm dia clearance for an M2.5 screw


def vec(x_mm, y_mm):
    return pcbnew.VECTOR2I(pcbnew.FromMM(ORIGIN_X + x_mm),
                           pcbnew.FromMM(ORIGIN_Y + y_mm))


def place(board):
    missing = []
    for ref, (x, y, rot) in PLACE.items():
        fp = board.FindFootprintByReference(ref)
        if fp is None:
            missing.append(ref)
            continue
        fp.SetPosition(vec(x, y))
        fp.SetOrientationDegrees(rot)
    if missing:
        print("WARNING: not found (assign footprints / import netlist first):",
              ", ".join(missing))
    else:
        print("Placed all %d footprints." % len(PLACE))


def seg(board, x1, y1, x2, y2):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(vec(x1, y1))
    s.SetEnd(vec(x2, y2))
    s.SetLayer(pcbnew.Edge_Cuts)
    s.SetWidth(pcbnew.FromMM(0.15))
    board.Add(s)


def outline(board):
    seg(board, 0, 0, BOARD_W, 0)
    seg(board, BOARD_W, 0, BOARD_W, BOARD_H)
    seg(board, BOARD_W, BOARD_H, 0, BOARD_H)
    seg(board, 0, BOARD_H, 0, 0)
    print("Drew %.0f x %.0f mm outline." % (BOARD_W, BOARD_H))


def holes(board):
    for cx, cy in HOLES:
        c = pcbnew.PCB_SHAPE(board)
        c.SetShape(pcbnew.SHAPE_T_CIRCLE)
        c.SetStart(vec(cx, cy))                 # center
        c.SetEnd(vec(cx + HOLE_R, cy))          # radius point
        c.SetLayer(pcbnew.Edge_Cuts)
        c.SetWidth(pcbnew.FromMM(0.15))
        board.Add(c)
    print("Added %d mounting-hole cutouts (unplated; swap to MountingHole fp if you "
          "want plated)." % len(HOLES))


def main():
    board = pcbnew.LoadBoard(BOARD_PATH) if BOARD_PATH else pcbnew.GetBoard()
    place(board)
    outline(board)
    holes(board)
    if BOARD_PATH:
        pcbnew.SaveBoard(BOARD_PATH, board)
        print("Saved", BOARD_PATH)
    else:
        try:
            pcbnew.Refresh()
        except Exception:
            pass
    print("Done. Now: set net-class widths (below), route, pour GND, DRC.")


main()

# -----------------------------------------------------------------------------
# Net classes to set in Board Setup (the API for this is version-fiddly; 30s in GUI):
#   Power  -> nets VBAT, VBAT_RAW, SERVO_VCC, GND   : track 0.9 mm, via 0.6/0.3 mm
#   Default (signals)                               : track 0.25 mm, via 0.5/0.3 mm
# Then: bottom layer = one solid GND pour, top = GND pour around signals,
# stitch with a few vias. Keep VBAT_SENSE off any pour gaps.
# -----------------------------------------------------------------------------
