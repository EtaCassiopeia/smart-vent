# ADR-002: Dual-Protocol Architecture (CoAP + Matter)

**Status:** Accepted
**Date:** 2025-05-15

## Context

The Smart Vent system originally used CoAP over Thread as its sole application protocol, with a Python hub CLI and Home Assistant custom component for control. Adding Matter support enables interoperability with major ecosystems (Google Home, Alexa, Apple Home) and Home Assistant's built-in Matter integration.

However, the Matter Window Covering cluster exposes only position control. It does not cover the extended telemetry and operational features the CoAP API provides:

- **RSSI** — radio signal strength for mesh health monitoring
- **Free heap** — firmware memory diagnostics
- **Power source** — USB vs battery detection
- **Room / floor assignment** — per-device location metadata
- **Batch operations** — the hub CLI's `set-room` and `set-floor` commands control groups of devices in a single call

Replacing CoAP entirely with Matter would lose these capabilities with no standard Matter equivalent.

## Decision

Run both CoAP and Matter simultaneously over the same Thread network interface. Both protocols share the same `AppState` (defined in `state.rs`) protected by a `Mutex`. Cross-protocol sync ensures state changes from either side are reflected:

- **CoAP → Matter:** When a CoAP `PUT /vent/target` updates `AppState`, the CoAP handler calls `matter::report_operational_status()` to push the new position to the Matter fabric.
- **Matter → CoAP:** When a Matter `GoToLiftPercentage` command arrives, the Matter callback writes to `AppState`. The next CoAP `GET /vent/position` reads the updated state.

The Matter SDK manages the OpenThread stack internally. CoAP continues to operate on port 5683 on the same Thread interface.

## Consequences

**Positive:**
- Gradual migration path — existing CoAP users keep full functionality while gaining Matter ecosystem access.
- Extended telemetry preserved — hub CLI and HA custom component continue to report RSSI, heap, power source, and room/floor data.
- Multi-ecosystem control — a vent can be controlled from Google Home, Alexa, Apple Home, HA Matter, and the CoAP hub simultaneously without conflict.

**Negative:**
- Two code paths to maintain — bug fixes and new features may need to be applied to both CoAP handlers and Matter callbacks.
- Increased firmware binary size — the Matter SDK adds significant flash footprint alongside the existing CoAP stack.
- Potential for transient state inconsistency — a brief window exists between an `AppState` update and the cross-protocol notification where one protocol may report a stale value.

## References

- `firmware/vent-controller/src/state.rs` — `AppState`, `with_app_state()` mutex accessor
- `firmware/vent-controller/src/coap.rs` — CoAP handlers, calls `matter::report_operational_status()` after state changes
- `firmware/vent-controller/src/matter.rs` — Matter callbacks, `on_position_change` writes to `AppState`
- [Architecture: Dual-Protocol Architecture](../architecture.md#41-dual-protocol-architecture)
- [ADR-001](001-thread-credential-provisioning.md) — Thread credential provisioning via Matter BLE
