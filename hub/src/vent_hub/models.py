"""Data models for vent devices, rooms, and floors."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class VentState(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    PARTIAL = "partial"
    MOVING = "moving"


class PowerSource(str, Enum):
    USB = "usb"
    BATTERY = "battery"


@dataclass
class VentDevice:
    """A single vent controller device."""

    eui64: str
    ipv6_address: str = ""
    room: str = ""
    floor: str = ""
    name: str = ""
    angle: int = 90
    state: VentState = VentState.CLOSED
    firmware_version: str = ""
    last_seen: datetime | None = None
    rssi: int = 0
    power_source: PowerSource = PowerSource.USB
    poll_period_ms: int = 0

    @property
    def position_pct(self) -> int:
        """Convert angle (90-180) to percentage (0-100)."""
        return round((self.angle - 90) / 90 * 100)

    @classmethod
    def from_row(cls, row: dict) -> VentDevice:
        """Create a VentDevice from a database row."""
        last_seen = None
        if row.get("last_seen"):
            last_seen = datetime.fromisoformat(row["last_seen"])
        return cls(
            eui64=row["eui64"],
            ipv6_address=row.get("ipv6_address", ""),
            room=row.get("room", ""),
            floor=row.get("floor", ""),
            name=row.get("name", ""),
            angle=row.get("angle", 90),
            state=VentState(row.get("state", "closed")),
            firmware_version=row.get("firmware_version", ""),
            last_seen=last_seen,
            rssi=row.get("rssi", 0),
            power_source=PowerSource(row.get("power_source", "usb")),
            poll_period_ms=row.get("poll_period_ms", 0),
        )


@dataclass
class Room:
    """A room containing one or more vents."""

    name: str
    floor: str
    devices: list[VentDevice] = field(default_factory=list)

    @property
    def average_angle(self) -> int:
        if not self.devices:
            return 90
        return round(sum(d.angle for d in self.devices) / len(self.devices))


@dataclass
class Floor:
    """A floor containing one or more rooms."""

    name: str
    rooms: list[Room] = field(default_factory=list)

    @property
    def all_devices(self) -> list[VentDevice]:
        return [d for room in self.rooms for d in room.devices]
