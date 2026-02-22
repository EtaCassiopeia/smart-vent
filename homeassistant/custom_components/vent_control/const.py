"""Constants for the Vent Control integration."""

DOMAIN = "vent_control"

CONF_HUB_HOST = "hub_host"
CONF_HUB_PORT = "hub_port"
CONF_POLL_INTERVAL = "poll_interval"
CONF_DB_PATH = "db_path"

DEFAULT_HUB_HOST = "localhost"
DEFAULT_HUB_PORT = 5683
DEFAULT_POLL_INTERVAL = 30
DEFAULT_DB_PATH = "/config/devices.db"

# Vent angle range
ANGLE_CLOSED = 90
ANGLE_OPEN = 180
