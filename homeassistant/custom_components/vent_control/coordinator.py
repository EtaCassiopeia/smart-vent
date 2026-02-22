"""Data update coordinator for vent devices."""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path
from typing import Any

import aiosqlite
import cbor2
from aiocoap import Context, Message
from aiocoap.numbers.codes import Code

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_DB_PATH, CONF_POLL_INTERVAL, DEFAULT_DB_PATH, DEFAULT_POLL_INTERVAL, DOMAIN

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
        self._target_angles: dict[str, int] = {}  # address -> target angle

    async def _async_setup(self) -> None:
        """Set up the CoAP client context."""
        self._coap_context = await Context.create_client_context()

    async def _read_device_addresses(self) -> list[str]:
        """Read device IPv6 addresses from the hub's SQLite database."""
        db_path = self._entry.data.get(CONF_DB_PATH, DEFAULT_DB_PATH)

        if not Path(db_path).exists():
            _LOGGER.warning("Hub database not found at %s", db_path)
            return []

        try:
            async with aiosqlite.connect(f"file:{db_path}?mode=ro", uri=True) as db:
                async with db.execute(
                    "SELECT ipv6_address FROM devices WHERE ipv6_address != ''"
                ) as cursor:
                    rows = await cursor.fetchall()
                    return [row[0] for row in rows]
        except Exception as err:
            _LOGGER.error("Failed to read hub database: %s", err)
            return []

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Poll all known vent devices."""
        if self._coap_context is None:
            await self._async_setup()

        # Read device addresses from hub's SQLite database
        addresses = await self._read_device_addresses()

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

    @staticmethod
    def _cbor_get(data: Any, index: int, default: Any = None) -> Any:
        """Get a value from a CBOR response (array or map)."""
        if isinstance(data, list):
            return data[index] if index < len(data) else default
        return data.get(index, default)

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
                result["angle"] = self._cbor_get(data, 0, 90)
                state_names = {0: "open", 1: "closed", 2: "partial", 3: "moving"}
                result["state"] = state_names.get(self._cbor_get(data, 1, 1), "closed")

                # Carry over stored target angle for direction detection
                if address in self._target_angles:
                    result["target_angle"] = self._target_angles[address]
                    # Clear target once movement completes
                    if result["state"] != "moving":
                        del self._target_angles[address]
        except Exception:
            return None

        # Get identity
        try:
            msg = Message(code=Code.GET, uri=f"coap://[{address}]/device/identity")
            resp = await self._coap_context.request(msg).response
            if resp.code.is_successful():
                data = cbor2.loads(resp.payload)
                result["eui64"] = self._cbor_get(data, 0, "")
                result["firmware_version"] = self._cbor_get(data, 1, "")
                result["uptime_s"] = self._cbor_get(data, 2, 0)
        except Exception:
            pass

        # Get config
        try:
            msg = Message(code=Code.GET, uri=f"coap://[{address}]/device/config")
            resp = await self._coap_context.request(msg).response
            if resp.code.is_successful():
                data = cbor2.loads(resp.payload)
                result["room"] = self._cbor_get(data, 0, "") or ""
                result["floor"] = self._cbor_get(data, 1, "") or ""
                result["name"] = self._cbor_get(data, 2, "") or ""
        except Exception:
            pass

        # Get health
        try:
            msg = Message(code=Code.GET, uri=f"coap://[{address}]/device/health")
            resp = await self._coap_context.request(msg).response
            if resp.code.is_successful():
                data = cbor2.loads(resp.payload)
                result["rssi"] = self._cbor_get(data, 0, 0)
                result["poll_period_ms"] = self._cbor_get(data, 1, 0)
                power_sources = {0: "usb", 1: "battery"}
                result["power_source"] = power_sources.get(self._cbor_get(data, 2, 0), "usb")
                result["free_heap"] = self._cbor_get(data, 3, 0)
                result["battery_mv"] = self._cbor_get(data, 4)
        except Exception:
            pass

        return result

    async def async_set_vent_position(self, address: str, angle: int) -> bool:
        """Set a vent's target position."""
        if self._coap_context is None:
            return False

        angle = max(90, min(180, angle))
        payload = cbor2.dumps([angle])
        msg = Message(
            code=Code.PUT,
            uri=f"coap://[{address}]/vent/target",
            payload=payload,
            content_format=60,
        )

        try:
            resp = await self._coap_context.request(msg).response
            if resp.code.is_successful():
                self._target_angles[address] = angle
                return True
            return False
        except Exception as err:
            _LOGGER.error("Failed to set position for %s: %s", address, err)
            return False
