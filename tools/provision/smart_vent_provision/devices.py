"""Enumerate connected ESP32-C6 boards (XIAO USB JTAG/serial)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import serial.tools.list_ports

XIAO_VID = 0x303A  # Espressif
XIAO_PID = 0x1001  # USB JTAG/serial debug unit


@dataclass(frozen=True)
class Board:
    port: str  # /dev/ttyACM0
    serial_number: str | None

    def __str__(self) -> str:
        return f"{self.port} (sn={self.serial_number or 'unknown'})"


def enumerate_boards() -> list[Board]:
    """Return all currently-attached XIAO ESP32-C6 boards.

    Sorted by port path for deterministic ordering when multiple boards
    are plugged into a hub.
    """
    boards: list[Board] = []
    for port in serial.tools.list_ports.comports():
        if port.vid == XIAO_VID and port.pid == XIAO_PID:
            boards.append(Board(port=port.device, serial_number=port.serial_number))
    boards.sort(key=lambda b: b.port)
    return boards


def find_single_board() -> Board:
    """Convenience for the interactive flow: expect exactly one board."""
    boards = enumerate_boards()
    if not boards:
        raise RuntimeError(
            "no XIAO ESP32-C6 detected. Plug it directly into a USB port "
            "(not through a hub) and confirm `lsusb -d 303a:` shows it."
        )
    if len(boards) > 1:
        ports = ", ".join(b.port for b in boards)
        raise RuntimeError(
            f"more than one XIAO ESP32-C6 attached: {ports}. "
            "Unplug all but the one you want to flash."
        )
    return boards[0]


def find_existing_port(port: str | Path) -> Board:
    """Return a Board for an explicit port path, or raise if not present."""
    port = str(port)
    for board in enumerate_boards():
        if board.port == port:
            return board
    raise RuntimeError(f"no XIAO ESP32-C6 attached at {port}")
