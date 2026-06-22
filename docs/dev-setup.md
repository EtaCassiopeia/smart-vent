# Dev machine setup

This is the consolidated "what do I install" doc for working on smart-vent.
Tooling instructions used to be scattered across `runbook.md` (which
documents building *on the Pi*), `provider-runbook.md`, and
`hardware/pcb/*/README.md`. This doc is the index; follow the links for
detail, come back here for the overall strategy.

**Recommendation: a Linux x86_64 machine (real box or VM) is the primary
dev machine.** The Raspberry Pi is a deployment target and final
hardware-validation step, not where you iterate. macOS is a fine secondary
choice if you only need PCB design or provisioning-CLI work.

## Why Linux x86_64, not the Pi or macOS

- **Firmware builds**: `.github/workflows/firmware.yml` builds on
  `ubuntu-latest` (x86_64 Linux). A Linux dev machine matches CI exactly.
  It's also dramatically faster than the Pi 4, which is constrained enough
  that `runbook.md` §2.4 has the team add 4GB of swap just to survive the
  Matter SDK + `esp-idf-sys` link step.
- **SD image baking**: `.github/workflows/sd-image.yml` also only runs on
  `ubuntu-latest` (pi-gen + QEMU ARM emulation). A Linux machine can run
  the literal same recipe locally instead of treating it as CI-only.
- **Pi hub runtime**: the OTBR/matter-server/Home Assistant Docker stack
  isn't actually Pi-CPU-specific — the `ip6_tables`/`ip6table_filter`
  kernel modules (`runbook.md` §2.1) are generic Linux, not ARM-only.
- **What still needs the real Pi**: the SLZB-07 802.15.4 dongle's
  USB/BlueZ behavior and real OTBR-over-Thread networking. The Pi is
  "deployment target + final hardware-in-the-loop validation," not
  "where you write code."
- **macOS**: confirmed viable for firmware *builds* (see §1 below) and
  already documented as fine for PCB work (`hardware/pcb/*/README.md`)
  and the provisioning CLI (`provider-runbook.md` §1.1, which already
  uses `diskutil`). Not recommended for SD-image work — that part is
  genuinely Linux-only.

## 1. Firmware (`firmware/vent-controller`, `firmware/shared-protocol`)

```bash
# rustup + nightly + rust-src
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
. "$HOME/.cargo/env"
rustup install nightly
rustup component add rust-src --toolchain nightly

# espup pulls ESP-IDF v5.2.3 + the RISC-V toolchain (pinned in
# firmware/vent-controller/.cargo/config.toml)
cargo install espup
espup install --targets riscv32imac-esp-espidf
. "$HOME/export-esp.sh"   # espup writes this; source it each new shell

# linker proxy + flasher
cargo install ldproxy
cargo install espflash --version '^3'
```

Build:

```bash
cd firmware/vent-controller
RUSTUP_TOOLCHAIN=nightly cargo build --release
```

**Verified working on macOS (Apple Silicon)**, not just assumed: the only
gap from a stock `espup` install was `rust-src` not being added by
default — once added, a clean build finished in ~3 minutes and produced a
valid `riscv32imac-esp-espidf` ELF. This was the open question this issue
started with; it's resolved. Flashing over USB (the rest of "build/flash"
parity with the Pi) wasn't exercised in that pass since no XIAO was
attached — if you hit USB/serial permission issues on Linux, they're
almost always udev rules (`usermod -aG dialout $USER` or similar), not a
toolchain problem.

One more thing worth knowing if you touch the C++ side
(`components/esp_matter_bridge/`): **incremental `cargo build` does not
reliably pick up changes under `extra_components`** (the
`esp-idf-sys` build script's change-detection doesn't track that
directory). If you edit `matter_bridge.cpp`/`.h` and a rebuild finishes
suspiciously fast with no C++ compiler invocations, force it:

```bash
cargo clean -p esp-idf-sys --release   # or --debug, matching your build
cargo build --release
```

This costs a full from-scratch ESP-IDF + Matter SDK rebuild (~1.5 minutes
once toolchains are cached locally; much longer cold) but is the only
reliable way to confirm a C++ change actually compiled.

System packages: mirror `firmware.yml`'s apt list on Debian/Ubuntu —
`build-essential pkg-config libssl-dev libudev-dev libusb-1.0-0-dev
python3 python3-pip python3-venv git curl jq`. On macOS, Xcode Command
Line Tools (`xcode-select --install`) cover the equivalent.

## 2. SD card image (`sd-image/`, `pi/`)

Most devs should just consume the prebuilt `.img.xz` from the latest
`hub-v*` GitHub release (per `provider-runbook.md` §3.1) — this is the
common case and needs nothing beyond `xz`/`dd`/`diskutil`, which is why
the provisioning CLI works fine from macOS too.

