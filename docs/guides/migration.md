# Migration Guide: CoAP to Matter

This guide covers migrating from the CoAP-only firmware (v0.1.x) to the Matter-enabled firmware (v0.2.0+).

## What Changes

| Aspect | CoAP-only (v0.1.x) | Matter + CoAP (v0.2.0+) |
|--------|-------------------|------------------------|
| Thread init | Hardcoded credentials in `ThreadConfig` | Matter provisions via BLE commissioning |
| Partition | 1.5MB app (single_app_large) | 1.9MB custom partition |
| BLE | Not used | Used for commissioning |
| Ecosystems | Home Assistant only (custom component) | Google Home, Alexa, Apple Home, HA (Matter + custom) |
| Binary size | ~822KB | ~1.2MB (estimated) |

## Migration Steps

### 1. Back Up Current Config

Before reflashing, note the current device configuration:

```bash
# From the hub
vent-hub get <eui64>
```

Record: room, floor, name assignments.

### 2. Reflash with Matter Firmware

```bash
cd firmware/vent-controller
cargo espflash flash --release --port /dev/cu.usbmodem101 --monitor
```

The device will boot with the new firmware but will **not** have Thread credentials — it needs to be commissioned via Matter.

### 3. Commission via Matter

Follow the commissioning guide for your chosen ecosystem:
- [Google Home](google-home-setup.md)
- [Alexa](alexa-setup.md)
- [Apple Home](home-assistant-matter.md)
- [Home Assistant Matter](home-assistant-matter.md)
- [chip-tool](../guides/commissioning.md)

### 4. Re-apply Configuration

After commissioning, the device joins the Thread network with new credentials. CoAP still works:

```bash
# Assign room/floor via CoAP (hub)
vent-hub assign <eui64> <room> <floor>
```

### 5. Update Home Assistant (Optional)

If using HA, you can switch from the custom component to the built-in Matter integration:

1. Remove the device from the Vent Control custom component
2. Commission into HA's Matter integration
3. The device appears as a standard Cover entity

Or keep both — the custom component continues to work via CoAP alongside Matter.

## Rollback

To revert to CoAP-only firmware:

1. Check out the `v0.1.x` tag
2. Reflash
3. The device uses hardcoded Thread credentials again
4. Run `vent-hub discover` to re-register

## Data Preserved Across Migration

| Data | Preserved? | Notes |
|------|-----------|-------|
| EUI-64 | Yes | Permanent in eFuse |
| NVS (room, floor, name) | Yes | NVS partition not erased during flash |
| Last vent angle | Yes | NVS WAL checkpoint |
| Thread credentials | No | New credentials from Matter commissioning |
| Hub registry | Yes | Hub database unchanged |
