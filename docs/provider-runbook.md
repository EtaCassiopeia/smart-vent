# Provider runbook

You're the **provider**: you assemble kits and ship them to clients.
A kit is one Pi + one SLZB-07 dongle + N vents (XIAO ESP32-C6 + SG90
servo + louver) + printed paperwork.

This runbook walks through every step from blank hardware to a
boxed-and-labeled kit ready to ship. The client does only one thing:
plug it in and commission their vents through the Home Assistant
app.

Everything here uses the `smart-vent-provision` CLI. If you want to
understand **why** any step is the way it is, jump to
[`handbook.md`](handbook.md). If you want the developer flow (build
firmware from source, hand-flash, hand-commission), see
[`runbook.md`](runbook.md).

---

## 1. One-time setup (laptop)

You'll need this set up once on your laptop. After that every kit
is just §3.

### 1.1 Tools

```
python3 (>= 3.11)
pip
sudo                          # the image subcommand writes to /dev/sdX
xz, dd                        # ship with any Debian/Ubuntu/macOS install
espflash (>= 3.0)             # cargo install espflash --version '^3'
SD-card reader                # USB or built-in
```

The `flash` and `capture` subcommands talk to XIAO ESP32-C6 boards
over USB. Plug each XIAO **directly** into your laptop — not via a
hub. The SMLIGHT SLZB-07 dongle goes in the client's Pi, not your
laptop.

### 1.2 Install the CLI

```bash
pip install --user \
  https://github.com/EtaCassiopeia/smart-vent/releases/download/provision-v0.1.0/smart_vent_provision-0.1.0-py3-none-any.whl

# Verify:
smart-vent-provision --version
smart-vent-provision --help
```

Subsequent releases publish at the same URL pattern. The CLI
auto-resolves to the latest `firmware-v*` and `hub-v*` releases when
you don't pin a tag.

---

## 2. What goes into a kit

| Item | Source | Notes |
|---|---|---|
| Raspberry Pi (4 or 5) | Off-the-shelf | Any model with USB + WiFi or Ethernet |
| SD card (≥ 16 GB) | Off-the-shelf | Class 10 / A1 recommended |
| SMLIGHT SLZB-07 USB dongle | <https://smlight.tech> | Thread radio for OTBR |
| N × XIAO ESP32-C6 boards | <https://www.seeedstudio.com> | One per vent |
| N × SG90 servos | Off-the-shelf | One per vent |
| N × vent louver assemblies | Per-house (3D-print or buy) | The mechanical part |
| Printed sticker sheet | `provision labels` (Avery 5160) | One QR sticker per vent |
| Printed quick-start card | `provision kit-card` | Goes in the box |

---

## 3. Prep one kit (per-client workflow)

You'll spend roughly **30 minutes per kit** of six vents once
you've done a couple. Sequence matters — flash before capture,
capture before stickers.

### 3.1 Bake the SD card (~5 min once cached)

Plug an SD card into your laptop. Find the device path:

```bash
# Linux:
lsblk
# macOS:
diskutil list
```

Triple-check you've got the right device — the next step **wipes
everything on it**.

```bash
sudo smart-vent-provision image --device /dev/sdX
# Or pin to a specific hub release:
sudo smart-vent-provision image --device /dev/sdX --hub-tag hub-v0.1.0
```

The CLI:
1. Downloads the `.img.xz` from the latest `hub-v*` GitHub release
   (cached at `~/.cache/smart-vent/hub/` so future kits are fast).
2. sha256-verifies it against the published `.sha256`.
3. Streams `xz | dd` onto the device. Refuses to write to anything
   that isn't a whole-disk block device (catches the common
   `/dev/sdX1` partition mistake).

Eject the card. It's now a complete hub-in-a-card: Pi OS Lite +
docker + the three containers (OTBR / matter-server / Home
Assistant) + the first-boot WiFi wizard + the seeded HA dashboard.

### 3.2 Flash + capture the vents (~30 s/vent after the first)

Pick a `kit-id` for this client. Default is
`kit-<yyyymmdd>-<uid>` if you don't pass one, but a human-readable
id like `kit-acme-2026-06-001` makes the printed paperwork friendlier.

```bash
smart-vent-provision batch \
  --count 6 \
  --kit-id kit-acme-2026-06-001 \
  --label-hints 'living room,living room,study,study,bedroom 1,basement'
```

`batch` walks you through each board:

1. **BOOT-hold + replug** — hold the XIAO's B button, plug in, release.
   The CLI auto-detects the board on `/dev/ttyACM0`.
2. **Flash** — espflash writes bootloader + partition table + app
   (~10 s). Uses the cached firmware release from
   `~/.cache/smart-vent/firmware/`.
3. **Power-cycle** — unplug + replug, NO BOOT hold this time.
4. **Capture** — CLI reads 45 s of serial, pulls the EUI-64, Matter
   QR payload, and manual pairing code from the boot banner.

Inventory accumulates at `./kits/kit-acme-2026-06-001/inventory.json`.
The `--label-hints` text is purely cosmetic — it gets printed on
the sticker so you can match physical vents to rooms during assembly.
**It does NOT assign vents to rooms.** That's the client's job at
commissioning time.

If a vent's BOOT-hold doesn't take, you'll see an espflash timeout.
Re-do the BOOT dance and the CLI retries. If a serial capture times
out after 45 s, the firmware booted but didn't log the expected
lines — power-cycle again (the boot banner reprints) and the next
capture picks it up.

### 3.3 Print the sticker sheet + kit-card

```bash
smart-vent-provision labels   --kit kit-acme-2026-06-001
smart-vent-provision kit-card --kit kit-acme-2026-06-001 \
    --support-contact 'help@yourcompany.example'
```

