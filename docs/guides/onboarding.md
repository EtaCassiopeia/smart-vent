# Onboarding Decision Tree

Choose how to add your smart vent to your smart home ecosystem.

## Which Ecosystem?

```
                    ┌─────────────────────┐
                    │  Which ecosystem(s) │
                    │  do you want to use?│
                    └─────────┬───────────┘
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
    ┌─────▼─────┐      ┌─────▼─────┐      ┌─────▼─────┐
    │  Google    │      │  Amazon   │      │  Apple    │
    │  Home     │      │  Alexa    │      │  Home     │
    └─────┬─────┘      └─────┬─────┘      └─────┬─────┘
          │                   │                   │
          ▼                   ▼                   ▼
    google-home-         alexa-              Requires Apple
    setup.md            setup.md            TV or HomePod
          │                   │              as Thread BR
          │                   │                   │
          └───────┬───────────┘                   │
                  │                               │
           ┌──────▼──────┐                        │
           │ Also want   │                        │
           │ Home Asst.? │                        │
           └──────┬──────┘                        │
              Yes │                               │
                  ▼                               │
         home-assistant-  ◄───────────────────────┘
         matter.md
         (multi-admin)
```

## Quick Start by Ecosystem

### Google Home Only
1. [Flash firmware](flash-firmware.md)
2. [Commission via Google Home](google-home-setup.md)
3. Done — use voice commands and app

### Alexa Only
1. [Flash firmware](flash-firmware.md)
2. [Commission via Alexa](alexa-setup.md)
3. Done — use voice commands and app

### Home Assistant Only (Matter)
1. [Flash firmware](flash-firmware.md)
2. [Commission via HA Matter](home-assistant-matter.md)
3. Done — use HA dashboard and automations

### Home Assistant Only (CoAP, legacy)
1. [Flash firmware](flash-firmware.md)
2. [Commission via CoAP](commissioning.md#legacy-coap-commissioning)
3. Install custom component
4. Done — use HA dashboard with extended telemetry

### Google Home + Home Assistant
1. [Flash firmware](flash-firmware.md)
2. [Commission via Google Home](google-home-setup.md) (primary)
3. [Add HA as second admin](multi-admin.md)
4. Done — voice commands via Google + dashboards via HA

### Alexa + Home Assistant
1. [Flash firmware](flash-firmware.md)
2. [Commission via Alexa](alexa-setup.md) (primary)
3. [Add HA as second admin](multi-admin.md)
4. Done — voice commands via Alexa + dashboards via HA

### All Ecosystems
1. [Flash firmware](flash-firmware.md)
2. Commission via first ecosystem
3. [Add second ecosystem](multi-admin.md)
4. Repeat for third (up to 5 fabrics)

## Choosing Between Matter and CoAP for Home Assistant

If you're using Home Assistant, you can connect vents via **Matter** (built-in integration), **CoAP** (custom component), or **both**. Here's how they compare:

| | Matter | CoAP (Custom Component) | Both |
|---|---|---|---|
| **Setup complexity** | Scan QR code in HA | Configure OTBR credentials, install hub, install custom component | Both setup steps |
| **Thread credential resilience** | Credentials provisioned dynamically — survives OTBR recreation | Hardcoded — OTBR recreation orphans devices ([ADR-001](../adr/001-thread-credential-provisioning.md)) | Matter path is resilient; CoAP path needs backup |
| **Multi-ecosystem support** | Google Home, Alexa, Apple Home, HA simultaneously | Home Assistant only | Full multi-ecosystem via Matter |
| **Extended telemetry** | Standard Matter attributes only | RSSI, free heap, power source, room/floor | Full telemetry via CoAP |
| **Batch operations** | Per-device only | `set-room`, `set-floor` via hub CLI | Batch via CoAP hub CLI |

**Recommendations:**
- **New installations** → use Matter. It's simpler to set up and doesn't require credential management.
- **Existing CoAP installations** → add Matter alongside CoAP. You gain multi-ecosystem support without losing telemetry. See [ADR-002](../adr/002-dual-protocol-architecture.md) for how dual-protocol works.
- **Need extended telemetry** → use both. Matter handles ecosystem interop; CoAP provides the health data and batch commands.

## Identifying Your Device

During setup, if you have multiple vents, use the **identify** feature to determine which physical vent corresponds to which device in the app:

1. In the ecosystem app, trigger "Identify" on the device
2. The vent's servo will **wiggle back and forth** for ~10 seconds
3. Look for the vent that's moving to confirm the match

This works from:
- **chip-tool**: `chip-tool identify identify 1 1 10`
- **Home Assistant**: Click the identify icon on the device page
- **Google Home / Alexa**: Check device settings for an identify option
