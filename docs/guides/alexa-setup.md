# Alexa Setup Guide

Control your smart vents with Alexa voice commands and the Alexa app.

## Prerequisites

- Smart vent flashed with Matter-enabled firmware (v0.2.0+)
- Amazon Alexa app (Android or iOS)
- Echo device with Thread support (Echo 4th gen+, Eero 6+)
- The Echo device must be on the same network as the Thread border router

## 1. Enable Matter Support in Alexa

1. Open the **Alexa** app
2. Go to **More** → **Skills & Games**
3. Search for **Matter**
4. Enable the **Matter** skill (if not already enabled)

## 2. Commission via Alexa App

1. Open the **Alexa** app
2. Tap **+** → **Add Device**
3. Select **Other** → **Matter**
4. Scan the **QR code** from the serial output (or enter the 11-digit manual pairing code)
5. Wait for commissioning to complete (~30-60 seconds)
6. Alexa discovers the vent as a "Window covering" or "Blind" device

## 3. Assign to a Room

After commissioning:
1. Alexa prompts you to add the device to a group
2. Select or create a room (e.g., "Bedroom", "Living Room")
3. Optionally rename the device (e.g., "Bedroom Vent")

## 4. Voice Commands

| Command | Action |
|---------|--------|
| "Alexa, open the bedroom vent" | Fully open (180°) |
| "Alexa, close the bedroom vent" | Fully close (90°) |
| "Alexa, set the bedroom vent to 50%" | Half open (135°) |

**Note:** Alexa may categorize the device as a "blind" or "shade" — voice commands work the same way.

## 5. Routines

Create routines in the Alexa app:

1. Go to **More** → **Routines**
2. Tap **+** to create a new routine
3. Set a trigger (time, location, etc.)
4. Add action → **Smart Home** → select the vent
5. Choose position (open/close/percentage)

Example routines:
- **Good Morning**: Open bedroom vent at 6:30 AM
- **Good Night**: Close all vents at 10:00 PM
- **Leaving Home**: Close all vents when phone disconnects from WiFi

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Device not found | Ensure BLE is enabled on your phone and the vent is advertising. Move closer to the device. |
| "Device is unresponsive" | Check vent is powered on and on the Thread network. Try "Alexa, discover devices". |
| Wrong device type shown | Alexa may show "blind" instead of "vent" — functionality is identical. |
| Position commands ignored | Try "Alexa, set [device name] to [number] percent" with explicit percentage. |
| "Sorry, I don't know that one" | Ensure the device name doesn't conflict with other devices. Try renaming. |
