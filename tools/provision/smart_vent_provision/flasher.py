"""Drive `espflash` to write a firmware bundle to a connected XIAO."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .release import FirmwareBundle


class FlashError(RuntimeError):
    """Raised when espflash exits non-zero."""


def ensure_espflash() -> str:
    """Return the path to espflash, or raise if not installed."""
    path = shutil.which("espflash")
    if not path:
        raise FlashError(
            "espflash not found on PATH. Install with `cargo install espflash --version '^3'`."
        )
    return path


def flash(bundle: FirmwareBundle, *, port: str, chip: str | None = None) -> None:
    """Flash the bundle to the board on `port`.

    Uses the layout from the manifest: bootloader at its offset,
    partition table at its offset, app at its offset. Matches the
    runbook §5.3 piecemeal flow.
    """
    chip = chip or bundle.chip
    espflash = ensure_espflash()

    by_name = {entry.name: entry for entry in bundle.layout}
    try:
        bootloader = by_name["bootloader"].path
        app = by_name["app"].path
    except KeyError as exc:
        raise FlashError(f"firmware bundle is missing required entry: {exc.args[0]}") from exc

    partitions_csv = bundle.cache_dir / "partitions.csv"
    if not partitions_csv.exists():
        raise FlashError(f"partitions.csv missing from bundle cache: {partitions_csv}")

    cmd = [
        espflash,
        "flash",
        "--chip", chip,
        "--port", port,
        "--partition-table", str(partitions_csv),
        "--bootloader", str(bootloader),
        str(app),
    ]
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        raise FlashError(f"espflash exited with code {result.returncode}")


def write_merged_image(bundle: FirmwareBundle, output: Path) -> Path:
    """Copy the merged single-image binary out of the cache to `output`.

    Useful when the operator wants a single .bin to drag into a third-
    party flasher (esptool.py, ESP Web Flasher, etc.) without dealing
    with three separate offsets.
    """
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(bundle.merged_image.read_bytes())
    return output
