# Alexa Integration Test Checklist

Manual test procedure for validating Alexa integration.

## Prerequisites

- Smart vent with Matter firmware flashed
- Alexa app on phone
- Thread-capable Echo device (4th gen+)

## Commission

- [ ] Matter skill enabled in Alexa
- [ ] Device appears during "Add Device" flow
- [ ] QR code scan succeeds
- [ ] Manual pairing code entry works as fallback
- [ ] Commissioning completes within 60 seconds
- [ ] Device appears in Alexa app device list

## Voice Commands

- [ ] "Alexa, open the [room] vent" → opens to 180°
- [ ] "Alexa, close the [room] vent" → closes to 90°
- [ ] "Alexa, set the [room] vent to 50 percent" → moves to 135°

## App Control

- [ ] Device controls work in Alexa app
- [ ] Position updates reflect in app

## Routines

- [ ] Create time-based routine
- [ ] Routine fires correctly
- [ ] Vent moves to expected position

## State Sync

- [ ] Open vent via Alexa → other ecosystems show open
- [ ] Close vent via another ecosystem → Alexa shows closed

## Edge Cases

- [ ] Power-cycle vent → Alexa reconnects
- [ ] Remove device from Alexa → can be re-added
- [ ] Factory reset vent → Alexa shows unresponsive, can re-commission
