# Multi-Admin Setup

Matter supports multi-admin — a single vent device can be controlled by multiple ecosystems simultaneously (e.g., Google Home + Home Assistant, or Alexa + Apple Home).

## How It Works

Each ecosystem is a separate **fabric**. When a device is commissioned into a fabric, it receives that fabric's credentials and can communicate with controllers on that fabric. A Matter device can belong to up to 5 fabrics simultaneously.

State changes from any fabric are reflected to all others. If Google Home opens a vent, Home Assistant sees it as open.

## Adding a Second Ecosystem

### Step 1: Commission into the first ecosystem

Follow the setup guide for your primary ecosystem:
- [Google Home](google-home-setup.md)
- [Alexa](alexa-setup.md)
- [Home Assistant Matter](home-assistant-matter.md)

### Step 2: Open a commissioning window

From the first ecosystem, open a commissioning window so the second ecosystem can join:

**From Google Home:**
1. Open device settings
2. **Linked Matter apps & services** → **Link new app**

**From Alexa:**
1. Open device settings in the Alexa app
2. **Matter** → **Enable pairing mode**

**From Home Assistant:**
1. Go to **Settings** → **Devices & Services** → **Matter**
2. Select the device → **Open commissioning window**

**From chip-tool:**
```bash
chip-tool pairing open-commissioning-window <node-id> 1 300 1000 3840
```
(Opens window for 300 seconds with discriminator 3840)

### Step 3: Commission from the second ecosystem

In the second ecosystem's app, add a new Matter device. It will find the vent via BLE (the commissioning window enables BLE advertising temporarily).

## Supported Combinations

| Primary | Secondary | Notes |
|---------|-----------|-------|
| Google Home | Home Assistant | Recommended for HA dashboard + voice control |
| Google Home | Alexa | Both voice ecosystems |
| Alexa | Home Assistant | Recommended for HA dashboard + voice control |
| Apple Home | Home Assistant | Requires Apple TV or HomePod as Thread border router |
| Home Assistant | Google Home | Commission HA first, then open window for Google |

## Limitations

- Maximum 5 fabrics per device
- Each ecosystem manages Thread credentials independently
- Factory reset clears all fabrics — device must be re-commissioned to each
- Some ecosystems may show slightly different device names or categories
