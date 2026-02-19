"""Group manager for batch vent operations by room and floor."""

from __future__ import annotations

import asyncio
import logging

from .coap_client import CoapClient
from .device_registry import DeviceRegistry
from .models import VentDevice

logger = logging.getLogger(__name__)


class GroupManager:
    """Manages batch operations across groups of vent devices."""

    def __init__(self, registry: DeviceRegistry, coap: CoapClient) -> None:
        self._registry = registry
        self._coap = coap

    async def set_room_angle(self, room: str, angle: int) -> list[VentDevice]:
        """Set all vents in a room to the same angle."""
        devices = await self._registry.list_by_room(room)
        return await self._set_devices(devices, angle)

    async def set_floor_angle(self, floor: str, angle: int) -> list[VentDevice]:
        """Set all vents on a floor to the same angle."""
        devices = await self._registry.list_by_floor(floor)
        return await self._set_devices(devices, angle)

    async def set_all_angle(self, angle: int) -> list[VentDevice]:
        """Set all registered vents to the same angle."""
        devices = await self._registry.list_all()
        return await self._set_devices(devices, angle)

    async def _set_devices(
        self, devices: list[VentDevice], angle: int
    ) -> list[VentDevice]:
        """Send target angle to multiple devices concurrently."""
        if not devices:
            logger.warning("No devices to control")
            return []

        angle = max(90, min(180, angle))
        logger.info(
            "Setting %d device(s) to %d°", len(devices), angle
        )

        tasks = [
            self._set_one(device, angle) for device in devices
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        updated = []
        for device, result in zip(devices, results):
            if isinstance(result, Exception):
                logger.error(
                    "Failed to set %s: %s", device.eui64, result
                )
            elif result is not None:
                updated.append(result)

        return updated

    async def _set_one(self, device: VentDevice, angle: int) -> VentDevice | None:
        """Set a single device's target angle and update registry."""
        if not device.ipv6_address:
            logger.warning("No IPv6 address for %s", device.eui64)
            return None

        try:
            await self._coap.set_target(device.ipv6_address, angle)
            await self._registry.update_position(
                device.eui64, angle, "moving"
            )
            device.angle = angle
            return device
        except Exception as e:
            logger.error("CoAP error for %s: %s", device.eui64, e)
            raise

    async def get_room_summary(self, room: str) -> dict:
        """Get summary of all vents in a room."""
        devices = await self._registry.list_by_room(room)
        return {
            "room": room,
            "device_count": len(devices),
            "average_angle": (
                round(sum(d.angle for d in devices) / len(devices))
                if devices
                else 90
            ),
            "devices": [
                {"eui64": d.eui64, "angle": d.angle, "state": d.state.value}
                for d in devices
            ],
        }

    async def get_floor_summary(self, floor: str) -> dict:
        """Get summary of all vents on a floor."""
        devices = await self._registry.list_by_floor(floor)
        rooms = {}
        for d in devices:
            rooms.setdefault(d.room, []).append(d)
        return {
            "floor": floor,
            "device_count": len(devices),
            "room_count": len(rooms),
            "rooms": list(rooms.keys()),
        }
