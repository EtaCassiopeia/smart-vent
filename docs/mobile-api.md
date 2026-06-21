# Mobile-app API contract

The smart-vent mobile app talks to a client's hub over the LAN. It
does **not** speak Matter or BLE itself — the Pi (`matter-server`)
handles BLE commissioning and the Matter fabric. The app's surface
area is two HTTP/WS endpoints exposed by the hub.

This document is the contract the [smart-vent-app](#) Flutter repo
builds against. Anything the app touches lives here.

## Endpoints exposed by the hub

| URL | Server | Purpose |
|---|---|---|
| `ws://<hub>:5580/ws` | `matter-server` | Commissioning (BLE PASE → fabric → CASE), node attribute reads/writes. JSON-over-WebSocket. |
| `http://<hub>:8123/api/...` | Home Assistant | Areas, floors, entities, services. Long-lived access token auth. |
| `_smart-vent._tcp.local.` (mDNS) | hub | Discovery. Advertised by HA's mDNS service plus a small helper on the Pi (TBD; not yet implemented). |

`<hub>` is either the mDNS-resolved hostname (e.g. `smart-vent.local`)
or a manual IP the user enters during onboarding.

## Auth model

- **HA**: long-lived access token. The app obtains one via HA's
  built-in OAuth-style flow on first run, stores it in
  keychain/keystore, sends it as `Authorization: Bearer <token>` on
  every REST call.
- **matter-server**: no auth. The WS is open to anything that can
  reach `localhost:5580` on the hub. The hub is on the LAN behind
  the home router; we trust the LAN perimeter. (Future hardening: a
  small reverse proxy on the Pi that requires the HA token for
  matter-server too.)

## Discovery: mDNS

The hub advertises:

```
_smart-vent._tcp.local.   port=8123
   txt: version=hub-v0.1.0
        ha_ws=ws://<hub>:8123/api/websocket
        matter_ws=ws://<hub>:5580/ws
```

App's first-run flow: browse for `_smart-vent._tcp.local.`, present
matches to the user, fall back to a manual-IP input. If multiple
hubs are on the same LAN, the app shows the list and lets the user
pick.

## matter-server WebSocket

On connect, the server sends a "hello" message with its info, then
the app sends commands. The library docs at
<https://github.com/home-assistant-libs/python-matter-server> have
the full schema. The app needs three commands.

### `commission_with_code`

The core of "add a vent": app scanned the sticker, has a Matter QR
payload (or the equivalent manual pairing code), sends:

```json
{
  "message_id": "uuid-1",
  "command": "commission_with_code",
  "args": {
    "code": "MT:Y3.13OTB00KA0648G00",
    "network_only": false
  }
}
```

`network_only: false` means full BLE PASE + Thread credential push +
CASE handoff. The server streams progress events back via the same
WS, and finally returns the assigned `node_id`.

Response shape (the success case):

```json
{
  "message_id": "uuid-1",
  "result": { "node_id": 14, "available": true }
}
```

Failure: `result` absent, `error_code` set. Common codes:

| code | meaning | what the app should do |
|---|---|---|
| `pairing_failed` | BLE PASE didn't complete | Power-cycle the vent (resets the 15-min fast-adv window), retry |
| `address_resolve_failed` | Thread credentials pushed but mDNS/CASE timed out | Wait 30s and re-attempt; OTBR may still be propagating |
| `node_already_exists` | The same QR code was paired before | Treat as success; fetch the existing node by EUI64 |

### `get_nodes`

List of nodes the fabric knows about. The app uses this to:
- Show "X vents commissioned" on the home screen.
- Skip commissioning if the user re-scans a sticker that's already
  paired.

```json
{
  "message_id": "uuid-2",
  "command": "get_nodes",
  "args": {}
}
```

Response: `result` is a list of node dicts with `node_id`,
`available`, and `attributes` (a flat map of `<endpoint>/<cluster>/<attr>`
→ value).

### `device_command`

Send a command to a node. The app's "test the vent" button uses
this after commissioning to confirm the vent moves.

```json
{
  "message_id": "uuid-3",
  "command": "device_command",
  "args": {
    "node_id": 14,
    "endpoint_id": 1,
    "cluster_id": 258,
    "command_name": "DownOrClose",
    "payload": {}
  }
}
```

`258` is the WindowCovering cluster ID.

## Home Assistant REST API

After commissioning, the app talks to HA to:
1. Create the Area for the vent's room (if it doesn't exist) and
   the Floor it belongs to.
2. Move the new cover entity into that Area.
3. Rename the entity to `cover.<room>_vent_<n>`.

All via REST + WebSocket. Two endpoints matter most.

### `GET /api/states`

Lists every entity HA knows about. The app filters
`startswith("cover.")` and `attributes.friendly_name contains "Vent"`
to find the just-commissioned cover.

Auth: `Authorization: Bearer <long-lived-token>`.

### `POST /api/services/<domain>/<service>`

Service call. The app uses three:

| call | purpose |
|---|---|
| `cover.open_cover` / `cover.close_cover` | "Test the vent" buttons during onboarding |
| `cover.set_cover_position` | Per-vent slider in the UI |

### Area + floor CRUD: WebSocket API

HA's REST API doesn't cover area/floor management; the WS API does.
URL: `ws://<hub>:8123/api/websocket`. The app sends the token in
the auth handshake.

| ws command | purpose |
|---|---|
| `config/area_registry/list` | List existing Areas (so the app can show "pick an existing room" UX before offering "create new"). |
| `config/area_registry/create` | Create an Area (room). Args: `name`, `floor_id?`. |
| `config/floor_registry/list` | List Floors. |
| `config/floor_registry/create` | Create a Floor. Args: `name`. |
| `config/device_registry/update` | Set a device's `area_id`. Args: `device_id`, `area_id`. |
| `config/entity_registry/update` | Rename an entity. Args: `entity_id`, `new_entity_id`, `name`. |

Full WS message schema is in HA's developer docs at
<https://developers.home-assistant.io/docs/api/websocket/>.

## Error model

Both servers return errors in the same shape over WS:

```json
{ "message_id": "uuid", "error_code": "...", "details": "..." }
```

HA REST errors are HTTP status + JSON body with `message`. App should
display the `details` / `message` verbatim on a failure screen — both
servers' messages are end-user actionable.

## Versioning

- `mDNS TXT version=hub-v0.1.0` tells the app what hub it's talking
  to. The app uses this to bail out cleanly if it meets a hub that's
  newer than it knows about.
- This document is versioned with the repo; bumping breaking changes
  to the contract goes via PR review.

## Out of scope (today)

- **Phone-side BLE PASE.** The app doesn't run a Matter SDK; the Pi
  does the BLE pairing. The phone just has to be on the same LAN
  as the Pi during commissioning.
- **Hub bootstrap.** Joining the hub to the home WiFi is the Pi's
  first-boot wizard (`pi/firstboot/`); the app isn't involved.
- **Voice integrations.** Out of v1 scope per the design plan.
