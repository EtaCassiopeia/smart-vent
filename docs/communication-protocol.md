# Communication Protocol

## Transport

- **Protocol**: CoAP (RFC 7252) over UDP/IPv6
- **Encoding**: CBOR (RFC 8949) for all payloads
- **Network**: Thread 802.15.4 mesh
- **Port**: 5683 (CoAP default)

## CoAP Resources

### `GET /vent/position`

Returns current vent position and state.

**Response (CBOR):**
```json
{
  "angle": 90,
  "state": "closed"
}
```

| Field | Type | Values |
|-------|------|--------|
| `angle` | u8 | 90–180 |
| `state` | str | `"open"`, `"closed"`, `"partial"`, `"moving"` |

---

### `PUT /vent/target`

Set target vent position. Servo moves gradually to target.

**Request (CBOR):**
```json
{
  "angle": 135
}
```

| Field | Type | Constraints |
|-------|------|------------|
| `angle` | u8 | 90–180 (clamped) |

**Response (CBOR):**
```json
{
  "angle": 135,
  "state": "moving",
  "previous_angle": 90
}
```

---

### `GET /device/identity`

Returns permanent device identification.

**Response (CBOR):**
```json
{
  "eui64": "00:11:22:33:44:55:66:77",
  "firmware_version": "0.1.0",
  "uptime_s": 3600
}
```

---

### `GET /device/config`

Returns user-configurable device settings.

**Response (CBOR):**
```json
{
  "room": "bedroom",
  "floor": "2",
  "name": "bedroom-east"
}
```

### `PUT /device/config`

Update device configuration. Partial updates supported — only include fields to change.

**Request (CBOR):**
```json
{
  "room": "living-room",
  "floor": "1"
}
```

**Response (CBOR):** Updated full config (same format as GET).

---

### `GET /device/health`

Returns device health telemetry.

**Response (CBOR):**
```json
{
  "rssi": -65,
  "poll_period_ms": 5000,
  "power_source": "usb",
  "free_heap": 180000,
  "battery_mv": null
}
```

| Field | Type | Notes |
|-------|------|-------|
| `rssi` | i8 | Average RSSI of parent link in dBm (via otThreadGetParentAverageRssi). -128 if unavailable |
| `poll_period_ms` | u32 | SED poll period (0 if always-on) |
| `power_source` | str | `"usb"` or `"battery"` |
| `free_heap` | u32 | Free heap in bytes |
| `battery_mv` | u16? | Battery voltage, null if USB |

## Response Codes

| Code | Meaning |
|------|---------|
| 2.05 Content | Successful GET |
| 2.04 Changed | Successful PUT |
| 4.00 Bad Request | Invalid CBOR or out-of-range values |
| 4.04 Not Found | Unknown resource path |
| 5.00 Internal Server Error | Device error |

## Discovery

Devices are discovered via the OTBR REST API:

1. Hub queries `GET /node/dataset/active` to verify network
2. Hub queries `GET /node/rloc` for mesh-local addresses
3. Hub sends CoAP `GET /device/identity` to each discovered address
4. New devices (unknown EUI-64) added to registry

## Multicast

All vent devices join the Thread multicast group `ff03::1` (realm-local all nodes).

For broadcast operations (e.g., "close all vents"), the hub sends a CoAP PUT to the multicast address. Devices process the request but do not send individual responses to multicast PUTs.

## CBOR Schema (shared-protocol)

```rust
// Vent position (GET /vent/position response)
struct VentPosition {
    angle: u8,      // 90-180
    state: String,  // "open"|"closed"|"partial"|"moving"
}

// Target request (PUT /vent/target request)
struct TargetRequest {
    angle: u8,      // 90-180
}

// Target response (PUT /vent/target response)
struct TargetResponse {
    angle: u8,
    state: String,
    previous_angle: u8,
}

// Device identity (GET /device/identity response)
struct DeviceIdentity {
    eui64: String,
    firmware_version: String,
    uptime_s: u32,
}

// Device config (GET/PUT /device/config)
struct DeviceConfig {
    room: Option<String>,
    floor: Option<String>,
    name: Option<String>,
}

// Device health (GET /device/health response)
struct DeviceHealth {
    rssi: i8,
    poll_period_ms: u32,
    power_source: String,
    free_heap: u32,
    battery_mv: Option<u16>,
}
```
