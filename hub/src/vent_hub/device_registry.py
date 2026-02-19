"""SQLite-backed device registry for vent device inventory."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from .models import VentDevice

logger = logging.getLogger(__name__)

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS devices (
    eui64 TEXT PRIMARY KEY,
    ipv6_address TEXT NOT NULL DEFAULT '',
    room TEXT NOT NULL DEFAULT '',
    floor TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    angle INTEGER NOT NULL DEFAULT 90,
    state TEXT NOT NULL DEFAULT 'closed',
    firmware_version TEXT NOT NULL DEFAULT '',
    last_seen TEXT,
    rssi INTEGER NOT NULL DEFAULT 0,
    power_source TEXT NOT NULL DEFAULT 'usb',
    poll_period_ms INTEGER NOT NULL DEFAULT 0
)
"""


class DeviceRegistry:
    """Persistent device registry using SQLite."""

    def __init__(self, db_path: str | Path = "devices.db") -> None:
        self._db_path = str(db_path)
        self._db: aiosqlite.Connection | None = None

    async def open(self) -> None:
        """Open the database and ensure tables exist."""
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute(CREATE_TABLE)
        await self._db.commit()

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    async def upsert(self, device: VentDevice) -> None:
        """Insert or update a device record."""
        assert self._db is not None
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            """
            INSERT INTO devices (eui64, ipv6_address, room, floor, name, angle, state,
                                 firmware_version, last_seen, rssi, power_source, poll_period_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(eui64) DO UPDATE SET
                ipv6_address=excluded.ipv6_address,
                room=CASE WHEN excluded.room != '' THEN excluded.room ELSE devices.room END,
                floor=CASE WHEN excluded.floor != '' THEN excluded.floor ELSE devices.floor END,
                name=CASE WHEN excluded.name != '' THEN excluded.name ELSE devices.name END,
                angle=excluded.angle,
                state=excluded.state,
                firmware_version=excluded.firmware_version,
                last_seen=excluded.last_seen,
                rssi=excluded.rssi,
                power_source=excluded.power_source,
                poll_period_ms=excluded.poll_period_ms
            """,
            (
                device.eui64,
                device.ipv6_address,
                device.room,
                device.floor,
                device.name,
                device.angle,
                device.state.value,
                device.firmware_version,
                now,
                device.rssi,
                device.power_source.value,
                device.poll_period_ms,
            ),
        )
        await self._db.commit()

    async def get(self, eui64: str) -> VentDevice | None:
        """Get a device by EUI-64."""
        assert self._db is not None
        async with self._db.execute(
            "SELECT * FROM devices WHERE eui64 = ?", (eui64,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return VentDevice.from_row(dict(row))
            return None

    async def list_all(self) -> list[VentDevice]:
        """List all registered devices."""
        assert self._db is not None
        async with self._db.execute(
            "SELECT * FROM devices ORDER BY floor, room, name"
        ) as cursor:
            rows = await cursor.fetchall()
            return [VentDevice.from_row(dict(r)) for r in rows]

    async def list_by_room(self, room: str) -> list[VentDevice]:
        """List devices in a specific room."""
        assert self._db is not None
        async with self._db.execute(
            "SELECT * FROM devices WHERE room = ?", (room,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [VentDevice.from_row(dict(r)) for r in rows]

    async def list_by_floor(self, floor: str) -> list[VentDevice]:
        """List devices on a specific floor."""
        assert self._db is not None
        async with self._db.execute(
            "SELECT * FROM devices WHERE floor = ?", (floor,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [VentDevice.from_row(dict(r)) for r in rows]

    async def update_assignment(
        self, eui64: str, room: str, floor: str
    ) -> bool:
        """Update room/floor assignment for a device."""
        assert self._db is not None
        async with self._db.execute(
            "UPDATE devices SET room = ?, floor = ? WHERE eui64 = ?",
            (room, floor, eui64),
        ) as cursor:
            await self._db.commit()
            return cursor.rowcount > 0

    async def update_position(
        self, eui64: str, angle: int, state: str
    ) -> bool:
        """Update the cached position for a device."""
        assert self._db is not None
        now = datetime.now(timezone.utc).isoformat()
        async with self._db.execute(
            "UPDATE devices SET angle = ?, state = ?, last_seen = ? WHERE eui64 = ?",
            (angle, state, now, eui64),
        ) as cursor:
            await self._db.commit()
            return cursor.rowcount > 0

    async def delete(self, eui64: str) -> bool:
        """Remove a device from the registry."""
        assert self._db is not None
        async with self._db.execute(
            "DELETE FROM devices WHERE eui64 = ?", (eui64,)
        ) as cursor:
            await self._db.commit()
            return cursor.rowcount > 0

    async def get_rooms(self) -> list[str]:
        """Get list of unique room names."""
        assert self._db is not None
        async with self._db.execute(
            "SELECT DISTINCT room FROM devices WHERE room != '' ORDER BY room"
        ) as cursor:
            rows = await cursor.fetchall()
            return [r["room"] for r in rows]

    async def get_floors(self) -> list[str]:
        """Get list of unique floor names."""
        assert self._db is not None
        async with self._db.execute(
            "SELECT DISTINCT floor FROM devices WHERE floor != '' ORDER BY floor"
        ) as cursor:
            rows = await cursor.fetchall()
            return [r["floor"] for r in rows]
