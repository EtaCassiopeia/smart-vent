# Home Assistant config templates

These files are **examples** you copy into your live HA config directory
(the one mounted into the `homeassistant` container as `/config` — per
`docs/runbook.md` §3.3, typically `~/homeassistant/` on the Pi). They are
not loaded from this repo directly.

Each commissioned vent shows up as a Matter `cover.*` entity once the
Matter integration is configured. Grouping, scheduling, and dashboards
all rely on HA's native primitives — Areas (rooms), Floors, Schedule
helpers, automations — no custom component is needed.

## File map

| File | Purpose | Where it goes |
|---|---|---|
| `scripts.yaml` | Reusable group-control scripts (close-by-floor, open-by-room, set-position) | `~/homeassistant/scripts.yaml` (or append into existing one) |
| `automations.yaml` | Time-based automations — both styles (raw time triggers + schedule-helper triggers) | `~/homeassistant/automations.yaml` |
| `helpers/schedule_helpers.yaml` | Weekly recurring schedule helpers used by the schedule-style automations | `~/homeassistant/helpers/schedule_helpers.yaml` (and include from `configuration.yaml`) |
| `dashboards/vents.yaml` | Lovelace dashboard grouping vents by floor → room | `~/homeassistant/dashboards/vents.yaml` (and register from `configuration.yaml` under `lovelace.dashboards`) |

## Before you copy

Replace these placeholders with your own values from HA:

- `area_id: living_room` → use the Area slug HA assigned (see
  Settings → Areas, zones & labels → Areas; the slug is shown when
  you click an area).
- `floor_id: main_floor` → same idea under the Floors tab.
- `entity_id: cover.living_room_vent_1` → the actual cover entity name
  HA gave your commissioned vent. Find it in Settings → Devices &
  services → Matter → click the device → entity list. Rename to a
  consistent `cover.<room>_vent_<n>` pattern via the entity's
  settings dialog.

## Reloading

After copying files into `~/homeassistant/`:

```
# In HA UI: Developer Tools → YAML → reload each of:
#   - Scripts
#   - Automations
#   - Schedule
#   - Lovelace dashboards
```

Or `docker restart homeassistant` for a full reload. Watch
`docker logs -f homeassistant` for YAML syntax errors.

## See also

- `docs/runbook.md` §7 — Area / floor assignment on the device side
- `docs/runbook.md` §7.5 — group control and scheduling workflow
- `docs/handbook.md` — why grouping lives in HA, not on the device
