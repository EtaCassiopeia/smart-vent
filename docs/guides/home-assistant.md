# Home Assistant User Guide

This guide covers day-to-day use of the Smart Vent Control integration in
Home Assistant — controlling individual vents, managing groups, setting up
schedules, and writing templates.

For initial setup (installing the integration, mounting the hub database),
see the [Commissioning Guide](commissioning.md#7-home-assistant).

## Entities

Each vent appears as a **cover** entity with device class `damper`. The
entity ID follows the pattern `cover.vent_<suffix>` where `<suffix>` is
derived from the device name or EUI-64.

### Entity attributes

Every vent entity exposes these state attributes:

| Attribute          | Description                          |
|--------------------|--------------------------------------|
| `current_position` | 0 (closed) to 100 (fully open)       |
| `eui64`            | Device hardware address              |
| `angle`            | Raw servo angle (90-180)             |
| `room`             | Room assigned via hub config         |
| `floor`            | Floor assigned via hub config        |
| `firmware_version`  | Firmware version string              |
| `rssi`             | Thread radio signal strength (dBm)   |
| `power_source`     | `usb` or `battery`                   |
| `free_heap`        | Free memory on the device (bytes)    |
| `battery_mv`       | Battery voltage (only if battery-powered) |

## Controlling individual vents

### From the UI

1. Go to **Settings -> Devices & Services -> Vent Control**
2. Click a vent entity
3. Use the slider to set position, or the up/down buttons to fully
   open or close

### From Developer Tools

**Settings -> Developer tools -> Actions**:

```yaml
action: cover.open_cover
target:
  entity_id: cover.vent_ab12c
```

```yaml
action: cover.close_cover
target:
  entity_id: cover.vent_ab12c
```

```yaml
action: cover.set_cover_position
target:
  entity_id: cover.vent_ab12c
data:
  position: 50
```

### From a script or automation

```yaml
- action: cover.set_cover_position
  target:
    entity_id: cover.vent_ab12c
  data:
    position: 75
```

## Controlling vents by room or floor

The integration registers two services for group control. These target
all vents matching the given room or floor name (as configured in the hub).

### `vent_control.set_room`

Set all vents in a room to the same position.

```yaml
action: vent_control.set_room
data:
  room: bedroom
  position: 100
```

| Field      | Type   | Description                          |
|------------|--------|--------------------------------------|
| `room`     | string | Room name (case-insensitive match)   |
| `position` | int    | 0 (closed) to 100 (fully open)       |

### `vent_control.set_floor`

Set all vents on a floor to the same position.

```yaml
action: vent_control.set_floor
data:
  floor: "2"
  position: 0
```

| Field      | Type   | Description                          |
|------------|--------|--------------------------------------|
| `floor`    | string | Floor identifier (case-insensitive)  |
| `position` | int    | 0 (closed) to 100 (fully open)       |

Both actions can be called from **Settings -> Developer tools -> Actions**,
from automations, or from scripts.

## Scheduling with blueprints

Pre-built blueprints let you create daily open/close schedules without
writing YAML.

### Import a blueprint

1. Go to **Settings -> Automations & Scenes -> Blueprints**
2. Click **Import Blueprint** (bottom right)
3. Paste one of these URLs:

   **Schedule by floor:**
   ```
   https://raw.githubusercontent.com/EtaCassiopeia/smart-vent/main/homeassistant/blueprints/automation/vent_control/schedule_vent_by_floor.yaml
   ```

   **Schedule by room:**
   ```
   https://raw.githubusercontent.com/EtaCassiopeia/smart-vent/main/homeassistant/blueprints/automation/vent_control/schedule_vent_by_room.yaml
   ```

4. Click **Preview** then **Import**

### Create an automation from a blueprint

1. Go to **Settings -> Automations & Scenes -> Automations**
2. Click **Create Automation -> Use a Blueprint**
3. Select **Schedule Vent by Room** (or Floor)
4. Fill in the fields:
   - **Room** (or Floor): must match the hub config exactly (e.g. `bedroom`)
   - **Open Time**: when to open (default 07:00)
   - **Close Time**: when to close (default 22:00)
   - **Open Position**: position at open time (default 100%)
   - **Close Position**: position at close time (default 0%)
5. Click **Save**

You can create multiple automations from the same blueprint — one per
room or floor.

## Writing automations manually

If the blueprints don't fit your needs, write automations in YAML directly.

### Close all bedroom vents at night

```yaml
automation:
  - alias: "Close bedroom vents at night"
    trigger:
      - platform: time
        at: "22:00:00"
    action:
      - action: vent_control.set_room
        data:
          room: bedroom
          position: 0
```

### Open ground floor vents on weekday mornings

```yaml
automation:
  - alias: "Open ground floor weekday mornings"
    trigger:
      - platform: time
        at: "06:30:00"
    condition:
      - condition: time
        weekday:
          - mon
          - tue
          - wed
          - thu
          - fri
    action:
      - action: vent_control.set_floor
        data:
          floor: "1"
          position: 100
```

### Partially open a vent based on another event

```yaml
automation:
  - alias: "Half-open office vent when PC turns on"
    trigger:
      - platform: state
        entity_id: binary_sensor.office_pc
        to: "on"
    action:
      - action: cover.set_cover_position
        target:
          entity_id: cover.vent_office
        data:
          position: 50
```

## Templates

HA templates let you read vent state in dashboards, conditions, and
notifications.

### Read current position

```jinja
{{ state_attr('cover.vent_ab12c', 'current_position') }}
```

### Check if a vent is open

```jinja
{{ is_state('cover.vent_ab12c', 'open') }}
```

### Get the room of a vent

```jinja
{{ state_attr('cover.vent_ab12c', 'room') }}
```

### Count open vents

```jinja
{{ states.cover
   | selectattr('attributes.device_class', 'eq', 'damper')
   | selectattr('state', 'eq', 'open')
   | list | count }}
```

### List all vents on a floor

```jinja
{% set floor = "2" %}
{% for vent in states.cover
   if vent.attributes.device_class == 'damper'
   and vent.attributes.floor == floor %}
  - {{ vent.name }}: {{ vent.attributes.current_position }}%
{% endfor %}
```

### Average position of bedroom vents

```jinja
{% set vents = states.cover
   | selectattr('attributes.device_class', 'eq', 'damper')
   | selectattr('attributes.room', 'eq', 'bedroom')
   | map(attribute='attributes.current_position')
   | list %}
{{ (vents | sum / vents | count) | round(0) if vents else 'N/A' }}%
```

### Use in a condition (only act if vent is less than 50% open)

```yaml
condition:
  - condition: template
    value_template: >
      {{ state_attr('cover.vent_ab12c', 'current_position') | int < 50 }}
```

## Dashboard cards

### Simple entity card

```yaml
type: entities
title: Bedroom Vents
entities:
  - entity: cover.vent_bedroom_1
  - entity: cover.vent_bedroom_2
```

### Vent position as a gauge

```yaml
type: gauge
entity: cover.vent_ab12c
attribute: current_position
name: Office Vent
unit: "%"
min: 0
max: 100
severity:
  green: 60
  yellow: 30
  red: 0
```

### All vents in a room (auto-entities, requires HACS)

If you have the `auto-entities` custom card installed:

```yaml
type: custom:auto-entities
card:
  type: entities
  title: Kitchen Vents
filter:
  include:
    - attributes:
        device_class: damper
        room: kitchen
```

## Troubleshooting

### Entity shows "unavailable"

The device is not responding to CoAP polls. Check:
1. Device is powered on and has joined the Thread network
2. Hub can reach the device: `vent-hub status`
3. HA container has `--network host` (required for IPv6/Thread)

### Position doesn't update after a command

The integration polls every 30 seconds (configurable). After sending a
command, the UI updates on the next poll cycle. To force a refresh,
reload the integration: **Settings -> Devices & Services -> Vent Control
-> three dots -> Reload**.

### Actions not showing in Developer Tools

The `vent_control.set_room` and `vent_control.set_floor` actions are
registered when the first config entry loads. If they don't appear in
**Settings -> Developer tools -> Actions**:
1. Confirm the integration is set up under **Devices & Services**
2. Restart Home Assistant
3. Check the HA log for errors from `vent_control`

### Blueprint import fails

Ensure you're pasting the **raw** GitHub URL (starts with
`https://raw.githubusercontent.com/`). If the repo is private, copy the
YAML file manually to `config/blueprints/automation/vent_control/` inside
the HA container.
