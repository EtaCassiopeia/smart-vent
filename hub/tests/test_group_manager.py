"""Tests for the group manager."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from vent_hub.coap_client import CoapClient
from vent_hub.group_manager import GroupManager


@pytest.fixture
def mock_coap():
    coap = MagicMock(spec=CoapClient)
    coap.set_target = AsyncMock(return_value={0: 135, 1: 3, 2: 90})
    return coap


@pytest.fixture
def group_mgr(registry, mock_coap):
    return GroupManager(registry, mock_coap)


@pytest.mark.asyncio
async def test_set_room_angle(group_mgr, mock_coap):
    updated = await group_mgr.set_room_angle("bedroom", 135)
    assert len(updated) == 2
    assert mock_coap.set_target.call_count == 2


@pytest.mark.asyncio
async def test_set_floor_angle(group_mgr, mock_coap):
    updated = await group_mgr.set_floor_angle("2", 90)
    assert len(updated) == 2


@pytest.mark.asyncio
async def test_set_all_angle(group_mgr, mock_coap):
    updated = await group_mgr.set_all_angle(180)
    assert len(updated) == 3


@pytest.mark.asyncio
async def test_set_room_empty(group_mgr, mock_coap):
    updated = await group_mgr.set_room_angle("nonexistent", 90)
    assert len(updated) == 0
    mock_coap.set_target.assert_not_called()


@pytest.mark.asyncio
async def test_set_room_partial_failure(group_mgr, mock_coap):
    """One device fails, others succeed."""
    call_count = 0

    async def fail_second(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise Exception("Connection refused")
        return {0: 135, 1: 3, 2: 90}

    mock_coap.set_target = AsyncMock(side_effect=fail_second)
    updated = await group_mgr.set_room_angle("bedroom", 135)
    assert len(updated) == 1  # one succeeded


@pytest.mark.asyncio
async def test_get_room_summary(group_mgr):
    summary = await group_mgr.get_room_summary("bedroom")
    assert summary["room"] == "bedroom"
    assert summary["device_count"] == 2
    assert len(summary["devices"]) == 2
