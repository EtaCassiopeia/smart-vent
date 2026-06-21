#!/bin/bash -e
# Stage prerun: clone previous stage's rootfs forward + drop the smart-vent
# source into the chroot at /usr/src/smart-vent so the 00-install step can
# call install.sh from there.

if [ ! -d "${ROOTFS_DIR}" ]; then
    copy_previous
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
