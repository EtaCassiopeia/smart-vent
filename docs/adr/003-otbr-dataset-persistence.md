# ADR-003: OTBR Dataset Persistence for Legacy Deployments

**Status:** Accepted
**Date:** 2025-05-15

## Context

The OTBR runs as a Docker container on the Raspberry Pi. When the container is removed (`docker rm otbr`) and recreated, the Thread operational dataset — including the network key, Extended PAN ID, and other credentials — is lost. Running `dataset init new` generates an entirely new dataset, silently orphaning any devices that joined the previous network.

The `setup_otbr.sh` script did not persist the dataset or warn users about this behavior. Users who recreated the OTBR container (e.g., to change the backbone interface or update the image) discovered that all their devices were unreachable, with no obvious recovery path.

Matter-commissioned devices (see [ADR-001](001-thread-credential-provisioning.md)) are unaffected by this issue because they receive Thread credentials dynamically from the commissioner at commission time and can be recommissioned to a new network. However, legacy CoAP-only devices have their credentials hardcoded in firmware and cannot re-provision without reflashing.

## Decision

Two-layer persistence for the OTBR dataset:

1. **Container-level persistence (Docker volume):** The `setup_otbr.sh` script adds `-v otbr-data:/var/lib/thread` to the `docker run` command. This Docker named volume survives `docker rm otbr` and is automatically reattached on `docker run`, preserving the dataset across container recreations.

2. **File-level backup (for disaster recovery):** After the Thread network is formed, the script exports the active dataset to `~/.thread/dataset-backup.txt` and sets permissions to `chmod 600`. On subsequent runs, if the OTBR state is `disabled` (fresh container with no network formed), the script checks for the backup file and restores the dataset automatically.

For Matter users, neither layer is needed — recommissioning provisions new credentials. The dataset persistence is specifically for legacy CoAP deployments where reflashing is the only alternative.

## Consequences

**Positive:**
- Idempotent script — `setup_otbr.sh` can be re-run safely. If the container exists, it is replaced; the Docker volume preserves state. If the volume is also lost, the file backup restores the dataset.
- No silent credential loss — users are warned about the backup file location and its contents.
- Clear migration path — the commissioning guide documents Matter commissioning as the recommended alternative to credential management.

**Negative:**
- The backup file (`~/.thread/dataset-backup.txt`) contains the Thread network key in plaintext hex. If an attacker obtains this file, they can join the Thread network. The file is protected with `chmod 600` but users must ensure their Pi's filesystem security is adequate.
- The Docker volume name (`otbr-data`) is a convention — users who run multiple OTBRs or use non-standard Docker setups may need to adjust.

## References

- `tools/scripts/setup_otbr.sh` — backup/restore implementation
- [Commissioning guide: Legacy CoAP](../guides/commissioning.md#legacy-coap-commissioning) — dataset volatility warning
- [ADR-001](001-thread-credential-provisioning.md) — Matter commissioning as the recommended alternative
