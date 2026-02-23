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

## Identifying Your Device

During setup, if you have multiple vents, use the **identify** feature to determine which physical vent corresponds to which device in the app:

1. In the ecosystem app, trigger "Identify" on the device
2. The vent's servo will **wiggle back and forth** for ~10 seconds
3. Look for the vent that's moving to confirm the match

This works from:
- **chip-tool**: `chip-tool identify identify 1 1 10`
- **Home Assistant**: Click the identify icon on the device page
- **Google Home / Alexa**: Check device settings for an identify option
