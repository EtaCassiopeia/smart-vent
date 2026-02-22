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

    async def _run_ot_ctl(self, *args: str) -> str | None:
        """Run an ot-ctl command and return its stdout, or None on failure."""
        try:
            proc = await asyncio.create_subprocess_exec(
                *self._otbr_cmd, *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
            if proc.returncode != 0:
                logger.warning(
                    "ot-ctl %s failed (rc=%d): %s",
                    " ".join(args), proc.returncode, stderr.decode().strip(),
                )
                return None
            return stdout.decode()
        except asyncio.TimeoutError:
            logger.error("ot-ctl %s timed out", " ".join(args))
            return None
        except Exception as e:
            logger.error("ot-ctl %s error: %s", " ".join(args), e)
            return None

    async def _get_thread_addresses(self) -> list[str]:
        """Get IPv6 addresses of Thread child devices from ot-ctl.

        Constructs RLOC addresses from child table and mesh-local prefix.
        """
        # Verify the Thread network is up
        state = await self._run_ot_ctl("state")
        if state is None:
            return []

        state_val = state.strip().splitlines()[0].strip().lower()
        if state_val in ("disabled", "detached"):
            logger.warning("OTBR Thread state is '%s', skipping discovery", state_val)
            return []

        # Get mesh-local prefix from active dataset
        dataset = await self._run_ot_ctl("dataset", "active")
        if dataset is None:
            return []

        ml_prefix = None
        for line in dataset.splitlines():
            if "Mesh Local Prefix" in line:
                # "Mesh Local Prefix: fddb:30d6:d32f:d61f::/64"
                raw = line.split(":", 1)[1].strip().split("/")[0].strip()
                # Remove trailing :: if present
                ml_prefix = raw.rstrip(":")
                break

        if not ml_prefix:
            logger.error("Could not determine mesh-local prefix")
            return []

        # Get child RLOC16 values from child table
        output = await self._run_ot_ctl("child", "table")
        if output is None:
            return []

        addresses = []
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("|") and "RLOC16" not in line and "---" not in line:
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 2:
                    rloc_str = parts[1].strip()
                    try:
                        rloc = int(rloc_str, 0)
                        addr = f"{ml_prefix}:0:ff:fe00:{rloc:04x}"
                        addresses.append(addr)
                    except ValueError:
                        continue

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
