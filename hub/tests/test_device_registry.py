"""Tests for the device registry."""

import pytest
from vent_hub.models import VentDevice, VentState


@pytest.mark.asyncio
async def test_list_all(registry):
    devices = await registry.list_all()
    assert len(devices) == 3


@pytest.mark.asyncio
async def test_get_by_eui64(registry):
    device = await registry.get("aa:bb:cc:dd:ee:ff:00:01")
    assert device is not None
    assert device.room == "bedroom"


@pytest.mark.asyncio
async def test_get_nonexistent(registry):
    device = await registry.get("nonexistent")
    assert device is None


@pytest.mark.asyncio
async def test_list_by_room(registry):
    devices = await registry.list_by_room("bedroom")
    assert len(devices) == 2
    assert all(d.room == "bedroom" for d in devices)


@pytest.mark.asyncio
async def test_list_by_floor(registry):
    devices = await registry.list_by_floor("2")
    assert len(devices) == 2
    assert all(d.floor == "2" for d in devices)


@pytest.mark.asyncio
async def test_update_assignment(registry):
    ok = await registry.update_assignment("aa:bb:cc:dd:ee:ff:00:01", "kitchen", "1")
    assert ok
    device = await registry.get("aa:bb:cc:dd:ee:ff:00:01")
    assert device.room == "kitchen"
    assert device.floor == "1"


@pytest.mark.asyncio
async def test_update_position(registry):
    ok = await registry.update_position("aa:bb:cc:dd:ee:ff:00:01", 135, "partial")
    assert ok
    device = await registry.get("aa:bb:cc:dd:ee:ff:00:01")
    assert device.angle == 135
    assert device.state == VentState.PARTIAL


@pytest.mark.asyncio
async def test_delete(registry):
    ok = await registry.delete("aa:bb:cc:dd:ee:ff:00:01")
    assert ok
    device = await registry.get("aa:bb:cc:dd:ee:ff:00:01")
    assert device is None
    devices = await registry.list_all()
    assert len(devices) == 2


@pytest.mark.asyncio
async def test_get_rooms(registry):
    rooms = await registry.get_rooms()
    assert "bedroom" in rooms
    assert "living-room" in rooms


@pytest.mark.asyncio
async def test_get_floors(registry):
    floors = await registry.get_floors()
    assert "1" in floors
    assert "2" in floors


@pytest.mark.asyncio
async def test_upsert_preserves_assignment(registry):
    """Upsert with empty room/floor should not overwrite existing values."""
    device = VentDevice(
        eui64="aa:bb:cc:dd:ee:ff:00:01",
        ipv6_address="fd00::1",
        angle=120,
        state=VentState.PARTIAL,
    )
    await registry.upsert(device)
    updated = await registry.get("aa:bb:cc:dd:ee:ff:00:01")
    assert updated.room == "bedroom"  # preserved
    assert updated.angle == 120  # updated


@pytest.mark.asyncio
async def test_empty_registry(empty_registry):
    devices = await empty_registry.list_all()
    assert len(devices) == 0