Outputs:
- `kits/kit-acme-2026-06-001/labels.pdf` — Avery 5160-compatible
  sheet, one QR sticker per vent. Print on an Avery 5160 sheet,
  apply one sticker per physical vent (the EUI last-4 on the
  sticker matches what `inventory.json` lists, so you can sanity-
  check).
- `kits/kit-acme-2026-06-001/kit-card.pdf` — one-page client
  quick-start. Plug-in, WiFi setup, install HA app, commission
  each vent.

If your kit ships with a per-kit AP password (baked into the SD
image via the `userconf.txt` mechanism or by editing
`/etc/smart-vent/ap-password` post-bake), pass it through
`--ap-password 'xxxx'` so the kit-card shows it.

### 3.4 Physical assembly

For each vent:
1. Solder/screw the XIAO + servo onto the louver assembly per your
   mechanical design.
2. Stick the sticker for that board on the visible side of the
   vent housing.
3. Power-test once: USB into laptop, watch for the boot banner.
   Same EUI-64 as the sticker means the right sticker is on the
   right board.

Plug the SLZB-07 dongle into one of the Pi's USB ports.

### 3.5 Pack and ship

In the box:
- Pi with SD card inserted, SLZB-07 already plugged in
- Power supply for the Pi (USB-C PD, 5 V / 3 A recommended)
- N vents, stickered
- Printed kit-card
- Optional: printed `inventory.json` as a backup record

---

## 4. The client side (what your shipment does on arrival)

The client's flow, in order:

1. **Plug in the Pi.** Wait ~30 s. The first-boot wizard publishes
   an AP named `smart-vent-setup-<short-eui>`.
2. **Join the AP from a phone.** The captive page asks for the
   client's home WiFi name + password.
3. **Wait for reboot.** The Pi joins their WiFi; the three docker
   containers come up.
4. **Install Home Assistant on the phone** (App Store / Play Store).
   Sign in to the hub on the local network.
5. **For each vent: scan the QR sticker.** HA's Matter integration
   pairs the vent over BLE, hands off Thread credentials via the
   SLZB-07, and the vent joins the mesh. Client picks the room
   when prompted.

The kit-card walks them through it. Anything past step 5 (per-vent
control, automations, schedules) is regular HA usage; the seeded
Vents dashboard is in the sidebar.

---

## 5. Troubleshooting (provider side)

### 5.1 `image` subcommand: "device is not a block device"

Either you passed a regular file path (typo) or you passed a
partition like `/dev/sdb1`. Pass the whole disk: `/dev/sdb`.

### 5.2 `image` subcommand: sha256 mismatch

The cached download is corrupt. Delete `~/.cache/smart-vent/hub/`
and retry; the CLI re-downloads.

### 5.3 `flash`: espflash times out at "Connecting…"

The XIAO isn't in download mode. Hold B, replug, release B —
retry.

### 5.4 `capture`: 45 s timeout, missing one or more fields

The firmware booted but didn't print one of EUI / QR / pairing
code. Most likely the board hasn't actually rebooted — power-cycle
it (unplug + replug, no BOOT) and rerun `capture` for that one
board.

### 5.5 SLZB-07 not detected during a client smoke test

Confirm the client's Pi sees it: `lsusb -d 10c4:ea60` and
`ls /dev/ttyUSB0`. If both are present but OTBR isn't leader, the
`ip6_tables` modules might not be loaded — the SD image installs
them, but a kernel update could mask the file. `lsmod | grep ip6_`
should show both `ip6_tables` and `ip6table_filter`.

### 5.6 GitHub rate-limit during release fetch

Unauthenticated GitHub API allows 60 requests/hour. If you're
prepping many kits in a row and hit a limit, set
`GH_TOKEN=<your-pat>` in the environment — `hub_release.py` and
`release.py` (firmware) honor it automatically via the `requests`
library.

### 5.7 Inventory.json drifted from the physical labels

`inventory.json` is hand-editable. Reorder vents to match
sticker-to-room physical assembly, fix typos in `label_hint`, then
re-run `labels` / `kit-card` to regenerate the PDFs.

---

## 6. What's *not* the provider's job

- **Commissioning the vents** — that's the client, via the HA app,
  by scanning each sticker after the Pi is on WiFi.
- **Picking rooms / floors** — same. The provider's `--label-hints`
  is just text on the sticker; the actual `area_id` is whatever the
  client picks when adding the vent in HA.
- **OTA firmware updates** — not in v1 yet. When a new
  `firmware-v*` ships, the provider re-flashes vents at kit-prep
  time; existing fielded vents stay on whatever they shipped with
  until that's solved.
- **Building from source** — you should never need to. The CLI
  pulls release artifacts; the runbook (`docs/runbook.md`)
  documents the source-build path for developers only.

---

## 7. References

- [`handbook.md`](handbook.md) — conceptual: how Matter + Thread fit
  together, what's happening inside the firmware, what a vent
  command actually traverses.
- [`runbook.md`](runbook.md) — developer flow. Build firmware from
  source, hand-flash, hand-commission. Useful when you're hacking
  on the project, not when you're prepping kits.
- [`mobile-api.md`](mobile-api.md) — the hub's WS + REST surface.
  Useful if you ever want to write automation that talks to the
  hub directly (Slack bot, monitoring, custom dashboard).
- [`mobile-app-spec.md`](mobile-app-spec.md) — deferred reference
  for a future branded mobile app. Not part of v1.
- [`../tools/provision/README.md`](../tools/provision/README.md) —
  the CLI's own README with subcommand reference.
