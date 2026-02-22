# XIAO ESP32C6 + SG90 Servo Wiring

## Components

- Seeed Studio XIAO ESP32C6
- SG90 micro servo
- Jumper wires (3x)
- (Optional) External 5V power supply for servo

## SG90 Wire Colors

| Wire | Color | Function |
|------|-------|----------|
| Signal | Orange/Yellow | PWM control |
| VCC | Red | +5V power |
| GND | Brown/Black | Ground |

## XIAO ESP32C6 Pinout Reference

[![XIAO ESP32C6 Board](https://files.seeedstudio.com/wiki/SeeedStudio-XIAO-ESP32C6/img/xiaoc6.jpg)](https://wiki.seeedstudio.com/xiao_esp32c6_getting_started/)

### Pin List

[![XIAO ESP32C6 Pin List](https://wdcdn.qpic.cn/MTY4ODg1Nzc0ODUwMjM3NA_318648_dMoXitoaQiq2N3-a_1711678067?w=1486&h=1228)](https://wiki.seeedstudio.com/xiao_esp32c6_getting_started/)

*Source: [Seeed Studio XIAO ESP32C6 Wiki](https://wiki.seeedstudio.com/xiao_esp32c6_getting_started/)*

Only the header pins (D0–D10) are used. The JTAG pads on the bottom of the
board (MTMS, MTDI, MTCK, MTDO) are **not** needed.

| Board Label | GPIO | Default Function | Alternate Functions | Notes |
|-------------|------|------------------|---------------------|-------|
| D0 | GPIO0 | Analog | LP_GPIO0, ADC | Strapping pin — avoid |
| D1 | GPIO1 | Analog | LP_GPIO1, ADC | |
| **D2** | **GPIO2** | **Analog** | **LP_GPIO2, ADC** | **PWM → servo signal** |
| D3 | GPIO21 | Digital | SDIO_DATA1 | |
| D4 / SDA | GPIO22 | I2C Data | SDIO_DATA2 | |
| D5 / SCL | GPIO23 | I2C Clock | SDIO_DATA3 | |
| D6 / TX | GPIO16 | UART TX | — | |
| D7 / RX | GPIO17 | UART RX | — | |
| D8 / SCK | GPIO19 | SPI Clock | SDIO_CLK | |
| D9 / MISO | GPIO20 | SPI Data | SDIO_DATA0 | |
| D10 / MOSI | GPIO18 | SPI Data | SDIO_CMD | |
| 5V | VBUS | Power | — | USB 5V in/out |
| 3V3 | 3V3 | Power | — | 3.3V regulated output |
| GND | — | Ground | — | |

## Wiring Diagram

![Wiring Diagram](../diagrams/wiring.svg)

## Pin Assignment

| XIAO Pin | GPIO | Function | Connected To |
|----------|------|----------|-------------|
| D2 | GPIO2 | LEDC PWM Channel 0 | SG90 signal (orange) |
| 5V | VBUS | Power output | SG90 VCC (red) |
| GND | — | Ground | SG90 GND (brown) |

```
  XIAO ESP32C6              SG90 Servo
  ┌──────────┐
  │ D2       │──────────── Signal (orange)
  │ 5V       │──────────── VCC (red)
  │ GND      │──────────── GND (brown)
  └──────────┘
```

The servo pin is configured in `firmware/vent-controller/src/main.rs` as
`peripherals.pins.gpio2`. To use a different pin, change this reference and
update the wiring accordingly.

## Power Considerations

### USB-Powered (Recommended for development)

The XIAO ESP32C6 provides 5V from its USB-C port via the VBUS pin. This is
sufficient for a single SG90 servo during testing.

### External Power (Recommended for production)

For reliable operation, power the servo from a separate 5V supply:

```
External 5V PSU ──── SG90 VCC (red)
                 └── SG90 GND (brown) ──── XIAO GND (shared ground!)
XIAO D2 (GPIO2) ──── SG90 Signal (orange)
```

**Important**: Always connect grounds together (XIAO GND and external PSU GND).

### Battery-Powered

For battery operation:

- Use 3x AA batteries (4.5V) or a LiPo with a 5V boost converter
- Enable deep sleep mode in firmware configuration
- The servo draws ~150mA under load, ~10mA idle
- ESP32-C6 in deep sleep: ~7uA

## Servo Range

| Angle | Position | PWM Duty (50Hz) |
|-------|----------|-----------------|
| 90° | Closed | ~1.0ms pulse |
| 135° | Half-open | ~1.5ms pulse |
| 180° | Open | ~2.0ms pulse |

## Mounting

The SG90 mounts to the vent louver with the included servo horn. Use the
single-arm horn for a direct push/pull linkage to the vent blade.
