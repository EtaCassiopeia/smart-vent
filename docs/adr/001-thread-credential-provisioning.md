# ADR-001: Thread Credential Provisioning via Matter BLE

**Status:** Accepted
**Date:** 2025-05-15

## Context

In v0.1.x the firmware hardcodes Thread network credentials (network key, channel, PAN ID, network name) in `ThreadConfig::default()`. The OTBR must be manually configured to match these values, or the firmware must be edited and reflashed to match an existing OTBR dataset.

This coupling creates a critical operational failure mode: when the OTBR Docker container is recreated (e.g., `docker rm otbr` followed by `docker run`), the `dataset init new` command generates a new Extended PAN ID and potentially new credentials. Devices that joined the old network store the full dataset in NVS and will not recognize the new network — they are silently orphaned. The only recovery is to reflash every device.

Thread has a built-in Joiner/Commissioner protocol for dynamic credential provisioning, but it adds operational complexity (running a Commissioner, managing PSKd per device) and is being superseded by Matter for consumer IoT use cases.

## Decision

Use Matter PASE (Password Authenticated Session Establishment) over BLE to provision Thread credentials at commission time. The firmware initializes the Thread stack via `ThreadManager::new_matter_managed()`, which delegates Thread network configuration entirely to the Matter SDK. The device advertises over BLE, the commissioner (Google Home, Alexa, Apple Home, Home Assistant, or chip-tool) establishes a PASE session, and the Thread operational dataset is transferred as part of the Matter commissioning flow.

The firmware never needs compile-time Thread credentials for the Matter path. `ThreadConfig::default()` remains available only for the legacy CoAP path.

## Consequences

**Positive:**
- No credential coupling between firmware and OTBR — OTBR can be recreated without orphaning Matter-commissioned devices (they receive credentials from the commissioner, which obtains them from the Thread border router at commission time).
- Multi-ecosystem support — the same device can be commissioned into Google Home, Alexa, Apple Home, and Home Assistant without firmware changes.
- Standard onboarding UX — users scan a QR code or enter a pairing code, matching the experience of other Matter devices.

**Negative:**
- Requires BLE proximity for initial onboarding — the commissioner must be within BLE range of the device during commissioning.
- The legacy CoAP path still requires hardcoded Thread credentials in `ThreadConfig::default()`. Users who choose CoAP-only must manually ensure OTBR and firmware credentials match (documented with warnings in the commissioning guide).

## References

- `firmware/vent-controller/src/thread.rs` — `new_matter_managed()` constructor
- `components/esp_matter_bridge/matter_bridge.cpp` — `matter_bridge_start()` initializes the Matter stack and BLE advertising
- [Commissioning guide](../guides/commissioning.md) — end-user instructions for both paths
- [ADR-003](003-otbr-dataset-persistence.md) — dataset backup/restore for legacy CoAP deployments
