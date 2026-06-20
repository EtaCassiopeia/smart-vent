# Pi hub runtime

Everything in this directory ends up at `/opt/smart-vent/` on a
provisioned Pi. It's the "what runs on the hub" half of the
deployment plan (workstream B), replacing the three hand-typed
`docker run` commands in `docs/runbook.md` §3.

## Layout (growing — current state)

```
pi/
  docker-compose.yaml   OTBR + matter-server + Home Assistant
  .env.example          Backbone interface + future config knobs
  README.md             this file
```

Next steps (separate commits, each one its own reviewable artifact):

- `systemd/smart-vent.service` — bring the compose up at boot
- `systemd/smart-vent-firstboot.service` — run the AP-mode wizard
  until WiFi is configured
- `install.sh` — idempotent installer for a fresh Raspberry Pi OS
- `firstboot/` — Flask-based AP-mode WiFi capture wizard (or a
  `comitup` adapter if the spike pans out)
- `config/homeassistant/` — seed HA config copied from the existing
  `homeassistant/` templates

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
