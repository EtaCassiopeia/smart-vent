# Google Home Integration Test Checklist

Manual test procedure for validating Google Home integration.

## Prerequisites

- Smart vent with Matter firmware flashed
- Google Home app on phone
- Thread-capable Google device (Nest Hub, Nest Mini 2nd gen+)

## Commission

- [ ] Device appears in Google Home app BLE scan
- [ ] QR code scan succeeds
- [ ] Manual pairing code entry works as fallback
- [ ] Commissioning completes within 60 seconds
- [ ] Device appears as "Window covering" in Google Home

## Voice Commands

- [ ] "Hey Google, open the [room] vent" → opens to 180°
- [ ] "Hey Google, close the [room] vent" → closes to 90°
- [ ] "Hey Google, set the [room] vent to 50%" → moves to 135°
- [ ] "Hey Google, what's the [room] vent position?" → reports correct %

## App Control

- [ ] Slider in Google Home app works
- [ ] Position updates reflect in app within 5 seconds
- [ ] Open/Close buttons work

## Routines

- [ ] Create time-based routine (open at specific time)
- [ ] Routine fires correctly
- [ ] Vent moves to expected position

## State Sync with Home Assistant

- [ ] Open vent via Google Home → HA shows open
- [ ] Close vent via HA → Google Home shows closed
- [ ] Set position via Google Home → HA cover slider updates

## Edge Cases

- [ ] Power-cycle vent → Google Home reconnects within 30s
- [ ] Remove device from Google Home → can be re-added
- [ ] Factory reset vent → Google Home shows unavailable, can re-commission
