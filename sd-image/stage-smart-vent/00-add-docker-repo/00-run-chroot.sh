#!/bin/bash -e
# Install Docker's official apt repo into the chroot so the next
# substage can apt-install docker-ce + docker-compose-plugin. Debian
# Bookworm doesn't ship docker-compose-plugin in main.

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

codename="$(. /etc/os-release && echo "${VERSION_CODENAME}")"
arch="$(dpkg --print-architecture)"
echo "deb [arch=${arch} signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian ${codename} stable" \
    > /etc/apt/sources.list.d/docker.list

apt-get update
