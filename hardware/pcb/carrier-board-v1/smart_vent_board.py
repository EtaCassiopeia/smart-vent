#!/usr/bin/env python3
"""
smart-vent carrier board — circuit described as code (SKiDL).

The status LED (D1/R7/C5, GPIO22) is OPTIONAL. It's the locate/status
indicator described in docs/battery-carrier-board.md; skipping it removes
one idle SK6812 load from the 3V3 rail for builds that don't need it.
Generates two netlists, one per variant:

    python3 smart_vent_board.py            -> smart_vent.net          (with LED)
    SMART_VENT_LED=0 python3 smart_vent_board.py  -> smart_vent_no_led.net (without)

Parts are defined inline (tool=SKIDL) so this runs with NO KiCad symbol
libraries installed. Footprints are assigned as strings; swap any of them
for the exact part/footprint you order. The XIAO pin NUMBERS below follow the
common community 14-pin XIAO footprint (1..7 = D0..D6, 8..11 = D7..D10,
12 = 3V3, 13 = GND, 14 = 5V). >>> Verify against the footprint you actually
drop in (the official Seeed XIAO footprint) before routing. <<<
"""

import os
from skidl import Part, Pin, Net, TEMPLATE, SKIDL, generate_netlist

INCLUDE_LED = os.environ.get("SMART_VENT_LED", "1") != "0"

P = Pin.types.PASSIVE  # treat everything as passive -> keeps ERC quiet


# ---------------------------------------------------------------- templates
def passive(prefix, npins=2):
    pins = [Pin(num=str(i + 1), name=str(i + 1), func=P) for i in range(npins)]
    return Part(tool=SKIDL, name=prefix, ref_prefix=prefix, dest=TEMPLATE, pins=pins)


R = passive("R")
C = passive("C")
SW = passive("SW")  # SPST master switch (2 terminals)
J2 = passive("J", 2)  # battery connector (2-pin)
J3 = passive("J", 3)  # servo connector (3-pin)

MOSFET = Part(
    tool=SKIDL, name="MOSFET", ref_prefix="Q", dest=TEMPLATE,
    pins=[Pin(num="1", name="G", func=P),
          Pin(num="2", name="S", func=P),
          Pin(num="3", name="D", func=P)],
)

if INCLUDE_LED:
    LED = Part(
        tool=SKIDL, name="SK6812", ref_prefix="D", dest=TEMPLATE,
        pins=[Pin(num="1", name="VDD", func=P),
              Pin(num="2", name="DOUT", func=P),
              Pin(num="3", name="GND", func=P),
              Pin(num="4", name="DIN", func=P)],
    )

# XIAO ESP32-C6 module, 14 pads (see header note for numbering)
XIAO = Part(
    tool=SKIDL, name="XIAO_ESP32C6", ref_prefix="U", dest=TEMPLATE,
    pins=[
        Pin(num="1", name="D0_GPIO0", func=P),   # unused (strapping-adjacent; left NC)
        Pin(num="2", name="D1_GPIO1", func=P),   # battery sense (A1)
        Pin(num="3", name="D2_GPIO2", func=P),   # servo signal
        Pin(num="4", name="D3_GPIO21", func=P),  # servo_en
        Pin(num="5", name="D4_GPIO22", func=P),  # LED data (only wired if INCLUDE_LED)
        Pin(num="6", name="D5_GPIO23", func=P),  # NC
        Pin(num="7", name="D6_GPIO16", func=P),  # NC
        Pin(num="8", name="D7_GPIO17", func=P),  # NC
        Pin(num="9", name="D8_GPIO19", func=P),  # NC
        Pin(num="10", name="D9_GPIO20", func=P), # NC
        Pin(num="11", name="D10_GPIO18", func=P),# NC
        Pin(num="12", name="3V3", func=P),
        Pin(num="13", name="GND", func=P),
        Pin(num="14", name="5V", func=P),        # board power in (from battery via switch)
    ],
)


# ---------------------------------------------------------------- instances
def fp(part, footprint):
    part.footprint = footprint
    return part

U1 = fp(XIAO(value="XIAO ESP32-C6"),
        "Seeed:XIAO-ESP32C6")  # replace w/ the exact Seeed XIAO footprint

JBAT = fp(J2(value="SM-2P battery"),
          "Connector_JST:JST_SH_BM02B-SRSS-TB_1x02-1MP_P1.00mm_Vertical")
SW1 = fp(SW(value="SPST master"),
         "Button_Switch_SMD:SW_SPST_PTS810")  # placeholder; use a slide switch >=1A
JSRV = fp(J3(value="SG90 servo"),
          "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical")

Q1 = fp(MOSFET(value="AO3401A (P)"), "Package_TO_SOT_SMD:SOT-23")   # servo high-side
Q2 = fp(MOSFET(value="2N7002 (N)"), "Package_TO_SOT_SMD:SOT-23")    # gate level-shift