If you're actually changing `sd-image/` or `pi/`, you need the local bake
(Linux only — pi-gen + QEMU ARM emulation):

```bash
sudo apt install -y docker.io qemu-user-static binfmt-support
# then mirror sd-image.yml's steps: clone pi-gen at the pinned
# PI_GEN_REF, drop in the smart-vent stage, run pi-gen's build script
# inside Docker.
```

This step has **not been independently re-verified on a fresh Linux
machine as part of this doc** — it's transcribed from `sd-image.yml`,
which is the authoritative source (it does run successfully in CI). If
you hit a discrepancy, trust the workflow file over this paragraph and
send a fix.

## 3. Pi hub runtime (`pi/`, `homeassistant/`)

```bash
sudo apt install -y docker.io docker-compose-plugin \
                    curl wscat avahi-utils bluez \
                    libssl-dev pkg-config build-essential \
                    git python3-pip python3-venv
sudo usermod -aG docker $USER   # log out/in to apply

sudo modprobe ip6_tables
sudo modprobe ip6table_filter
echo 'ip6_tables' | sudo tee /etc/modules-load.d/otbr.conf
echo 'ip6table_filter' | sudo tee -a /etc/modules-load.d/otbr.conf
```

(Transcribed from `runbook.md` §2.1–2.2, which already documents this for
the Pi — it's generic Linux, so it applies the same way to an x86_64 dev
box.) From there, `docker compose up` the same `otbr`/`matter-server`/
`homeassistant` containers described in `runbook.md` §3 for iteration.

**Still real-Pi-only**: the SLZB-07 dongle's USB/BlueZ behavior and actual
over-the-air Thread networking. Plugging the dongle into a Linux dev box
instead of a Pi should work identically in principle (it's just a USB
802.15.4 radio) but hasn't been tried — if you do, it's worth a quick note
back on this doc either way.

## 4. Provisioning CLI + QR generator (`tools/provision`, `tools/qr-generator`)

Already documented as macOS-friendly in `provider-runbook.md` §1.1
(`diskutil` is referenced there); works identically on Linux.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e tools/provision
pip install -r tools/qr-generator/requirements.txt   # or however it's packaged
```

Depends on `espflash` (§1, shared with the firmware toolchain) and
`qrcode[pil]`/`reportlab`.

## 5. PCB tooling (`hardware/pcb/`)

The one area where macOS is just as good a choice as Linux.

**macOS:**
```bash
brew install --cask kicad
```
The cask's `demos` artifact needs interactive sudo and will fail under a
non-interactive script — run it from a real terminal session if prompted,
or ignore the failure (the KiCad app itself installs fine either way).

**Linux:**
```bash
sudo apt install kicad   # or your distro's package; nixpkgs also has it
```

Either way:
```bash
pip install skidl
```

See `hardware/pcb/carrier-board-v1/README.md` for how these get used
(the SKiDL netlist script, `kicad-cli`-based DRC/Gerber pipeline, etc.).

## Nix: not adopted, here's why

Evaluated rather than assumed. The stack splits cleanly into "Nix would
help" and "Nix would fight you":

- **Python** (provisioning CLI, QR generator) and **KiCad** — nixpkgs
  handles both cleanly, especially on Linux.
- **Docker** — an external dependency either way; Nix doesn't replace the
  daemon.
- **Rust + ESP-IDF** — `espup` manages a large prebuilt toolchain
  (compiler, OpenOCD, etc.) outside the Nix store entirely. nixpkgs' own
  Espressif packaging is inconsistent across ESP-IDF versions and the
  pinned `v5.2.3` may not map cleanly to whatever's current in nixpkgs at
  any given time. This is the piece most likely to fight a Nix flake
  rather than benefit from one.

**Decision: don't add a `flake.nix` for now.** The win (reproducible
Python/KiCad environments) doesn't outweigh the cost (onboarding now
requires explaining Nix *and* still shelling out to `espup` for the part
that actually matters most — the firmware toolchain — since that's not
realistically Nix-managed at this pinned version). Revisit if: (a)
nixpkgs' ESP-IDF packaging matures enough to track arbitrary pinned
versions reliably, or (b) the team's onboarding pain shifts toward
Python/KiCad version drift rather than the firmware toolchain, which
isn't what's happened so far.

## Summary by task

| I want to... | Use | Notes |
|---|---|---|
| Build/flash firmware | Linux x86_64 (primary) or macOS (verified, secondary) | §1 |
| Bake a custom SD image | Linux x86_64 only | §2; most devs should use the prebuilt release instead |
| Run the hub stack for dev/test | Linux x86_64 or any Docker host | §3; SLZB-07-specific behavior still needs the real Pi |
| Provision kits (flash + label + image) | macOS or Linux | §4 |
| Design/edit the PCB | macOS or Linux | §5 |
