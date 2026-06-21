#!/bin/bash -e
# Stage prerun: clone previous stage's rootfs forward + drop the smart-vent
# source into the chroot at /usr/src/smart-vent so the 00-install step can
# call install.sh from there.

echo "stage-smart-vent: PREV_ROOTFS_DIR=${PREV_ROOTFS_DIR:-<unset>}"
echo "stage-smart-vent: ROOTFS_DIR=${ROOTFS_DIR:-<unset>}"
if [ -d "${PREV_ROOTFS_DIR:-/nonexistent}" ]; then
    echo "stage-smart-vent: PREV_ROOTFS_DIR contents (first 10):"
    ls "${PREV_ROOTFS_DIR}" | head -10
else
    echo "stage-smart-vent: PREV_ROOTFS_DIR does NOT exist."
fi

if [ ! -d "${ROOTFS_DIR}" ]; then
    echo "stage-smart-vent: calling copy_previous"
    copy_previous
    echo "stage-smart-vent: copy_previous returned $?"
fi

if [ ! -d "${ROOTFS_DIR}/etc" ]; then
    echo "stage-smart-vent: ROOTFS_DIR/etc does not exist after copy_previous; copy_previous must have failed." >&2
    echo "stage-smart-vent: ROOTFS_DIR contents:" >&2
    ls -la "${ROOTFS_DIR}" >&2 || true
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
