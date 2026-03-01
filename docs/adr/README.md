# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for the Smart Vent Control System. ADRs capture the context, decision, and consequences of significant architectural choices so that future contributors understand *why* the system is built the way it is.

## Convention

Each ADR is a numbered Markdown file (`NNN-short-title.md`) with this structure:

```
# ADR-NNN: Title

**Status:** Accepted | Superseded | Deprecated
**Date:** YYYY-MM-DD

## Context
What is the issue or force motivating this decision?

## Decision
What is the change that we're proposing or have agreed to?

## Consequences
What becomes easier or harder as a result of this decision?

## References
Links to code, PRs, or external resources.
```

- A new ADR is created for each significant architectural decision.
- Once accepted, ADRs are not modified (except to update status). A new ADR supersedes the old one if the decision changes.
- Keep ADRs concise — a reader should understand the decision in under 5 minutes.

## Index

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [001](001-thread-credential-provisioning.md) | Thread Credential Provisioning via Matter BLE | Accepted | 2025-05-15 |
| [002](002-dual-protocol-architecture.md) | Dual-Protocol Architecture (CoAP + Matter) | Accepted | 2025-05-15 |
| [003](003-otbr-dataset-persistence.md) | OTBR Dataset Persistence for Legacy Deployments | Accepted | 2025-05-15 |
