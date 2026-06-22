#!/usr/bin/env python3
"""Resolve courtyard overlaps in the carrier board placement by iterative
pairwise separation, using real (post-rotation) courtyard bounding boxes.
Prints the resolved PLACE dict so it can be pasted back into build_board.py
and place_smart_vent.py as fixed, reproducible coordinates (no physics at
import time -- this is a one-off solve, not a runtime layout engine).

This already ran once to produce the coordinates currently hardcoded in
build_board.py's PLACE dicts (which also got a couple of manual follow-up
nudges this script doesn't know about -- J2 moved to clear both the board
edge and U1's oddly-shaped placeholder courtyard, see the comment above
PLACE in build_board.py). Re-run it if you change which footprints are
used or the board outline, then re-apply any manual follow-ups by hand.
"""
import os
import sys
import wx
_app = wx.App()
import pcbnew

INCLUDE_LED = os.environ.get("SMART_VENT_LED", "1") != "0"
FPLIB = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"
ORIGIN_X, ORIGIN_Y = 30.0, 30.0
BOARD_W, BOARD_H = 45.0, 34.0
MARGIN = 1.0  # keep this far from the board edge
HOLES = [(3.0, 3.0), (42.0, 31.0)]
HOLE_CLEARANCE = 3.2  # keep courtyards this far from a mounting-hole center

def mm(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(ORIGIN_X + x), pcbnew.FromMM(ORIGIN_Y + y))

board = pcbnew.BOARD()

def load(lib, name):
    fp = pcbnew.FootprintLoad(f"{FPLIB}/{lib}.pretty", name)
    if fp is None:
        raise RuntimeError(f"footprint not found: {lib}:{name}")
    return fp

PARTS = {
    "U1":  ("Connector_PinHeader_2.54mm", "PinHeader_1x07_P2.54mm_Vertical"),
    "J1":  ("Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical"),
    "SW1": ("Button_Switch_THT", "SW_DIP_SPSTx01_Slide_9.78x4.72mm_W7.62mm_P2.54mm"),
    "J2":  ("Connector_PinHeader_2.54mm", "PinHeader_1x03_P2.54mm_Vertical"),
    "Q1":  ("Package_TO_SOT_SMD", "SOT-23"),
    "Q2":  ("Package_TO_SOT_SMD", "SOT-23"),
    "R1":  ("Resistor_SMD", "R_0603_1608Metric"),
    "R2":  ("Resistor_SMD", "R_0603_1608Metric"),
    "R3":  ("Resistor_SMD", "R_0603_1608Metric"),
    "R4":  ("Resistor_SMD", "R_0603_1608Metric"),
    "R5":  ("Resistor_SMD", "R_0603_1608Metric"),
    "R6":  ("Resistor_SMD", "R_0603_1608Metric"),
    "C1":  ("Capacitor_SMD", "C_0603_1608Metric"),
    "C2":  ("Capacitor_THT", "CP_Radial_D8.0mm_P3.50mm"),
    "C3":  ("Capacitor_SMD", "C_0603_1608Metric"),
    "C4":  ("Capacitor_SMD", "C_0805_2012Metric"),
}
if INCLUDE_LED:
    PARTS["R7"] = ("Resistor_SMD", "R_0603_1608Metric")
    PARTS["C5"] = ("Capacitor_SMD", "C_0603_1608Metric")
    PARTS["D1"] = ("LED_SMD", "LED_SK6812_PLCC4_5.0x5.0mm_P3.2mm")

# Seed positions: same zoning as before (signal left / power right /
# connectors bottom), but SW1 rotated 90 deg -- unrotated it's 10.37mm wide
# and would stick off the right edge of a 45mm-wide board.
PLACE = {
    "U1":  [22.5, 11.5,   0],
    "J1":  [41.5,  5.0,   0],
    "SW1": [41.5, 13.0,  90],
    "C4":  [36.5,  6.0,   0],
    "Q1":  [38.0, 18.0,   0],
    "Q2":  [42.5, 18.0,   0],
    "R1":  [36.0, 16.0,  90],
    "R2":  [36.0, 20.0,  90],
    "R3":  [40.0, 22.5,   0],
    "C2":  [38.5, 27.0,   0],
    "C3":  [43.5, 24.0,  90],
    "R6":  [ 6.0,  9.0,  90],
    "R4":  [ 4.0, 18.0,  90],
    "R5":  [ 4.0, 21.0,  90],
    "C1":  [ 7.5, 19.5,  90],
    "J2":  [22.5, 31.5,   0],
}
if INCLUDE_LED:
    PLACE["D1"] = [37.0, 30.0,   0]
    PLACE["R7"] = [32.5, 29.5,  90]
    PLACE["C5"] = [41.5, 30.0,  90]

footprints = {}
for ref, (lib, name) in PARTS.items():
    fp = load(lib, name)
    fp.SetReference(ref)
    board.Add(fp)
    footprints[ref] = fp

def apply_positions():
    for ref, (x, y, rot) in PLACE.items():
        fp = footprints[ref]
        fp.SetPosition(mm(x, y))
        fp.SetOrientationDegrees(rot)

