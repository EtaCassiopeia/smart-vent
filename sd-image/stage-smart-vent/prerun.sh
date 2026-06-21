#!/bin/bash -e
# Standard pi-gen prerun: clone the previous stage's rootfs forward.
# Same pattern as upstream stage1/stage2 prerun.sh — the smart-vent
# bits get layered on by the substages below.

if [ ! -d "${ROOTFS_DIR}" ]; then
    copy_previous
fi
