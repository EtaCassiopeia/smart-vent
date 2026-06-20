# smart-vent-provision

Provider-side CLI for prepping smart-vent kits.

It pulls a tagged firmware release from this repo, flashes the boards
one at a time (interactively), captures each board's QR + EUI + manual
pairing code into a per-kit `inventory.json`, then generates printable
PDFs (sticker sheet + client quick-start card).

## Install

The CLI is published as a Python wheel; until then, install from this
repo:

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

```bash
# 1. Flash a batch of vents. Walks through one board at a time.
smart-vent-provision flash --count 6 \
  --rooms 'living_room,living_room,study,study,bedroom_1,basement'
# Writes ./kits/kit-2026-06-20-abc123/inventory.json

# 2. Print sticker sheet (Avery 5160).
smart-vent-provision labels --kit kit-2026-06-20-abc123 --out labels.pdf

# 3. Print the client quick-start card.
smart-vent-provision kit-card --kit kit-2026-06-20-abc123 \
  --ap-password 'changeMe' --support-contact 'help@smart-vent.example'
```

## Per-vent flow

For each board the CLI prompts:

1. Hold BOOT, replug USB, release BOOT (download mode).
2. CLI runs `espflash flash --partition-table ... --bootloader ... <app>`.
3. Power-cycle the board (unplug + replug, no BOOT).
4. CLI tails `/dev/ttyACM0` for 45s waiting on the boot banner; pulls
   EUI-64, QR payload, and manual pairing code from the log.
5. Appends to the kit `inventory.json` with the room hint passed via
   `--rooms`.

## Inventory schema

```json
{
  "kit_id": "kit-2026-06-20-abc123",
  "firmware_version": "firmware-v0.1.0",
  "hub_image_version": "",
  "vents": [
    {
      "eui64": "58:e6:c5:01:0a:dc",
      "qr": "MT:Y3.13OTB00KA0648G00",
      "manual_code": "34970112332",
      "label_hint": "living_room"
    }
  ]
}
```

Hand-editable: fix typos, add hints, reorder. The PDF generators read
this verbatim.

## Limitations (v1)

- One board at a time. No parallel-flash jig yet (BOOT-hold is still
  manual per board).
- `image` subcommand (write SD card) deferred — depends on the Pi
  hub image, which is the next workstream.
- Per-vent unique Matter passcodes deferred to v2 (factory NVS
  partitions + `mfg_tool`). v1 uses the SDK default passcode, like the
  Pi-side runbook.

## Tests

```bash
pytest tools/provision/tests -q
```

No hardware needed — release fetch is mocked, label/QR rendering is
deterministic.
