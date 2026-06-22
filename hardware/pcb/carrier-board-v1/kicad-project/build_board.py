#!/usr/bin/env python3
"""Build a real .kicad_pcb for the smart-vent carrier board v1: load real
library footprints where they exist, placeholder footprints where they
don't (XIAO module, SM-2P battery connector), place everything per the
floorplan, wire nets per smart_vent_board.py's connectivity, draw the
board outline + mounting holes. Routing is intentionally NOT attempted —
verifying placement/footprints/export is the goal here.
"""
import wx
_app = wx.App()
import pcbnew

FPLIB = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"

ORIGIN_X, ORIGIN_Y = 30.0, 30.0
BOARD_W, BOARD_H = 45.0, 34.0

def mm(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(ORIGIN_X + x), pcbnew.FromMM(ORIGIN_Y + y))

board = pcbnew.BOARD()

def load(lib, name):
    fp = pcbnew.FootprintLoad(f"{FPLIB}/{lib}.pretty", name)
    if fp is None:
        raise RuntimeError(f"footprint not found: {lib}:{name}")
    return fp

# ref -> (lib, name, placeholder?)
PARTS = {
    "U1":  ("Connector_PinHeader_2.54mm", "PinHeader_1x07_P2.54mm_Vertical", True),   # placeholder: real Seeed XIAO fp not in stock libs
    "J1":  ("Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical", True),   # placeholder: no stock "JST-SM" 2P footprint
    "SW1": ("Button_Switch_THT", "SW_DIP_SPSTx01_Slide_9.78x4.72mm_W7.62mm_P2.54mm", False),
    "J2":  ("Connector_PinHeader_2.54mm", "PinHeader_1x03_P2.54mm_Vertical", False),
    "Q1":  ("Package_TO_SOT_SMD", "SOT-23", False),
    "Q2":  ("Package_TO_SOT_SMD", "SOT-23", False),
    "R1":  ("Resistor_SMD", "R_0603_1608Metric", False),
    "R2":  ("Resistor_SMD", "R_0603_1608Metric", False),
    "R3":  ("Resistor_SMD", "R_0603_1608Metric", False),
    "R4":  ("Resistor_SMD", "R_0603_1608Metric", False),
    "R5":  ("Resistor_SMD", "R_0603_1608Metric", False),
    "R6":  ("Resistor_SMD", "R_0603_1608Metric", False),
    "R7":  ("Resistor_SMD", "R_0603_1608Metric", False),
    "C1":  ("Capacitor_SMD", "C_0603_1608Metric", False),
    "C2":  ("Capacitor_THT", "CP_Radial_D8.0mm_P3.50mm", True),  # placeholder: exact CP_Elec_6.3x5.4 SMD not present, using closest stock part
    "C3":  ("Capacitor_SMD", "C_0603_1608Metric", False),
    "C4":  ("Capacitor_SMD", "C_0805_2012Metric", False),
    "C5":  ("Capacitor_SMD", "C_0603_1608Metric", False),
    "D1":  ("LED_SMD", "LED_SK6812_PLCC4_5.0x5.0mm_P3.2mm", False),
}

PLACE = {
    "U1":  (22.5, 11.5,   0),
    "J1":  (41.0,  6.0,   0),
    "SW1": (41.0, 11.0,   0),
    "C4":  (37.0,  8.0,   0),
    "Q1":  (40.0, 16.5,   0),
    "Q2":  (43.5, 16.5,   0),
    "R1":  (37.0, 15.0,  90),
    "R2":  (37.0, 17.5,  90),
    "R3":  (43.5, 20.0,   0),
    "C2":  (40.0, 24.0,   0),
    "C3":  (43.5, 23.5,  90),
    "R6":  ( 6.0,  9.0,  90),
    "R4":  ( 4.0, 18.0,  90),
    "R5":  ( 4.0, 21.0,  90),
    "C1":  ( 7.5, 19.5,  90),
    "J2":  (22.5, 31.5,   0),
    "D1":  (40.5, 30.5,   0),
    "R7":  (36.5, 29.5,  90),
    "C5":  (44.0, 30.5,  90),
}