R1 = fp(R(value="100k"), "Resistor_SMD:R_0603_1608Metric")   # P-FET gate pullup -> VBAT
R2 = fp(R(value="1k"),   "Resistor_SMD:R_0603_1608Metric")   # GPIO -> N-FET gate series
R3 = fp(R(value="100k"), "Resistor_SMD:R_0603_1608Metric")   # N-FET gate pulldown -> GND
R4 = fp(R(value="2M"),   "Resistor_SMD:R_0603_1608Metric")   # divider top  (VBAT -> SENSE)
R5 = fp(R(value="1M"),   "Resistor_SMD:R_0603_1608Metric")   # divider bottom (SENSE -> GND)
R6 = fp(R(value="330R"), "Resistor_SMD:R_0603_1608Metric")   # servo signal series

C1 = fp(C(value="100nF"), "Capacitor_SMD:C_0603_1608Metric")          # sense tap
C2 = fp(C(value="470uF"), "Capacitor_SMD:CP_Elec_6.3x5.4")            # servo bulk (polarized)
C3 = fp(C(value="100nF"), "Capacitor_SMD:C_0603_1608Metric")          # servo decouple
C4 = fp(C(value="10uF"),  "Capacitor_SMD:C_0805_2012Metric")         # VBAT bulk

# --- optional status LED (locate / battery / install indicator) ---
if INCLUDE_LED:
    R7 = fp(R(value="470R"), "Resistor_SMD:R_0603_1608Metric")   # LED data series
    C5 = fp(C(value="100nF"), "Capacitor_SMD:C_0603_1608Metric")  # LED decouple
    D1 = fp(LED(value="SK6812"), "LED_SMD:LED_SK6812_PLCC4_5.0x5.0mm")


# ---------------------------------------------------------------- nets
gnd        = Net("GND")
vbat_raw   = Net("VBAT_RAW")   # battery + before the master switch
vbat       = Net("VBAT")       # switched battery rail (system)
v3v3       = Net("V3V3")       # XIAO 3V3 out -> LED Vdd (if fitted)
servo_vcc  = Net("SERVO_VCC")  # P-FET drain -> servo power (gated)
servo_sig  = Net("SERVO_SIG")  # at the servo connector
sig_mcu    = Net("SERVO_SIG_MCU")
servo_en   = Net("SERVO_EN")   # GPIO21
nfet_gate  = Net("NFET_GATE")
pfet_gate  = Net("PFET_GATE")
sense      = Net("VBAT_SENSE")
if INCLUDE_LED:
    led_din = Net("LED_DIN")
    led_mcu = Net("LED_DATA_MCU")

# --- battery input + master switch
vbat_raw += JBAT[1]
gnd      += JBAT[2]
vbat_raw += SW1[1]
vbat     += SW1[2]

# --- XIAO power
vbat += U1["14"]   # 5V pin fed from battery rail
v3v3 += U1["12"]
gnd  += U1["13"]

# --- servo high-side P-FET (Q1): S=VBAT, D=SERVO_VCC, G=PFET_GATE
vbat      += Q1["S"]
servo_vcc += Q1["D"]
pfet_gate += Q1["G"]
R1[1] += vbat
R1[2] += pfet_gate          # 100k pullup keeps P-FET off by default

# --- level-shift N-FET (Q2): pulls PFET_GATE low when GPIO drives it
pfet_gate += Q2["D"]
gnd       += Q2["S"]
nfet_gate += Q2["G"]
R2[1] += servo_en
R2[2] += nfet_gate          # 1k series from GPIO21
R3[1] += nfet_gate
R3[2] += gnd                # 100k pulldown -> servo OFF during boot/float

# --- servo signal + connector
sig_mcu   += U1["3"]        # GPIO2
R6[1] += sig_mcu
R6[2] += servo_sig          # 330R series
servo_en  += U1["4"]        # GPIO21
servo_sig += JSRV[1]
servo_vcc += JSRV[2]
gnd       += JSRV[3]

# --- servo rail caps
servo_vcc += C2[1], C3[1]
gnd       += C2[2], C3[2]

# --- battery sense divider (1:3) -> A1/GPIO1
vbat  += R4[1]
sense += R4[2], R5[1], C1[1], U1["2"]
gnd   += R5[2], C1[2]

# --- VBAT bulk cap
vbat += C4[1]
gnd  += C4[2]

# --- status / identify LED (optional — see docs/battery-carrier-board.md
#     "LED indicator (optional)" for the battery-life tradeoff). GPIO22
#     is left unconnected on the no-LED variant.
if INCLUDE_LED:
    led_mcu += U1["5"]          # GPIO22
    R7[1] += led_mcu
    R7[2] += led_din            # 470R data series
    v3v3    += D1["VDD"], C5[1]
    gnd     += D1["GND"], C5[2]
    led_din += D1["DIN"]
    # D1 DOUT left unconnected (single LED)

OUT_FILE = "smart_vent.net" if INCLUDE_LED else "smart_vent_no_led.net"
generate_netlist(file_=OUT_FILE)
print(f"OK: wrote {OUT_FILE} (LED {'included' if INCLUDE_LED else 'omitted'})")
