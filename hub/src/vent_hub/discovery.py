"""Device discovery via OTBR ot-ctl."""

from __future__ import annotations

import asyncio
import logging
import shlex
from typing import Any

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
        otbr_cmd: str = "docker exec otbr ot-ctl",
    ) -> None:
        self._registry = registry
        self._coap = coap
        self._otbr_cmd = shlex.split(otbr_cmd)

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

    async def _run_ot_ctl(self, command: str) -> str | None:
        """Run an ot-ctl command and return its stdout, or None on failure."""
        try:
            proc = await asyncio.create_subprocess_exec(
                *self._otbr_cmd, command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
            if proc.returncode != 0:
                logger.warning(
                    "ot-ctl %s failed (rc=%d): %s",
                    command, proc.returncode, stderr.decode().strip(),
                )
                return None
            return stdout.decode()
        except asyncio.TimeoutError:
            logger.error("ot-ctl %s timed out", command)
            return None
        except Exception as e:
            logger.error("ot-ctl %s error: %s", command, e)
            return None

    async def _get_thread_addresses(self) -> list[str]:
        """Get IPv6 addresses of Thread child devices from ot-ctl."""
        # Verify the Thread network is up
        state = await self._run_ot_ctl("state")
        if state is None:
            return []

        state = state.strip().lower()
        if state in ("disabled", "detached"):
            logger.warning("OTBR Thread state is '%s', skipping discovery", state)
            return []

        # Get child IPv6 addresses via childip6
        output = await self._run_ot_ctl("childip6")
        if output is None:
            return []

        addresses = []
        for line in output.strip().splitlines():
            # Format: "0xa801: fd0a:9540:e1a1:0:2c2a:1afa:8c69:db9e"
            line = line.strip()
            if not line:
                continue
            parts = line.split(": ", 1)
            if len(parts) == 2:
                addresses.append(parts[1].strip())

        return addresses

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
