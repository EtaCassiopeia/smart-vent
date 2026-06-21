#!/bin/bash -e
# Stage prerun: clone previous stage's rootfs forward + drop the smart-vent
# source into the chroot at /usr/src/smart-vent so the 00-install step can
# call install.sh from there.
#
# We don't just call pi-gen's copy_previous because on this pi-gen tag
# (2026-06-18-raspios-bookworm-arm64) PREV_ROOTFS_DIR points at an empty
# work/stage2/rootfs by the time stage-smart-vent runs (the standard
# stages must do something we don't see; copying rsync's only the empty
# dir). Find the most-populated previous stage's rootfs instead and
# rsync from it directly.

echo "stage-smart-vent: ROOTFS_DIR=${ROOTFS_DIR}"
echo "stage-smart-vent: PREV_ROOTFS_DIR=${PREV_ROOTFS_DIR:-<unset>}"
echo "stage-smart-vent: contents of /pi-gen/work:"
find /pi-gen/work -maxdepth 2 -type d | sort
echo "stage-smart-vent: sizes of candidate rootfs dirs:"
du -sh /pi-gen/work/*/rootfs 2>/dev/null || true

SOURCE_ROOTFS=""
for candidate in \
    "${PREV_ROOTFS_DIR:-}" \
    /pi-gen/work/stage2/rootfs \
    /pi-gen/work/stage1/rootfs \
    /pi-gen/work/stage0/rootfs ; do
    [ -z "${candidate}" ] && continue
    if [ -d "${candidate}/etc" ] && [ -d "${candidate}/usr" ]; then
        SOURCE_ROOTFS="${candidate}"
        break
    fi
done

if [ -z "${SOURCE_ROOTFS}" ]; then
    echo "stage-smart-vent: could not find a populated prev-stage rootfs." >&2
    exit 1
fi

echo "stage-smart-vent: using ${SOURCE_ROOTFS} as base rootfs"

mkdir -p "${ROOTFS_DIR}"
rsync -aHAXx --exclude var/cache/apt/archives "${SOURCE_ROOTFS}/" "${ROOTFS_DIR}/"

# Sanity: rootfs is now usable for chroot.
if [ ! -d "${ROOTFS_DIR}/etc" ]; then
    echo "stage-smart-vent: rsync did not populate ${ROOTFS_DIR}/etc; aborting." >&2
    exit 1
fi

# The CI workflow rsyncs the smart-vent checkout into this stage's src/
# directory before pi-gen runs (build-docker.sh wraps the build in a
# container, so arbitrary host paths aren't reachable — but the pi-gen
# tree is). For a local bake, run the same `cp -r ../smart-vent ./src`
# step from the README before kicking off build-docker.sh.
STAGE_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC="${STAGE_DIR}/src"

if [ ! -d "${SRC}/pi" ]; then
    echo "stage-smart-vent: ${SRC} is not a smart-vent checkout; aborting." >&2
    echo "stage-smart-vent: copy the repo into ${SRC} before running pi-gen." >&2
    exit 1
fi

mkdir -p "${ROOTFS_DIR}/usr/src/smart-vent"
rsync -a \
    --exclude '.git' \
    --exclude 'firmware/vent-controller/target' \
    --exclude '**/__pycache__' \
    --exclude '**/.venv' \
    "${SRC}/" "${ROOTFS_DIR}/usr/src/smart-vent/"
