"""Tests for the scheduler module."""

from datetime import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from vent_hub.group_manager import GroupManager
from vent_hub.scheduler import ScheduleRule, Scheduler


@pytest.fixture
def mock_group_mgr():
    mgr = MagicMock(spec=GroupManager)
    mgr.set_all_angle = AsyncMock(return_value=[])
    mgr.set_room_angle = AsyncMock(return_value=[])
    mgr.set_floor_angle = AsyncMock(return_value=[])
    return mgr


@pytest.fixture
def scheduler(mock_group_mgr):
    return Scheduler(mock_group_mgr)


def _rule(name="test", hour=8, minute=0, target="all", target_type="all", angle=180, enabled=True):
    return ScheduleRule(
        name=name,
        time=time(hour, minute),
        target=target,
        target_type=target_type,
        angle=angle,
        enabled=enabled,
    )


def test_add_and_list_rules(scheduler):
    scheduler.add_rule(_rule("morning"))
    scheduler.add_rule(_rule("evening", hour=22))
    assert len(scheduler.rules) == 2
    assert scheduler.rules[0].name == "morning"
    assert scheduler.rules[1].name == "evening"


def test_remove_rule(scheduler):
    scheduler.add_rule(_rule("morning"))
    scheduler.add_rule(_rule("evening", hour=22))
    assert scheduler.remove_rule("morning") is True
    assert len(scheduler.rules) == 1
    assert scheduler.rules[0].name == "evening"


def test_remove_nonexistent_rule(scheduler):
    scheduler.add_rule(_rule("morning"))
    assert scheduler.remove_rule("nonexistent") is False
    assert len(scheduler.rules) == 1


def test_matches_time():
    rule = _rule(hour=8, minute=30)
    assert rule.matches_time(time(8, 30)) is True


def test_does_not_match_different_time():
    rule = _rule(hour=8, minute=30)
    assert rule.matches_time(time(8, 31)) is False
    assert rule.matches_time(time(9, 30)) is False


def test_disabled_rule_does_not_match():
    rule = _rule(hour=8, minute=0, enabled=False)
    assert rule.matches_time(time(8, 0)) is False


@pytest.mark.asyncio
async def test_check_rules_all(scheduler, mock_group_mgr):
    scheduler.add_rule(_rule(target_type="all", angle=180, hour=8))
    executed = await scheduler.check_rules(time(8, 0))
    assert executed == 1
    mock_group_mgr.set_all_angle.assert_awaited_once_with(180)


@pytest.mark.asyncio
async def test_check_rules_room(scheduler, mock_group_mgr):
    scheduler.add_rule(_rule(target="bedroom", target_type="room", angle=135, hour=9))
    executed = await scheduler.check_rules(time(9, 0))
    assert executed == 1
    mock_group_mgr.set_room_angle.assert_awaited_once_with("bedroom", 135)


@pytest.mark.asyncio
async def test_check_rules_floor(scheduler, mock_group_mgr):
    scheduler.add_rule(_rule(target="2", target_type="floor", angle=90, hour=22))
    executed = await scheduler.check_rules(time(22, 0))
    assert executed == 1
    mock_group_mgr.set_floor_angle.assert_awaited_once_with("2", 90)


@pytest.mark.asyncio
async def test_check_rules_no_match(scheduler, mock_group_mgr):
    scheduler.add_rule(_rule(hour=8))
    executed = await scheduler.check_rules(time(9, 0))
    assert executed == 0
    mock_group_mgr.set_all_angle.assert_not_awaited()


@pytest.mark.asyncio
async def test_disabled_rule_skipped(scheduler, mock_group_mgr):
    scheduler.add_rule(_rule(hour=8, enabled=False))
    executed = await scheduler.check_rules(time(8, 0))
    assert executed == 0
    mock_group_mgr.set_all_angle.assert_not_awaited()


@pytest.mark.asyncio
async def test_rule_execution_failure_logged(scheduler, mock_group_mgr):
    mock_group_mgr.set_all_angle = AsyncMock(side_effect=Exception("Network error"))
    scheduler.add_rule(_rule(hour=8))
    executed = await scheduler.check_rules(time(8, 0))
    assert executed == 1  # rule was attempted, exception caught internally


@pytest.mark.asyncio
async def test_multiple_rules_same_time(scheduler, mock_group_mgr):
    scheduler.add_rule(_rule("open_all", target_type="all", angle=180, hour=8))
    scheduler.add_rule(_rule("close_bedroom", target="bedroom", target_type="room", angle=90, hour=8))
    executed = await scheduler.check_rules(time(8, 0))
    assert executed == 2
    mock_group_mgr.set_all_angle.assert_awaited_once_with(180)
    mock_group_mgr.set_room_angle.assert_awaited_once_with("bedroom", 90)
