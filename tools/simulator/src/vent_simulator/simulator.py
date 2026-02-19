"""Multi-device vent simulator managing multiple virtual vents."""

from __future__ import annotations

import asyncio
import logging

import aiocoap

from .virtual_vent import VirtualVent

logger = logging.getLogger(__name__)


class VentSimulator:
    """Manages multiple virtual vent devices, each with its own CoAP server."""

    def __init__(self, base_port: int = 5683, bind_address: str = "::1") -> None:
        self._base_port = base_port
        self._bind_address = bind_address
        self._vents: list[VirtualVent] = []
        self._servers: list[aiocoap.Context] = []

    def add_vent(
        self,
        eui64: str | None = None,
        room: str = "",
        floor: str = "",
        name: str = "",
    ) -> VirtualVent:
        """Add a new virtual vent device."""
        index = len(self._vents)
        port = self._base_port + index

        if eui64 is None:
            eui64 = f"sim:{index:02d}:00:00:00:00:00:{index:02x}"

        vent = VirtualVent(eui64=eui64, port=port)
        vent.room = room
        vent.floor = floor
        vent.name = name or f"sim-vent-{index}"
        self._vents.append(vent)
        return vent

    async def start(self) -> None:
        """Start CoAP servers for all virtual vents."""
        for vent in self._vents:
            site = vent.build_resource_tree()
            context = await aiocoap.Context.create_server_context(
                site,
                bind=(self._bind_address, vent.port),
            )
            self._servers.append(context)
            logger.info(
                "Virtual vent %s listening on [%s]:%d",
                vent.eui64,
                self._bind_address,
                vent.port,
            )

    async def stop(self) -> None:
        """Stop all CoAP servers."""
        for server in self._servers:
            await server.shutdown()
        self._servers.clear()
        logger.info("All virtual vents stopped")

    @property
    def vents(self) -> list[VirtualVent]:
        return list(self._vents)

    def get_vent(self, eui64: str) -> VirtualVent | None:
        for v in self._vents:
            if v.eui64 == eui64:
                return v
        return None

    async def run_forever(self) -> None:
        """Start all vents and run until cancelled."""
        await self.start()
        logger.info("Simulator running with %d vent(s). Press Ctrl+C to stop.", len(self._vents))
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()
