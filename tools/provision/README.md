# smart-vent-provision

Provider-side CLI for prepping smart-vent kits.

## Phases — separate by design

This tool is responsible for the **provider** workflow: writing firmware
to boards and gathering the artifacts needed to print stickers for each
vent. It does **not** commission anything. Commissioning (pairing a vent
to a Matter fabric and assigning it to a room) is the **client's** job,
done from the smart-vent mobile app at install time.

| Phase | Owned by | Tool | Effect |
|---|---|---|---|
| Flash | Provider | `smart-vent-provision flash` | Writes firmware to the ESP32-C6 via `espflash`. Nothing else. |
| Capture | Provider | `smart-vent-provision capture` | Reads the post-boot serial log, records each board's EUI-64 / Matter QR / pairing code into a per-kit `inventory.json`. |
| Label | Provider | `smart-vent-provision labels` | Renders an Avery 5160 sticker sheet from the inventory. Sticker goes on the physical vent. |
| Quick-start | Provider | `smart-vent-provision kit-card` | Renders the one-page card that ships in the box. |
| SD image | Provider | `smart-vent-provision image` | Pulls the hub `.img.xz` from the latest `hub-v*` GitHub release, sha256-verifies it, and `xz \| dd`s it onto the SD card. |
| **Commission** | **Client** | **smart-vent mobile app** | **Scans the sticker QR, pairs the vent into the client's HA fabric, picks the room/floor.** |

The mobile app is a separate project (Flutter, single codebase for
Android + iOS). It talks to the client's hub via `matter-server`'s
WebSocket API and HA's REST API. It is not part of this CLI.

## Install

The CLI is published as a Python wheel via the repo's release pipeline.
Until that wheel lands, install from this repo:

```bash
cd tools/provision
pip install --user -e .

# Optional dev deps for running the tests:
pip install --user -e ".[dev]"
```

External dependency: **espflash** must be on `PATH`.

```bash
cargo install espflash --version '^3'
```

## Usage

### Flash a board (just the firmware bits)

```bash
# Single board
smart-vent-provision flash

# Several in a row
smart-vent-provision flash --count 6
```

The CLI prompts you to BOOT-hold + replug, then runs espflash. Repeat
for as many boards as `--count`. No inventory is written.

### Capture a board's identity for the sticker

After flashing, power-cycle the board (NO BOOT hold) so it emits a
fresh boot banner, then:

```bash
smart-vent-provision capture --kit-id kit-acme-2026-06-001
# optional cosmetic hint (purely what gets printed on the sticker)
smart-vent-provision capture --kit-id kit-acme-2026-06-001 --label-hint 'study'
```

This reads `/dev/ttyACM0` for up to 45s, pulls the EUI-64, Matter QR
payload, and manual pairing code from the boot log, and appends to
`./kits/<kit-id>/inventory.json`.

### Flash + capture in one walk (convenience)

```bash
smart-vent-provision batch --count 6 \
  --kit-id kit-acme-2026-06-001 \
  --label-hints 'living room,living room,study,study,bedroom 1,basement'
```

Walks: BOOT-hold prompt → flash → power-cycle prompt → capture, for
each of N boards. The label-hints are purely cosmetic printed text;
they do **not** assign vents to rooms.

### Print stickers + client card

```bash
smart-vent-provision labels   --kit kit-acme-2026-06-001  # -> labels.pdf
smart-vent-provision kit-card --kit kit-acme-2026-06-001 \
  --ap-password 'changeMe' --support-contact 'help@smart-vent.example'
```

### Write the SD card

```bash
# Pulls the latest hub-v* GH release, sha256-verifies, dd's onto /dev/sdb.
sudo smart-vent-provision image --device /dev/sdb

# Pin to a specific tag instead of latest:
sudo smart-vent-provision image --device /dev/sdb --hub-tag hub-v0.1.0
```

Refuses to write to anything that isn't a whole-disk block device
(catches the common `/dev/sdb1` partition mistake) and prompts for
confirmation before clobbering the device. `--yes` skips the prompt
for automation. Needs `xz` and `dd` on `PATH` — both ship in any
Debian/Ubuntu base install.

## Inventory schema

```json
{
  "kit_id": "kit-acme-2026-06-001",
  "firmware_version": "firmware-v0.1.0",
  "hub_image_version": "",
  "vents": [
    {
      "eui64": "58:e6:c5:01:0a:dc",
      "qr": "MT:Y3.13OTB00KA0648G00",
      "manual_code": "34970112332",
      "label_hint": "study"
    }
  ]
}
```

Hand-editable. Fix typos, add cosmetic hints, reorder before printing.
`label_hint` is **just sticker text** — the client app decides the
actual room during commissioning.

## Limitations (v1)

- One board at a time. No parallel flash jig (BOOT-hold is still
  manual). Operator target: <30 s/board after the first.
- `image` subcommand (write SD card) deferred — depends on the Pi hub
  SD image, which is the next workstream.
- Per-vent unique Matter passcodes deferred to v2 (per-device factory
  NVS partitions via `mfg_tool`). v1 uses the SDK default passcode.

## Tests

```bash
pytest tools/provision/tests -q
```

No hardware needed — release fetch is mocked, label/QR rendering is
deterministic.
