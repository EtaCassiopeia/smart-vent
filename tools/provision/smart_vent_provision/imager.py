"""Write a .img.xz to a removable block device.

Uses xz | dd via subprocess so the decompression streams without
materializing the uncompressed image to disk first.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class ImageWriteError(RuntimeError):
    """Raised when dd/xz fails."""


def assert_block_device(path: Path) -> None:
    """Refuse to write to anything that isn't a real block device.

    Catches the common mistake of pointing the CLI at a regular file
    (or a partition like /dev/sdX1 instead of the whole disk /dev/sdX).
    """
    if not path.exists():
        raise ImageWriteError(f"{path} does not exist")
    if not path.is_block_device():
        raise ImageWriteError(f"{path} is not a block device (refusing to write)")
    # Partition path heuristic: ends with a digit on /dev/sd*, /dev/nvme*p, /dev/mmcblk*p.
    name = path.name
    if name[-1:].isdigit() and not name.startswith(("loop", "ram")):
        raise ImageWriteError(
            f"{path} looks like a partition (ends in a digit). Pass the whole-disk "
            "device, e.g. /dev/sdb instead of /dev/sdb1."
        )


def write_image(image: Path, device: Path, *, bs: str = "4M") -> None:
    """Stream `image` (xz-compressed) onto `device`.

    Both `image` and `device` must already exist; caller is responsible
    for `sudo` and for any safety prompts before invoking.
    """
    if not image.exists():
        raise ImageWriteError(f"{image} does not exist")
    assert_block_device(device)

    for tool in ("xz", "dd"):
        if not shutil.which(tool):
            raise ImageWriteError(f"{tool} not found on PATH")

    cmd = f"xz -dc {_quote(image)} | dd of={_quote(device)} bs={bs} status=progress conv=fsync"
    result = subprocess.run(["bash", "-c", cmd], check=False)
    if result.returncode != 0:
        raise ImageWriteError(f"image write failed (exit {result.returncode})")


def _quote(p: Path | str) -> str:
    s = str(p)
    if all(c.isalnum() or c in "/._-" for c in s):
        return s
    return "'" + s.replace("'", "'\\''") + "'"
