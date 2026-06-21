"""Test the safety guards on imager.write_image / assert_block_device.

Block-device-specific work is exercised via a synthetic device (tmpfile
that lies via mock); the actual dd path is integration-only and not in
this test suite.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from smart_vent_provision import imager


def test_assert_block_device_rejects_regular_file(tmp_path: Path):
    f = tmp_path / "not-a-device.img"
    f.write_bytes(b"hello")
    with pytest.raises(imager.ImageWriteError, match="not a block device"):
        imager.assert_block_device(f)


def test_assert_block_device_rejects_missing(tmp_path: Path):
    with pytest.raises(imager.ImageWriteError, match="does not exist"):
        imager.assert_block_device(tmp_path / "ghost")


def test_assert_block_device_rejects_partition_path():
    # Use a fake path that ends in a digit and pretend it's a block device.
    fake = Path("/dev/sdb1")
    with patch.object(Path, "exists", return_value=True), \
         patch.object(Path, "is_block_device", return_value=True):
        with pytest.raises(imager.ImageWriteError, match="looks like a partition"):
            imager.assert_block_device(fake)


def test_assert_block_device_accepts_whole_disk():
    fake = Path("/dev/sdb")
    with patch.object(Path, "exists", return_value=True), \
         patch.object(Path, "is_block_device", return_value=True):
        # Should NOT raise.
        imager.assert_block_device(fake)


# The full write_image path (xz | dd) is integration-only and exercised
# manually with `smart-vent-provision image --device /dev/sdX`. The two
# safety guards above are the unit-test-worthy bits.
