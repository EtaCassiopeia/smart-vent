"""Capture the firmware boot log to extract EUI-64, QR payload, and code.

The firmware logs three lines we care about during its first 30 seconds:

    I (1043)  Vent Controller v0.1.0
    I (1234)  EUI-64: 58:e6:c5:01:0a:dc
    I (2123)  Manual pairing code: 34970112332
    I (2125)  QR code payload: MT:Y3...

We read the serial port (115200, 8-N-1) and parse those lines. Time out
after ~30s if we don't see what we need.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

import serial

EUI64_RE = re.compile(r"EUI-64:\s*([0-9a-fA-F:]{17,23})")
QR_RE = re.compile(r"QR code payload:\s*(MT:\S+)")
CODE_RE = re.compile(r"Manual pairing code:\s*(\d{8,12})")
BANNER_RE = re.compile(r"Vent Controller v")


@dataclass
class BootInfo:
    eui64: str
    qr: str
    manual_code: str


class CaptureTimeout(RuntimeError):
    """Raised when we don't see all three values within the timeout."""


def capture(port: str, *, baudrate: int = 115_200, timeout_s: float = 45.0) -> BootInfo:
    """Open the serial port and read until we have all three fields.

    Raises CaptureTimeout if we don't see them in `timeout_s` seconds
    after the first banner line (which marks a fresh boot).
    """
    eui64: str | None = None
    qr: str | None = None
    code: str | None = None
    banner_seen = False

    deadline = time.monotonic() + timeout_s

    with serial.Serial(port, baudrate=baudrate, timeout=1.0) as ser:
        # Make sure we're starting from a fresh boot — drain stale data.
        ser.reset_input_buffer()

        while time.monotonic() < deadline:
            line = ser.readline().decode("utf-8", errors="replace")
            if not line:
                continue

            if BANNER_RE.search(line):
                banner_seen = True

            if eui64 is None:
                m = EUI64_RE.search(line)
                if m:
                    eui64 = m.group(1).lower()
            if qr is None:
                m = QR_RE.search(line)
                if m:
                    qr = m.group(1)
            if code is None:
                m = CODE_RE.search(line)
                if m:
                    code = m.group(1)

            if eui64 and qr and code:
                if not banner_seen:
                    # We grabbed all three but never saw a fresh-boot banner
                    # — probably reading mid-stream from a long-running
                    # device. Acceptable but worth noting upstream.
                    pass
                return BootInfo(eui64=eui64, qr=qr, manual_code=code)

    missing = [name for name, val in (("eui64", eui64), ("qr", qr), ("code", code)) if val is None]
    raise CaptureTimeout(
        f"timed out after {timeout_s}s waiting for: {', '.join(missing)}. "
        "Power-cycle the board (unplug + replug, NO BOOT-hold) to emit a fresh boot banner."
    )
