"""Device discovery via OTBR REST API."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from .coap_client import CoapClient
from .device_registry import DeviceRegistry
from .models import VentDevice

logger = logging.getLogger(__name__)


class DeviceDiscovery:
    """Discovers vent devices on the Thread network via OTBR."""

    def __init__(
        self,
        registry: DeviceRegistry,
        coap: CoapClient,
        otbr_url: str = "http://localhost:8081",
    ) -> None:
        self._registry = registry
        self._coap = coap
        self._otbr_url = otbr_url.rstrip("/")

    async def discover(self) -> list[VentDevice]:
        """Query OTBR for Thread devices and probe each one via CoAP.

        Returns list of newly discovered devices.
        """
        addresses = await self._get_thread_addresses()
        if not addresses:
            logger.info("No Thread devices found via OTBR")
            return []

        logger.info("Found %d Thread address(es), probing...", len(addresses))

        new_devices = []
        for addr in addresses:
            device = await self._coap.probe_device(addr)
            if device is None:
                continue

            existing = await self._registry.get(device.eui64)
            await self._registry.upsert(device)

            if existing is None:
                logger.info("Discovered new device: %s at %s", device.eui64, addr)
                new_devices.append(device)
            else:
                logger.debug("Updated known device: %s", device.eui64)

        return new_devices

    async def _get_thread_addresses(self) -> list[str]:
        """Get IPv6 addresses of Thread devices from OTBR REST API."""
        try:
            async with aiohttp.ClientSession() as session:
                # Get the active dataset to verify the network is up
                async with session.get(
                    f"{self._otbr_url}/v1/node/dataset/active",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status != 200:
                        logger.warning("OTBR dataset query failed: %d", resp.status)
                        return []

                # Get neighbor table for mesh-local addresses
                async with session.get(
                    f"{self._otbr_url}/v1/node/neighbor-table",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status != 200:
                        logger.warning("OTBR neighbor query failed: %d", resp.status)
                        return []
                    neighbors = await resp.json()

            addresses = []
            for neighbor in neighbors:
                if "IPv6Address" in neighbor:
                    addresses.append(neighbor["IPv6Address"])
                elif "Rloc16" in neighbor:
                    # Fall back to mesh-local from RLOC
                    rloc = neighbor["Rloc16"]
                    addresses.append(f"fdde:ad00:beef:0:0:ff:fe00:{rloc:04x}")

            return addresses

        except Exception as e:
            logger.error("OTBR discovery failed: %s", e)
            return []

    async def poll_all(self) -> int:
        """Poll all known devices and update their status in the registry.

        Returns the number of devices successfully polled.
        """
        devices = await self._registry.list_all()
        if not devices:
            return 0

        count = 0
        for device in devices:
            if not device.ipv6_address:
                continue
            try:
                updated = await self._coap.probe_device(device.ipv6_address)
                if updated:
                    await self._registry.upsert(updated)
                    count += 1
            except Exception as e:
                logger.debug("Poll failed for %s: %s", device.eui64, e)

        return count