placeholders = []
footprints = {}
for ref, (lib, name, is_placeholder) in PARTS.items():
    fp = load(lib, name)
    fp.SetReference(ref)
    x, y, rot = PLACE[ref]
    fp.SetPosition(mm(x, y))
    fp.SetOrientationDegrees(rot)
    board.Add(fp)
    footprints[ref] = fp
    if is_placeholder:
        placeholders.append((ref, lib, name))

# --- nets, mirroring smart_vent_board.py's connectivity ---
NETS = {
    "GND":        [("J1", 2), ("U1", 13 if False else 7), ("Q2", 2), ("J2", 3), ("C2", 2), ("C3", 2), ("R5", 2), ("C1", 2), ("C4", 2), ("D1", 3), ("C5", 2)],
}
# U1 is a 7-pin placeholder header (not the real 14-pad XIAO), so pin-exact
# net wiring against it is not meaningful yet -- skip net assignment on U1
# pending the real footprint. Wire everything else.
NETS = {
    "VBAT_RAW":  [("J1", 1), ("SW1", 1)],
    "VBAT":      [("SW1", 2), ("Q1", 2), ("R1", 1), ("R4", 1), ("C4", 1)],
    "SERVO_VCC": [("Q1", 3), ("J2", 2), ("C2", 1), ("C3", 1)],
    "PFET_GATE": [("Q1", 1), ("R1", 2), ("Q2", 3)],
    "NFET_GATE": [("Q2", 1), ("R2", 2), ("R3", 1)],
    "SERVO_EN":  [("R2", 1)],
    "SERVO_SIG_MCU": [("R6", 1)],
    "SERVO_SIG": [("R6", 2), ("J2", 1)],
    "VBAT_SENSE": [("R4", 2), ("R5", 1), ("C1", 1)],
    "LED_DATA_MCU": [("R7", 1)],
    "LED_DIN":   [("R7", 2), ("D1", 4)],
    "V3V3":      [("D1", 1), ("C5", 1)],
    "GND":       [("J1", 2), ("Q2", 2), ("J2", 3), ("C2", 2), ("C3", 2), ("R5", 2),
                  ("C1", 2), ("C4", 2), ("D1", 3), ("C5", 2)],
}

netinfo = board.GetNetInfo()
for net_name, pads in NETS.items():
    ni = pcbnew.NETINFO_ITEM(board, net_name)
    board.Add(ni)
    for ref, pin in pads:
        pad = footprints[ref].FindPadByNumber(str(pin))
        if pad is None:
            print(f"WARN: {ref} pad {pin} not found (footprint pad numbering may differ)")
            continue
        pad.SetNet(ni)

# board outline
def seg(x1, y1, x2, y2):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(mm(x1, y1))
    s.SetEnd(mm(x2, y2))
    s.SetLayer(pcbnew.Edge_Cuts)
    s.SetWidth(pcbnew.FromMM(0.15))
    board.Add(s)

seg(0, 0, BOARD_W, 0)
seg(BOARD_W, 0, BOARD_W, BOARD_H)
seg(BOARD_W, BOARD_H, 0, BOARD_H)
seg(0, BOARD_H, 0, 0)

for cx, cy in [(3.0, 3.0), (42.0, 31.0)]:
    c = pcbnew.PCB_SHAPE(board)
    c.SetShape(pcbnew.SHAPE_T_CIRCLE)
    c.SetStart(mm(cx, cy))
    c.SetEnd(mm(cx + 1.35, cy))
    c.SetLayer(pcbnew.Edge_Cuts)
    c.SetWidth(pcbnew.FromMM(0.15))
    board.Add(c)

OUT = "/tmp/kicad-build/smart_vent_v1.kicad_pcb"
pcbnew.SaveBoard(OUT, board)
print(f"Saved {OUT}")
print(f"Placed {len(footprints)} footprints, {len(NETS)} nets wired.")
if placeholders:
    print("PLACEHOLDER footprints (no exact stock-library match, need sourcing before fab):")
    for ref, lib, name in placeholders:
        print(f"  {ref}: using {lib}:{name} as a stand-in")
