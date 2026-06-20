#!/usr/bin/env bash
# install.sh — idempotent installer for the smart-vent Pi runtime.
#
# Run paths:
#
#   # From a fresh Pi over the network:
#   curl -sSL https://raw.githubusercontent.com/EtaCassiopeia/smart-vent/main/pi/install.sh \
#       | sudo bash
#
#   # From a local checkout (developer flow, also what the SD image builder uses):
#   sudo SMART_VENT_SRC=$(pwd) bash pi/install.sh
#
# Optional args:
#   --tag <ref>         git ref to clone (default: latest hub-v* tag)
#   --skip-wizard       Mark .configured immediately, skip first-boot WiFi
#                       onboarding. For SD images that ship with WiFi
#                       creds pre-seeded, or for wired-Ethernet installs.
#   --from-source DIR   Same as setting SMART_VENT_SRC.
#
# Re-running is safe — every step is idempotent.

set -euo pipefail

# --------------------------------------------------------------- defaults
REPO_URL="https://github.com/EtaCassiopeia/smart-vent"
INSTALL_DIR="/opt/smart-vent"
DATA_DIR="/opt/smart-vent/data"
STATE_DIR="/var/lib/smart-vent"
SYSTEMD_DIR="/etc/systemd/system"

TAG=""
SKIP_WIZARD=0
SRC_DIR="${SMART_VENT_SRC:-}"

# ------------------------------------------------------------- arg parse
while [[ $# -gt 0 ]]; do
  case "$1" in
    --tag) TAG="$2"; shift 2 ;;
    --skip-wizard) SKIP_WIZARD=1; shift ;;
    --from-source) SRC_DIR="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,/^set/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "install.sh: unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

# ------------------------------------------------------------- helpers
say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31mxx\033[0m %s\n' "$*" >&2; exit 1; }

require_root() {
  [[ $EUID -eq 0 ]] || die "must run as root (try: sudo bash $0)"
}

preflight() {
  if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    case "${ID:-}${ID_LIKE:-}" in
      *raspbian*|*debian*|*ubuntu*) ;;
      *)
        warn "OS is '${PRETTY_NAME:-unknown}'. install.sh targets Raspberry Pi OS / Debian. Continuing, but you may need to adjust by hand."
        ;;
    esac
  fi

  case "$(uname -m)" in
    aarch64|arm*|x86_64) ;;
    *)
      warn "uname -m reports '$(uname -m)'. Docker images target arm64/armhf/amd64; YMMV."
      ;;
  esac
}

# ----------------------------------------------------------- apt packages
install_packages() {
  say "Installing system packages (docker, compose plugin, AP-mode wizard deps)..."
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y --no-install-recommends \
    ca-certificates curl git \
    docker.io docker-compose-plugin \
    hostapd dnsmasq \
    python3 python3-flask \
    network-manager
  systemctl enable --now docker.service >/dev/null
}

# ----------------------------------------------------- get source on disk
fetch_source() {
  if [[ -n "$SRC_DIR" ]]; then
    [[ -f "$SRC_DIR/pi/docker-compose.yaml" ]] || die "SMART_VENT_SRC=$SRC_DIR does not look like a smart-vent checkout"
    say "Using local source: $SRC_DIR"
    return
  fi

  # Resolve tag if not pinned.
  if [[ -z "$TAG" ]]; then
    TAG=$(curl -sSL "https://api.github.com/repos/EtaCassiopeia/smart-vent/tags?per_page=100" \
      | grep -oE '"name":\s*"hub-v[^"]+"' \
      | head -n1 \
      | sed -E 's/.*"(hub-v[^"]+)".*/\1/' || true)
    if [[ -z "$TAG" ]]; then
      warn "No hub-v* tag published yet; falling back to main."
      TAG="main"
    fi
  fi

  SRC_DIR=$(mktemp -d -t smart-vent-XXXXXX)
  say "Cloning $REPO_URL @ $TAG into $SRC_DIR..."
  git clone --depth 1 --branch "$TAG" "$REPO_URL" "$SRC_DIR"
}