def courtyard_bbox_mm(fp):
    fp.BuildCourtyardCaches()
    poly = fp.GetCourtyard(pcbnew.F_CrtYd)
    if poly.OutlineCount() == 0:
        poly = fp.GetCourtyard(pcbnew.B_CrtYd)
    if poly.OutlineCount() == 0:
        bb = fp.GetBoundingBox()
    else:
        bb = poly.BBox()
    cx = pcbnew.ToMM(bb.GetCenter().x) - ORIGIN_X
    cy = pcbnew.ToMM(bb.GetCenter().y) - ORIGIN_Y
    hw = pcbnew.ToMM(bb.GetWidth()) / 2
    hh = pcbnew.ToMM(bb.GetHeight()) / 2
    return cx, cy, hw, hh

GAP = 0.25  # minimum clearance to leave between courtyards

# Keep these fixed: U1/J2 are enclosure/pin-geography anchors, and the
# left analog cluster (R4/R5/R6/C1) had no DRC findings -- no reason to
# disturb them. Only the right power cluster (+ LED corner) needs solving.
FIXED = {"U1", "J2", "R4", "R5", "R6", "C1"}

def resolve(max_iters=600):
    refs = list(PARTS.keys())
    movable = [r for r in refs if r not in FIXED]
    for it in range(max_iters):
        apply_positions()
        boxes = {r: courtyard_bbox_mm(footprints[r]) for r in refs}
        moved = False
        for i, r1 in enumerate(refs):
            for r2 in refs[i + 1:]:
                if r1 in FIXED and r2 in FIXED:
                    continue
                cx1, cy1, hw1, hh1 = boxes[r1]
                cx2, cy2, hw2, hh2 = boxes[r2]
                dx = cx2 - cx1
                dy = cy2 - cy1
                overlap_x = (hw1 + hw2 + GAP) - abs(dx)
                overlap_y = (hh1 + hh2 + GAP) - abs(dy)
                if overlap_x > 0 and overlap_y > 0:
                    moved = True
                    f1, f2 = (r1 in FIXED), (r2 in FIXED)
                    # split the push: 0 to a fixed ref, all of it to the
                    # movable one; half each if both movable
                    s1 = 0.0 if f1 else (1.0 if f2 else 0.5)
                    s2 = 0.0 if f2 else (1.0 if f1 else 0.5)
                    if overlap_x < overlap_y:
                        push = overlap_x + 0.04
                        sign = 1 if dx >= 0 else -1
                        PLACE[r1][0] -= sign * push * s1
                        PLACE[r2][0] += sign * push * s2
                    else:
                        push = overlap_y + 0.04
                        sign = 1 if dy >= 0 else -1
                        PLACE[r1][1] -= sign * push * s1
                        PLACE[r2][1] += sign * push * s2
        # mounting-hole keepout
        for r in movable:
            cx, cy, hw, hh = boxes[r]
            for hx, hy in HOLES:
                ddx = cx - hx
                ddy = cy - hy
                dist = (ddx ** 2 + ddy ** 2) ** 0.5
                min_dist = HOLE_CLEARANCE + max(hw, hh)
                if dist < min_dist and dist > 1e-6:
                    moved = True
                    push = (min_dist - dist) + 0.05
                    PLACE[r][0] += ddx / dist * push
                    PLACE[r][1] += ddy / dist * push
        # board-edge clamp
        for r in movable:
            cx, cy, hw, hh = boxes[r]
            PLACE[r][0] = min(max(PLACE[r][0], MARGIN + hw), BOARD_W - MARGIN - hw)
            PLACE[r][1] = min(max(PLACE[r][1], MARGIN + hh), BOARD_H - MARGIN - hh)
        if not moved:
            print(f"Converged after {it+1} iterations.")
            return
    print(f"WARNING: did not fully converge after {max_iters} iterations.")

resolve()
apply_positions()

print("\nResolved PLACE = {")
for ref, (x, y, rot) in PLACE.items():
    print(f'    "{ref}": ({round(x,2)}, {round(y,2)}, {int(rot)}),')
print("}")

OUT = "/tmp/kicad-build/nudged_with_led.kicad_pcb" if INCLUDE_LED else "/tmp/kicad-build/nudged_no_led.kicad_pcb"

# board outline + holes for visual sanity in pcbnew if opened directly
def seg(x1, y1, x2, y2):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(mm(x1, y1)); s.SetEnd(mm(x2, y2))
    s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(pcbnew.FromMM(0.15))
    board.Add(s)
seg(0, 0, BOARD_W, 0); seg(BOARD_W, 0, BOARD_W, BOARD_H)
seg(BOARD_W, BOARD_H, 0, BOARD_H); seg(0, BOARD_H, 0, 0)
for cx, cy in HOLES:
    c = pcbnew.PCB_SHAPE(board)
    c.SetShape(pcbnew.SHAPE_T_CIRCLE)
    c.SetStart(mm(cx, cy)); c.SetEnd(mm(cx + 1.35, cy))
    c.SetLayer(pcbnew.Edge_Cuts); c.SetWidth(pcbnew.FromMM(0.15))
    board.Add(c)

pcbnew.SaveBoard(OUT, board)
print(f"\nSaved {OUT} (no nets wired -- this script only solves placement)")
