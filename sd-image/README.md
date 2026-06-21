# SD card image bake

Workstream C of the deployment plan: bake a Raspberry Pi OS image that
contains the smart-vent runtime, the systemd units, the first-boot
wizard, and the seeded HA config — so the provider can `dd` it to an
SD card and ship.

The bake re-uses `pi/install.sh` against a Raspberry Pi OS Lite
chroot. install.sh is the single source of truth for the layout —
there is no parallel "what the SD image contains" definition.

## Layout

```
sd-image/
  config                              pi-gen build config (IMG_NAME, stage list, …)
  stage-smart-vent/
    prerun.sh                         rsync the repo into the chroot at /usr/src/smart-vent
    EXPORT_IMAGE                      marker telling pi-gen to export an .img from this stage
    00-install/
      00-run-chroot.sh                run install.sh inside the chroot
```

## How CI uses this

`.github/workflows/sd-image.yml` (added alongside this directory)
on a `hub-v*` tag or manual dispatch:

1. Checks out smart-vent at the tag.
2. Clones [pi-gen](https://github.com/RPi-Distro/pi-gen) into the runner.
3. Drops our `config` and `stage-smart-vent` into pi-gen's tree.
4. Runs pi-gen inside Docker (ARM emulation via QEMU binfmt).
5. Captures `deploy/*.img.xz` + sha256, uploads as a release asset.

Expected runtime on `ubuntu-latest`: ~30–60 min cold.

## How to bake locally (if you have ~30 min and Docker)

```bash
git clone --branch 2026-06-18-raspios-bookworm-arm64 \
  https://github.com/RPi-Distro/pi-gen
cd pi-gen
cp ../smart-vent/sd-image/config ./config
cp -r ../smart-vent/sd-image/stage-smart-vent ./
# Stage the smart-vent source where prerun.sh can find it. build-docker.sh
# only mounts the pi-gen tree into the build container, so we co-locate.
rsync -a \
  --exclude '.git/' \
  --exclude 'firmware/vent-controller/target/' \
  --exclude '**/__pycache__/' --exclude '**/.venv/' \
  ../smart-vent/ stage-smart-vent/src/
echo 'export SMART_VENT_VERSION=dev' >> config
sudo CONTINUE=1 ./build-docker.sh
ls deploy/
```

## Why pi-gen, not packer / nspawn / etc

pi-gen is the official Raspberry Pi tooling, knows the exact partition
layout / bootloader / firstrun.sh shape Pi OS expects, and is what
upstream Raspberry Pi OS releases are built with. Less surprise on
boot.
