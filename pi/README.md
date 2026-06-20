# Pi hub runtime

Everything in this directory ends up at `/opt/smart-vent/` on a
provisioned Pi. It's the "what runs on the hub" half of the
deployment plan (workstream B), replacing the three hand-typed
`docker run` commands in `docs/runbook.md` §3.

## Layout (growing — current state)

```
pi/
  docker-compose.yaml          OTBR + matter-server + Home Assistant
  .env.example                 Backbone interface + future config knobs
  systemd/
    smart-vent.service         Bring the compose up at boot (after first-boot)
    smart-vent-firstboot.service  AP-mode wizard, runs until .configured exists
  README.md                    this file
```

Next steps (separate commits, each one its own reviewable artifact):

- `install.sh` — idempotent installer for a fresh Raspberry Pi OS
- `firstboot/` — Flask-based AP-mode WiFi capture wizard (or a
  `comitup` adapter if the spike pans out)
- `config/homeassistant/` — seed HA config copied from the existing
  `homeassistant/` templates

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