# ----------------------------------------------------- lay down /opt + state
deploy_files() {
  say "Deploying to $INSTALL_DIR ..."
  mkdir -p "$INSTALL_DIR" "$STATE_DIR"

  # Container data dirs live under $DATA_DIR so the operator can back
  # them up with tar and edit HA's config in place. Created with
  # restrictive permissions; HA / matter-server / OTBR run as root
  # inside their containers, so the host-side ownership doesn't
  # block them.
  mkdir -p "$DATA_DIR/otbr" "$DATA_DIR/matter-server" "$DATA_DIR/homeassistant"
  chmod 700 "$DATA_DIR/matter-server"   # has Matter fabric credentials

  # Copy the pi/ tree (and only the pi/ tree) under /opt/smart-vent/pi/.
  # rsync so an upgrade-in-place doesn't drop file modes the systemd
  # units depend on, and so we don't blow away $DATA_DIR (--exclude).
  rsync -a --delete --exclude '/data' "$SRC_DIR/pi/" "$INSTALL_DIR/pi/"

  # Seed .env from .env.example if no operator-edited .env yet.
  if [[ ! -f "$INSTALL_DIR/pi/.env" ]]; then
    cp "$INSTALL_DIR/pi/.env.example" "$INSTALL_DIR/pi/.env"
  fi
}

# --------------------------------------------- seed Home Assistant config
# Seeds /opt/smart-vent/data/homeassistant/ with:
#   - configuration.yaml from pi/config/homeassistant/
#   - scripts.yaml, automations.yaml, helpers/, dashboards/ from the
#     repo's top-level homeassistant/ templates (same content used by
#     people who manually copy them into a stock HA install)
# Never overwrites an existing configuration.yaml — operator edits win.
seed_homeassistant_config() {
  local target="$DATA_DIR/homeassistant"
  if [[ -f "$target/configuration.yaml" ]]; then
    say "HA config exists at $target/configuration.yaml; leaving it alone."
    return
  fi

  say "Seeding HA bootstrap config into $target ..."
  install -m 0644 "$SRC_DIR/pi/config/homeassistant/configuration.yaml" \
    "$target/configuration.yaml"

  # Copy the template files in (scripts.yaml, automations.yaml, etc.).
  mkdir -p "$target/helpers" "$target/dashboards"
  install -m 0644 "$SRC_DIR/homeassistant/scripts.yaml"     "$target/scripts.yaml"
  install -m 0644 "$SRC_DIR/homeassistant/automations.yaml" "$target/automations.yaml"
  install -m 0644 "$SRC_DIR/homeassistant/helpers/schedule_helpers.yaml" \
    "$target/helpers/schedule_helpers.yaml"
  install -m 0644 "$SRC_DIR/homeassistant/dashboards/vents.yaml" \
    "$target/dashboards/vents.yaml"
}

# ----------------------------------------------------- systemd units
install_units() {
  say "Installing systemd units..."
  install -m 0644 "$INSTALL_DIR/pi/systemd/smart-vent.service" "$SYSTEMD_DIR/smart-vent.service"
  install -m 0644 "$INSTALL_DIR/pi/systemd/smart-vent-firstboot.service" "$SYSTEMD_DIR/smart-vent-firstboot.service"
  systemctl daemon-reload
  systemctl enable smart-vent.service >/dev/null

  if [[ "$SKIP_WIZARD" -eq 1 ]]; then
    say "Skipping first-boot wizard (--skip-wizard); marking .configured."
    touch "$STATE_DIR/.configured"
    systemctl disable smart-vent-firstboot.service >/dev/null 2>&1 || true
  else
    systemctl enable smart-vent-firstboot.service >/dev/null
  fi
}

# ----------------------------------------------------- pre-pull images
prepull_images() {
  say "Pre-pulling docker images (so first boot doesn't need internet)..."
  # Compose v2 plugin has `pull`.
  (cd "$INSTALL_DIR/pi" && docker compose pull --quiet) || warn "image pre-pull failed; will retry at first boot"
}

# ----------------------------------------------------- summary
print_summary() {
  echo
  say "smart-vent runtime installed at $INSTALL_DIR/pi"
  echo "    compose:   $INSTALL_DIR/pi/docker-compose.yaml"
  echo "    state:     $STATE_DIR (.configured = onboarding flag)"
  echo "    units:     $SYSTEMD_DIR/smart-vent{,-firstboot}.service"

  if [[ "$SKIP_WIZARD" -eq 1 ]]; then
    echo
    echo "    First-boot wizard SKIPPED. Reboot or run:"
    echo "        sudo systemctl start smart-vent.service"
  else
    echo
    echo "    On next boot the Pi will publish an AP named"
    echo "        smart-vent-setup-<short-eui>"
    echo "    Connect with your phone and follow the captive page to"
    echo "    enter your home WiFi credentials."
  fi
}

# ============================================================= main
require_root
preflight
install_packages
fetch_source
deploy_files
seed_homeassistant_config
install_units
prepull_images
print_summary
