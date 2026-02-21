"""Async CoAP client for communicating with vent devices."""

from __future__ import annotations

import logging
from typing import Any

import cbor2
from aiocoap import Context, Message
from aiocoap.numbers.codes import Code

from .models import PowerSource, VentDevice, VentState

logger = logging.getLogger(__name__)

# CoAP content format for CBOR
CONTENT_FORMAT_CBOR = 60


class CoapClient:
    """CoAP client for vent device communication."""

    def __init__(self) -> None:
        self._context: Context | None = None

    async def start(self) -> None:
        """Initialize the CoAP client context."""
        self._context = await Context.create_client_context()

    async def close(self) -> None:
        """Shut down the CoAP client context."""
        if self._context:
            await self._context.shutdown()
            self._context = None

    @staticmethod
    def _build_uri(address: str, path: str) -> str:
        """Build a CoAP URI from an address and path.

        Address formats:
          - Plain IPv6: "fd00::1" → coap://[fd00::1]/path (default port 5683)
          - With port:  "[::1]:15683" → coap://[::1]:15683/path
        """
        if address.startswith("["):
            return f"coap://{address}/{path}"
        return f"coap://[{address}]/{path}"

    async def _get(self, address: str, path: str) -> dict[str, Any]:
        """Send a CoAP GET request and decode the CBOR response."""
        assert self._context is not None, "Client not started"
        uri = self._build_uri(address, path)
        request = Message(code=Code.GET, uri=uri)
        response = await self._context.request(request).response
        if response.code.is_successful():
            return cbor2.loads(response.payload)
        raise CoapError(f"GET {path} failed: {response.code}")

    async def _put(self, address: str, path: str, payload: dict) -> dict[str, Any]:
        """Send a CoAP PUT request with CBOR payload."""
        assert self._context is not None, "Client not started"
        uri = self._build_uri(address, path)
        encoded = cbor2.dumps(payload)
        request = Message(
            code=Code.PUT,
            uri=uri,
            payload=encoded,
            content_format=CONTENT_FORMAT_CBOR,
        )
        response = await self._context.request(request).response
        if response.code.is_successful():
            return cbor2.loads(response.payload)
        raise CoapError(f"PUT {path} failed: {response.code}")

    _STATE_MAP = {0: VentState.OPEN, 1: VentState.CLOSED, 2: VentState.PARTIAL, 3: VentState.MOVING}

    async def get_position(self, address: str) -> tuple[int, VentState]:
        """Get current vent position from a device."""
        data = await self._get(address, "vent/position")
        state = self._STATE_MAP.get(data[1], VentState.CLOSED)
        return data[0], state

    async def set_target(self, address: str, angle: int) -> dict[str, Any]:
        """Set target vent angle on a device."""
        angle = max(90, min(180, angle))
        return await self._put(address, "vent/target", {0: angle})

    async def get_identity(self, address: str) -> dict[str, Any]:
        """Get device identity information."""
        data = await self._get(address, "device/identity")
        return {"eui64": data[0], "firmware_version": data[1], "uptime_s": data[2]}

    async def get_config(self, address: str) -> dict[str, str]:
        """Get device configuration."""
        data = await self._get(address, "device/config")
        return {
            "room": data.get(0, ""),
            "floor": data.get(1, ""),
            "name": data.get(2, ""),
        }

    async def set_config(
        self, address: str, room: str | None = None, floor: str | None = None, name: str | None = None
    ) -> dict[str, str]:
        """Update device configuration."""
        payload: dict[int, str] = {}
        if room is not None:
            payload[0] = room
        if floor is not None:
            payload[1] = floor
        if name is not None:
            payload[2] = name
        data = await self._put(address, "device/config", payload)
        return {"room": data.get(0, ""), "floor": data.get(1, ""), "name": data.get(2, "")}

    async def get_health(self, address: str) -> dict[str, Any]:
        """Get device health information."""
        data = await self._get(address, "device/health")
        return {
            "rssi": data[0],
            "poll_period_ms": data[1],
            "power_source": "usb" if data[2] == 0 else "battery",
            "free_heap": data[3],
            "battery_mv": data.get(4),
        }

    async def probe_device(self, address: str) -> VentDevice | None:
        """Probe a device address and return a VentDevice if it responds."""
        try:
            identity = await self.get_identity(address)
            position = await self._get(address, "vent/position")
            config = await self.get_config(address)
            health = await self.get_health(address)

            state_map = {0: VentState.OPEN, 1: VentState.CLOSED, 2: VentState.PARTIAL, 3: VentState.MOVING}

            return VentDevice(
                eui64=identity["eui64"],
                ipv6_address=address,
                room=config.get("room", ""),
                floor=config.get("floor", ""),
                name=config.get("name", ""),
                angle=position[0],
                state=state_map.get(position[1], VentState.CLOSED),
                firmware_version=identity["firmware_version"],
                rssi=health["rssi"],
                power_source=PowerSource(health["power_source"]),
                poll_period_ms=health["poll_period_ms"],
            )
        except Exception as e:
            logger.debug("Probe failed for %s: %s", address, e)
            return None


class CoapError(Exception):
    """CoAP communication error."""
