#!/bin/bash -e
# Outside-chroot step: copy the smart-vent runtime tree into the rootfs.
# Anything that's just a `cp` / `mkdir` / `chmod` belongs here — keeps
# the next sub-stage (chroot) focused on systemctl + package configuration.

STAGE_DIR_HERE="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${STAGE_DIR_HERE}/src"

if [ ! -d "${SRC}/pi" ]; then
    echo "stage-smart-vent: ${SRC} is not a smart-vent checkout; aborting." >&2
    echo "stage-smart-vent: the CI workflow copies the repo there before bake." >&2
    exit 1
fi

INSTALL_DIR="${ROOTFS_DIR}/opt/smart-vent"
DATA_DIR="${INSTALL_DIR}/data"
STATE_DIR="${ROOTFS_DIR}/var/lib/smart-vent"
SYSTEMD_DIR="${ROOTFS_DIR}/etc/systemd/system"

mkdir -p "${INSTALL_DIR}/pi" "${STATE_DIR}" "${SYSTEMD_DIR}"
mkdir -p "${DATA_DIR}/otbr" "${DATA_DIR}/matter-server" "${DATA_DIR}/homeassistant"
chmod 700 "${DATA_DIR}/matter-server"

# Copy pi/ tree.
rsync -a --delete --exclude '/data' "${SRC}/pi/" "${INSTALL_DIR}/pi/"

# Default .env if none provided.
if [ ! -f "${INSTALL_DIR}/pi/.env" ]; then
    cp "${INSTALL_DIR}/pi/.env.example" "${INSTALL_DIR}/pi/.env"
fi

# Drop systemd units in /etc/systemd/system; enabling happens in the
# next sub-stage (which runs inside chroot so systemctl can update the
# symlink farm).
install -m 0644 "${SRC}/pi/systemd/smart-vent.service"           "${SYSTEMD_DIR}/smart-vent.service"
install -m 0644 "${SRC}/pi/systemd/smart-vent-firstboot.service" "${SYSTEMD_DIR}/smart-vent-firstboot.service"

# OTBR needs ip6_tables + ip6table_filter loaded to route IPv6
# Thread <-> backbone. Persist via modules-load.d so kernel loads
# them on every boot of the baked image.
mkdir -p "${ROOTFS_DIR}/etc/modules-load.d"
install -m 0644 "${SRC}/pi/config/modules-load.d/otbr.conf" \
    "${ROOTFS_DIR}/etc/modules-load.d/otbr.conf"

# Seed Home Assistant config (unless one already exists — preserves
# operator edits on a future re-bake).
HA="${DATA_DIR}/homeassistant"
if [ ! -f "${HA}/configuration.yaml" ]; then
    install -m 0644 "${SRC}/pi/config/homeassistant/configuration.yaml" "${HA}/configuration.yaml"
    mkdir -p "${HA}/helpers" "${HA}/dashboards"
    install -m 0644 "${SRC}/homeassistant/scripts.yaml"                       "${HA}/scripts.yaml"
    install -m 0644 "${SRC}/homeassistant/automations.yaml"                   "${HA}/automations.yaml"
    install -m 0644 "${SRC}/homeassistant/helpers/schedule_helpers.yaml"      "${HA}/helpers/schedule_helpers.yaml"
    install -m 0644 "${SRC}/homeassistant/dashboards/vents.yaml"              "${HA}/dashboards/vents.yaml"
fi

# Version stamp.
mkdir -p "${ROOTFS_DIR}/etc/smart-vent"
echo "${SMART_VENT_VERSION:-dev}" > "${ROOTFS_DIR}/etc/smart-vent/version"
