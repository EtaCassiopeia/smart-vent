# Google Home Setup Guide

Control your smart vents with Google Home voice commands and the Google Home app.

## Prerequisites

- Smart vent flashed with Matter-enabled firmware (v0.2.0+)
- Google Home app (Android or iOS)
- Google Nest Hub, Nest Mini, or other Thread-capable Google device
- The Google device must be on the same network as the Thread border router

## 1. Commission via Google Home App

1. Open the **Google Home** app
2. Tap **+** → **Set up device** → **New device**
3. Choose your home
4. The app scans for nearby Matter devices via BLE
5. When the vent appears, tap it
6. Scan the **QR code** from the serial output (or enter the manual pairing code)
7. Wait for commissioning to complete (~30 seconds)
8. The vent appears as a "Window covering" device

## 2. Assign to a Room

After commissioning:
1. Google Home prompts you to assign the device to a room
2. Select the room where the vent is installed (e.g., "Bedroom", "Living Room")
3. Optionally rename the device (e.g., "Bedroom Vent")

## 3. Voice Commands

| Command | Action |
|---------|--------|
| "Hey Google, open the bedroom vent" | Fully open (180°) |
| "Hey Google, close the bedroom vent" | Fully close (90°) |
| "Hey Google, set the bedroom vent to 50%" | Half open (135°) |
| "Hey Google, what's the bedroom vent position?" | Report current position |

**Note:** Google Home maps "open" to 100% open (0% in Matter terms) and "close" to 0% open (100% in Matter terms).

## 4. Routines

Create routines in the Google Home app to automate vent control:

1. Go to **Automations** → **+** (Add)
2. Add a **Starter** (e.g., time of day, sunrise/sunset)
3. Add an **Action** → **Adjust home devices** → select the vent
4. Set the desired position

Example routines:
- **Morning**: Open bedroom vent at 7:00 AM
- **Night**: Close guest room vent at 10:00 PM
- **Away**: Close all vents when everyone leaves

## 5. Multi-Admin with Home Assistant

The vent can be controlled by both Google Home and Home Assistant simultaneously:

1. First commission into Google Home (steps above)
2. Open a commissioning window from Google Home:
   - Go to device settings → **Linked Matter apps & services** → **Link new app**
3. Commission into Home Assistant's Matter integration
4. Both ecosystems now control the same device — state stays in sync

See [multi-admin.md](multi-admin.md) for detailed instructions.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Device not found during scan | Ensure the vent is powered on and BLE advertising (check serial output). Move phone closer to device. |
| "Setup failed" error | Power-cycle the vent and try again. Check that your Google Home device supports Thread. |
| Voice commands don't work | Verify the device is assigned to a room. Try "Hey Google, sync my devices". |
| Position doesn't update | The Google Home app may cache state. Pull down to refresh. |
| "Device unavailable" | Check that the vent is powered on and on the Thread network (serial output shows "child" role). |
