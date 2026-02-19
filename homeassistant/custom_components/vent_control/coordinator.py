"""Data update coordinator for vent devices."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import cbor2
from aiocoap import Context, Message
from aiocoap.numbers.codes import Code

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class VentCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Coordinator to poll vent devices via CoAP."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        poll_interval = entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=poll_interval),
        )
        self._entry = entry
        self._coap_context: Context | None = None
        self._devices: dict[str, dict[str, Any]] = {}

    async def _async_setup(self) -> None:
        """Set up the CoAP client context."""
        self._coap_context = await Context.create_client_context()

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Poll all known vent devices."""
        if self._coap_context is None:
            await self._async_setup()

        # Get device addresses from config entry or discovery
        addresses: list[str] = self._entry.data.get("device_addresses", [])

        updated: dict[str, dict[str, Any]] = {}
        for addr in addresses:
            try:
                device_data = await self._poll_device(addr)
                if device_data:
                    eui64 = device_data.get("eui64", addr)
                    updated[eui64] = device_data
            except Exception as err:
                _LOGGER.debug("Failed to poll %s: %s", addr, err)

        self._devices = updated
        return updated

    async def _poll_device(self, address: str) -> dict[str, Any] | None:
        """Poll a single device for all its data."""
        assert self._coap_context is not None

        result: dict[str, Any] = {"address": address}

        # Get position
        try:
            msg = Message(code=Code.GET, uri=f"coap://[{address}]/vent/position")
            resp = await self._coap_context.request(msg).response
            if resp.code.is_successful():
                data = cbor2.loads(resp.payload)
                result["angle"] = data.get(0, 90)
                state_names = {0: "open", 1: "closed", 2: "partial", 3: "moving"}
                result["state"] = state_names.get(data.get(1, 1), "closed")
        except Exception:
            return None

        # Get identity
        try:
            msg = Message(code=Code.GET, uri=f"coap://[{address}]/device/identity")
            resp = await self._coap_context.request(msg).response
            if resp.code.is_successful():
                data = cbor2.loads(resp.payload)
                result["eui64"] = data.get(0, "")
                result["firmware_version"] = data.get(1, "")
                result["uptime_s"] = data.get(2, 0)
        except Exception:
            pass

        # Get config
        try:
            msg = Message(code=Code.GET, uri=f"coap://[{address}]/device/config")
            resp = await self._coap_context.request(msg).response
            if resp.code.is_successful():
                data = cbor2.loads(resp.payload)
                result["room"] = data.get(0, "")
                result["floor"] = data.get(1, "")
                result["name"] = data.get(2, "")
        except Exception:
            pass

        return result

    async def async_set_vent_position(self, address: str, angle: int) -> bool:
        """Set a vent's target position."""
        if self._coap_context is None:
            return False

        angle = max(90, min(180, angle))
        payload = cbor2.dumps({0: angle})
        msg = Message(
            code=Code.PUT,
            uri=f"coap://[{address}]/vent/target",
            payload=payload,
            content_format=60,
        )

        try:
            resp = await self._coap_context.request(msg).response
            return resp.code.is_successful()
        except Exception as err:
            _LOGGER.error("Failed to set position for %s: %s", address, err)
            return False
