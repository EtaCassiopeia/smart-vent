#!/bin/bash -e
# Run install.sh inside the chroot. The source was copied in by prerun.sh.
#
# Notes:
#   - Compose `pull` will fail (no docker daemon in chroot); install.sh
#     already treats it as a warning, so the bake doesn't abort.
#   - smart-vent.service and smart-vent-firstboot.service get enabled.
#     They start on the actual Pi's first boot, not during the bake.
#   - SD-image version comes from the IMG_NAME suffix; CI passes
#     SMART_VENT_VERSION through so we can stamp /etc/smart-vent/version.

on_chroot << EOF
set -e
export DEBIAN_FRONTEND=noninteractive

mkdir -p /etc/smart-vent
echo "${SMART_VENT_VERSION:-dev}" > /etc/smart-vent/version

SMART_VENT_SRC=/usr/src/smart-vent \
    bash /usr/src/smart-vent/pi/install.sh
EOF
