# ESP32-C6 + SG90 Servo Wiring

## Components

- ESP32-C6 development board
- SG90 micro servo
- Jumper wires (3x)
- (Optional) External 5V power supply for servo

## SG90 Wire Colors

| Wire | Color | Function |
|------|-------|----------|
| Signal | Orange/Yellow | PWM control |
| VCC | Red | +5V power |
| GND | Brown/Black | Ground |

## Wiring Diagram

```
ESP32-C6                SG90 Servo
+----------+           +----------+
|          |           |          |
|  GPIO 6  |---[signal]---| Orange   |
|          |           |          |
|  5V/VIN  |---[power]----| Red      |
|          |           |          |
|  GND     |---[ground]---| Brown    |
|          |           |          |
+----------+           +----------+
```

## Pin Assignment

| ESP32-C6 Pin | Function | Connected To |
|-------------|----------|-------------|
| GPIO 6 | LEDC PWM Channel 0 | SG90 signal (orange) |
| 5V / VIN | Power output | SG90 VCC (red) |
| GND | Ground | SG90 GND (brown) |

GPIO 6 is configured in `firmware/vent-controller/src/main.rs`. To use a different pin, change the `peripherals.pins.gpio6` reference.

## Power Considerations

### USB-Powered (Recommended for development)

The ESP32-C6 dev board provides 5V from its USB port. This is sufficient for a single SG90 servo during testing.

### External Power (Recommended for production)

For reliable operation, power the servo from a separate 5V supply:

```
External 5V PSU ──── SG90 VCC (red)
                 └── SG90 GND (brown) ──── ESP32-C6 GND (shared ground!)
ESP32-C6 GPIO 6 ──── SG90 Signal (orange)
```

**Important**: Always connect grounds together (ESP32-C6 GND and external PSU GND).

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

The SG90 mounts to the vent louver with the included servo horn. Use the single-arm horn for a direct push/pull linkage to the vent blade.
