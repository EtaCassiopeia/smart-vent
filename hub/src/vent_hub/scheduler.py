"""Time-based automation scheduler for vent control."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import time
from typing import Callable, Awaitable

from .group_manager import GroupManager

logger = logging.getLogger(__name__)


@dataclass
class ScheduleRule:
    """A time-based automation rule."""

    name: str
    time: time
    target: str  # "all", room name, or floor name
    target_type: str  # "all", "room", "floor"
    angle: int
    enabled: bool = True

    def matches_time(self, current: time) -> bool:
        return (
            self.enabled
            and self.time.hour == current.hour
            and self.time.minute == current.minute
        )


class Scheduler:
    """Runs time-based vent automation rules."""

    def __init__(self, group_manager: GroupManager) -> None:
        self._group_manager = group_manager
        self._rules: list[ScheduleRule] = []
        self._running = False

    def add_rule(self, rule: ScheduleRule) -> None:
        self._rules.append(rule)
        logger.info("Added schedule rule: %s at %s", rule.name, rule.time)

    def remove_rule(self, name: str) -> bool:
        before = len(self._rules)
        self._rules = [r for r in self._rules if r.name != name]
        return len(self._rules) < before

    @property
    def rules(self) -> list[ScheduleRule]:
        return list(self._rules)

    async def check_rules(self, current_time: time) -> int:
        """Check and execute any rules matching the current time.

        Returns number of rules executed.
        """
        executed = 0
        for rule in self._rules:
            if rule.matches_time(current_time):
                await self._execute_rule(rule)
                executed += 1
        return executed

    async def _execute_rule(self, rule: ScheduleRule) -> None:
        logger.info("Executing rule: %s -> %s=%d°", rule.name, rule.target, rule.angle)
        try:
            if rule.target_type == "all":
                await self._group_manager.set_all_angle(rule.angle)
            elif rule.target_type == "room":
                await self._group_manager.set_room_angle(rule.target, rule.angle)
            elif rule.target_type == "floor":
                await self._group_manager.set_floor_angle(rule.target, rule.angle)
        except Exception as e:
            logger.error("Rule %s failed: %s", rule.name, e)

    async def run(self) -> None:
        """Run the scheduler loop, checking rules every 60 seconds."""
        self._running = True
        logger.info("Scheduler started with %d rule(s)", len(self._rules))

        while self._running:
            from datetime import datetime

            now = datetime.now().time().replace(second=0, microsecond=0)
            await self.check_rules(now)
            await asyncio.sleep(60)

    def stop(self) -> None:
        self._running = False
