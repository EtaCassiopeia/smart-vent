"""Shared test fixtures."""

import pytest
import pytest_asyncio

from vent_hub.device_registry import DeviceRegistry
from .mocks.mock_devices import ALL_DEVICES


@pytest_asyncio.fixture
async def registry(tmp_path):
    """Create an in-memory test registry with sample devices."""
    db_path = tmp_path / "test.db"
    reg = DeviceRegistry(str(db_path))
    await reg.open()
    for device in ALL_DEVICES:
        await reg.upsert(device)
    yield reg
    await reg.close()


@pytest_asyncio.fixture
async def empty_registry(tmp_path):
    """Create an empty test registry."""
    db_path = tmp_path / "empty.db"
    reg = DeviceRegistry(str(db_path))
    await reg.open()
    yield reg
    await reg.close()
