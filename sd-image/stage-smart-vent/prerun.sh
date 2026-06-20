#!/bin/bash -e
# Stage prerun: clone previous stage's rootfs forward + drop the smart-vent
# source into the chroot at /usr/src/smart-vent so the 00-install step can
# call install.sh from there.

if [ ! -d "${ROOTFS_DIR}" ]; then
    copy_previous
fi

# SMART_VENT_SRC_HOST is set by the CI workflow to the path of the
# repo checkout on the build runner. We copy the source into the
# chroot rather than bind-mounting so the image is self-contained
# during the chroot install.
if [ -z "${SMART_VENT_SRC_HOST:-}" ]; then
    echo "stage-smart-vent: SMART_VENT_SRC_HOST is not set; aborting" >&2
    exit 1
fi
if [ ! -d "${SMART_VENT_SRC_HOST}/pi" ]; then
    echo "stage-smart-vent: SMART_VENT_SRC_HOST=${SMART_VENT_SRC_HOST} does not look like a smart-vent checkout" >&2
    exit 1
fi

mkdir -p "${ROOTFS_DIR}/usr/src/smart-vent"
rsync -a \
    --exclude '.git' \
    --exclude 'firmware/vent-controller/target' \
    --exclude '**/__pycache__' \
    --exclude '**/.venv' \
    "${SMART_VENT_SRC_HOST}/" "${ROOTFS_DIR}/usr/src/smart-vent/"
