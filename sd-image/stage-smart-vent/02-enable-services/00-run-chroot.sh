#!/bin/bash -e
# Inside-chroot step: enable systemd units + light pre-pull.
# (Docker compose pull deliberately skipped — there's no daemon in the
# chroot. install.sh on an actual Pi handles that at first boot.)

systemctl daemon-reload || true
systemctl enable docker.service
systemctl enable smart-vent.service
systemctl enable smart-vent-firstboot.service
