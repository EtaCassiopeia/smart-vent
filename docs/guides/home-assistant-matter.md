# Home Assistant Matter Integration Guide

Control your smart vents using Home Assistant's built-in Matter integration (no custom component required).

## Prerequisites

- Smart vent flashed with Matter-enabled firmware (v0.2.0+)
- Home Assistant 2023.2+ with Matter integration enabled
- Thread border router accessible from HA (OTBR or Apple TV/HomePod)

## 1. Enable the Matter Integration

1. Go to **Settings** → **Devices & Services**
2. Click **Add Integration**
3. Search for **Matter (BETA)** and add it
4. Follow the setup wizard to connect to your Matter server

## 2. Commission the Vent

### Option A: Direct commissioning (HA as first controller)

1. In HA, go to **Settings** → **Devices & Services** → **Matter**
2. Click **Commission Device**
3. Enter the **manual pairing code** from the vent's serial output (e.g., `34970112332`)
4. Or scan the QR code if using the HA mobile app
5. Wait for commissioning to complete

### Option B: Multi-admin (HA as secondary controller)

If the vent is already commissioned into Google Home or Alexa:

1. Open a commissioning window from the primary ecosystem (see [multi-admin.md](multi-admin.md))
2. In HA, go to **Settings** → **Devices & Services** → **Matter**
3. Click **Commission Device**
4. HA discovers the vent via BLE and joins as a second admin

## 3. Device in Home Assistant

After commissioning, the vent appears as a **Cover** entity:

- **Entity type**: `cover.smart_hvac_vent`
- **Device class**: Shade (mapped from Window Covering)
- **Supported features**: Open, Close, Set Position

### Controls

| Action | HA Service | Effect |
|--------|-----------|--------|
| Open | `cover.open_cover` | Fully open (180°) |
| Close | `cover.close_cover` | Fully close (90°) |
| Set position | `cover.set_cover_position` | Set to percentage (0%=closed, 100%=open) |

**Note:** Home Assistant's cover position convention (0%=closed, 100%=open) is the inverse of Matter's percent100ths (0%=open, 100%=closed). HA handles the conversion automatically.

## 4. Dashboard Card

Add a cover card to your dashboard:

```yaml
type: entities
entities:
  - entity: cover.smart_hvac_vent
    name: Bedroom Vent
```

Or use a tile card with position slider:

```yaml
type: tile
entity: cover.smart_hvac_vent
name: Bedroom Vent
features:
  - type: cover-position
```

## 5. Automations

Example automation to close vents at night:

```yaml
automation:
  - alias: "Close vents at night"
    trigger:
      - platform: time
        at: "22:00:00"
    action:
      - service: cover.close_cover
        target:
          entity_id: cover.smart_hvac_vent
```

## Custom Component vs Matter Integration

| Feature | Custom Component | Matter Integration |
|---------|-----------------|-------------------|
| Protocol | CoAP (custom) | Matter (standard) |
| Setup | Requires hub service | Direct HA ↔ device |
| Multi-ecosystem | No | Yes (Google, Alexa, Apple) |
| Extra attributes | Room, floor, RSSI, heap | Standard Matter attributes |
| Device health | Yes (custom) | Limited |

For most users, the Matter integration is recommended. The custom component is useful if you need the extended health telemetry or already have the CoAP hub infrastructure.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Commission fails | Ensure HA can reach the Thread network. Check OTBR is running. |
| "Device not found" | Verify BLE is available on the HA host. Try moving closer. |
| Position always 0% | Check that the firmware is reporting position correctly (serial log). |
| "Entity unavailable" | Vent may be powered off or disconnected from Thread. Check serial output. |
