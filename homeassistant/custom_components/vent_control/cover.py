"""Cover platform for vent control — maps vents to HA cover entities."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ANGLE_CLOSED, ANGLE_OPEN, DOMAIN
from .coordinator import VentCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up vent cover entities from a config entry."""
    coordinator: VentCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for eui64, data in coordinator.data.items():
        entities.append(VentCoverEntity(coordinator, eui64, data))

    async_add_entities(entities, True)


class VentCoverEntity(CoordinatorEntity[VentCoordinator], CoverEntity):
    """A vent represented as a Home Assistant cover entity."""

    _attr_device_class = CoverDeviceClass.DAMPER
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.SET_POSITION
    )

    def __init__(
        self,
        coordinator: VentCoordinator,
        eui64: str,
        data: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._eui64 = eui64
        self._address = data.get("address", "")
        self._attr_unique_id = f"vent_{eui64.replace(':', '')}"
        self._attr_name = data.get("name") or f"Vent {eui64[-5:]}"

        if data.get("room"):
            self._attr_suggested_area = data["room"]

    @property
    def _device_data(self) -> dict[str, Any]:
        return self.coordinator.data.get(self._eui64, {})

    @property
    def current_cover_position(self) -> int | None:
        """Return current position as 0-100%."""
        data = self._device_data
        if not data:
            return None
        angle = data.get("angle", ANGLE_CLOSED)
        return round((angle - ANGLE_CLOSED) / (ANGLE_OPEN - ANGLE_CLOSED) * 100)

    @property
    def is_closed(self) -> bool | None:
        data = self._device_data
        if not data:
            return None
        return data.get("state") == "closed"

    @property
    def is_opening(self) -> bool:
        return self._device_data.get("state") == "moving"

    @property
    def is_closing(self) -> bool:
        return self._device_data.get("state") == "moving"

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the vent fully."""
        await self.coordinator.async_set_vent_position(self._address, ANGLE_OPEN)
        await self.coordinator.async_request_refresh()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the vent fully."""
        await self.coordinator.async_set_vent_position(self._address, ANGLE_CLOSED)
        await self.coordinator.async_request_refresh()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Set vent to a specific position (0-100%)."""
        position = kwargs.get("position", 0)
        angle = ANGLE_CLOSED + round(position / 100 * (ANGLE_OPEN - ANGLE_CLOSED))
        await self.coordinator.async_set_vent_position(self._address, angle)
        await self.coordinator.async_request_refresh()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self._device_data
        return {
            "eui64": self._eui64,
            "angle": data.get("angle"),
            "room": data.get("room", ""),
            "floor": data.get("floor", ""),
            "firmware_version": data.get("firmware_version", ""),
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
