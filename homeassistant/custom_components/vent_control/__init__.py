"""Smart Vent Control integration for Home Assistant."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall

from .const import DOMAIN
from .coordinator import VentCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.COVER]

SERVICE_SET_FLOOR = "set_floor"
SERVICE_SET_ROOM = "set_room"

SERVICE_SET_FLOOR_SCHEMA = vol.Schema(
    {
        vol.Required("floor"): str,
        vol.Required("position"): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=100)
        ),
    }
)

SERVICE_SET_ROOM_SCHEMA = vol.Schema(
    {
        vol.Required("room"): str,
        vol.Required("position"): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=100)
        ),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Vent Control from a config entry."""
    coordinator = VentCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services once (on first config entry)
    if not hass.services.has_service(DOMAIN, SERVICE_SET_FLOOR):
        async def handle_set_floor(call: ServiceCall) -> None:
            floor = call.data["floor"]
            position = call.data["position"]
            for coord in hass.data[DOMAIN].values():
                await coord.async_set_floor_position(floor, position)
                await coord.async_request_refresh()

        async def handle_set_room(call: ServiceCall) -> None:
            room = call.data["room"]
            position = call.data["position"]
            for coord in hass.data[DOMAIN].values():
                await coord.async_set_room_position(room, position)
                await coord.async_request_refresh()

        hass.services.async_register(
            DOMAIN, SERVICE_SET_FLOOR, handle_set_floor, schema=SERVICE_SET_FLOOR_SCHEMA
        )
        hass.services.async_register(
            DOMAIN, SERVICE_SET_ROOM, handle_set_room, schema=SERVICE_SET_ROOM_SCHEMA
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    # Unregister services when last entry is removed
    if not hass.data[DOMAIN]:
        hass.services.async_remove(DOMAIN, SERVICE_SET_FLOOR)
        hass.services.async_remove(DOMAIN, SERVICE_SET_ROOM)

    return unload_ok
