# Pi hub runtime

Everything in this directory ends up at `/opt/smart-vent/` on a
provisioned Pi. It's the "what runs on the hub" half of the
deployment plan (workstream B), replacing the three hand-typed
`docker run` commands in `docs/runbook.md` §3.

## Layout (growing — current state)

```
pi/
  docker-compose.yaml             OTBR + matter-server + Home Assistant
  .env.example                    Backbone interface + future config knobs
  install.sh                      Idempotent installer for a fresh Pi
  systemd/
    smart-vent.service            Bring the compose up at boot (after first-boot)
    smart-vent-firstboot.service  AP-mode wizard, runs until .configured exists
  firstboot/
    wizard.py                     Flask + hostapd + dnsmasq + nmcli onboarding
    templates/, static/           Captive page + styling
    README.md                     Behaviour + debugging notes
  config/
    homeassistant/
      configuration.yaml          HA bootstrap, seeded into data/homeassistant/
  README.md                       this file
```

## Data layout on the Pi

```
/opt/smart-vent/
  pi/                    # everything from this directory, rsync'd here
  data/                  # container state, bind-mounted into the services
    otbr/                # Thread dataset, Thread network state
    matter-server/       # Fabric credentials + matter-server storage (chmod 700)
    homeassistant/       # HA /config — operator can edit in place
```

`install.sh` seeds `data/homeassistant/` with the
`configuration.yaml` from `pi/config/homeassistant/` plus the
`scripts.yaml` / `automations.yaml` / schedule helpers / Vents
dashboard from the repo's top-level `homeassistant/` directory.
Operator edits are preserved on re-install (the seed step only
runs when `configuration.yaml` is absent).

## Install (the script does it all)

```bash
# Curl-piped, latest hub-v* tag:
curl -sSL https://raw.githubusercontent.com/EtaCassiopeia/smart-vent/main/pi/install.sh | sudo bash

# Developer flow (run from inside this repo):
sudo SMART_VENT_SRC=$(pwd) bash pi/install.sh

# Wired-Ethernet install or pre-configured WiFi (skips the wizard):
sudo bash pi/install.sh --skip-wizard
```

The script is idempotent — re-running it upgrades in place without
breaking the existing state.

## Service relationship

On a fresh Pi:

1. Boot → `smart-vent-firstboot.service` runs (no `.configured` flag yet).
   It brings up the AP, captures WiFi creds, joins the network, writes
   `/var/lib/smart-vent/.configured`, and reboots.
2. After reboot → `smart-vent-firstboot.service` is skipped (flag
   present), `smart-vent.service` runs `docker compose up -d`.

`smart-vent.service` is also gated on the flag, so even if the
first-boot service was uninstalled, the main service would refuse to
start without it (avoids the "Pi booted but isn't on the LAN" failure
mode).

## Bring-up (today, manual)

Once we have the systemd units, the install script will do this for
you. For now (developer flow on the existing Pi):

```bash
cp .env.example .env
# edit .env if your LAN is on eth0
docker compose up -d
docker compose ps
```

Verify per `docs/runbook.md` §3.4 (the four-check ladder).
