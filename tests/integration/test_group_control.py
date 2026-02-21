"""Integration test: group operations via hub against simulator."""

import pytest
import pytest_asyncio

from vent_hub.coap_client import CoapClient
from vent_hub.device_registry import DeviceRegistry
from vent_hub.group_manager import GroupManager
from vent_hub.models import VentDevice, VentState
from vent_simulator.simulator import VentSimulator


@pytest_asyncio.fixture
async def simulator():
    sim = VentSimulator(base_port=16683, bind_address="::1")
    sim.add_vent(room="bedroom", floor="2")
    sim.add_vent(room="bedroom", floor="2")
    sim.add_vent(room="living-room", floor="1")
    await sim.start()
    yield sim
    await sim.stop()


@pytest_asyncio.fixture
async def services(simulator, tmp_path):
    registry = DeviceRegistry(str(tmp_path / "test.db"))
    await registry.open()

    coap = CoapClient()
    await coap.start()

    # Register simulated devices
    for vent in simulator.vents:
        device = VentDevice(
            eui64=vent.eui64,
            ipv6_address=f"[::1]:{vent.port}",
            room=vent.room,
            floor=vent.floor,
            name=vent.name,
        )
        await registry.upsert(device)

    group_mgr = GroupManager(registry, coap)
    yield registry, coap, group_mgr

    await coap.close()
    await registry.close()


@pytest.mark.asyncio
async def test_set_room_angle(services, simulator):
    registry, coap, group_mgr = services

    updated = await group_mgr.set_room_angle("bedroom", 150)
    assert len(updated) == 2

    # Verify on simulator side
    for vent in simulator.vents:
        if vent.room == "bedroom":
            assert vent.angle == 150


@pytest.mark.asyncio
async def test_set_floor_angle(services, simulator):
    registry, coap, group_mgr = services

    updated = await group_mgr.set_floor_angle("2", 180)
    assert len(updated) == 2

    for vent in simulator.vents:
        if vent.floor == "2":
            assert vent.angle == 180


@pytest.mark.asyncio
async def test_set_all_angle(services, simulator):
    registry, coap, group_mgr = services

    updated = await group_mgr.set_all_angle(90)
    assert len(updated) == 3

    for vent in simulator.vents:
        assert vent.angle == 90
