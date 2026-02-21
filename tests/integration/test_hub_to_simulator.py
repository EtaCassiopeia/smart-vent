"""Integration test: hub CoAP client against the device simulator."""

import asyncio

import pytest
import pytest_asyncio

from vent_hub.coap_client import CoapClient
from vent_hub.models import VentState
from vent_simulator.simulator import VentSimulator


@pytest_asyncio.fixture
async def simulator():
    """Start a simulator with 2 virtual vents."""
    sim = VentSimulator(base_port=15683, bind_address="::1")
    sim.add_vent(room="bedroom", floor="2")
    sim.add_vent(room="living-room", floor="1")
    await sim.start()
    yield sim
    await sim.stop()


@pytest_asyncio.fixture
async def coap():
    """Create a CoAP client."""
    client = CoapClient()
    await client.start()
    yield client
    await client.close()


@pytest.mark.asyncio
async def test_get_identity(simulator, coap):
    vent = simulator.vents[0]
    identity = await coap.get_identity(f"[::1]:{vent.port}")
    assert identity["eui64"] == vent.eui64
    assert "sim" in identity["firmware_version"]


@pytest.mark.asyncio
async def test_get_position_default_closed(simulator, coap):
    vent = simulator.vents[0]
    angle, state = await coap.get_position(f"[::1]:{vent.port}")
    assert angle == 90
    assert state == VentState.CLOSED


@pytest.mark.asyncio
async def test_set_target_and_read_back(simulator, coap):
    vent = simulator.vents[0]
    addr = f"[::1]:{vent.port}"

    await coap.set_target(addr, 135)
    angle, state = await coap.get_position(addr)
    assert angle == 135
    assert state == VentState.PARTIAL


@pytest.mark.asyncio
async def test_set_config(simulator, coap):
    vent = simulator.vents[1]
    addr = f"[::1]:{vent.port}"

    await coap.set_config(addr, room="kitchen", floor="1", name="kitchen-main")
    config = await coap.get_config(addr)
    assert config["room"] == "kitchen"
    assert config["floor"] == "1"
    assert config["name"] == "kitchen-main"


@pytest.mark.asyncio
async def test_get_health(simulator, coap):
    vent = simulator.vents[0]
    health = await coap.get_health(f"[::1]:{vent.port}")
    assert "rssi" in health
    assert health["power_source"] == "usb"


@pytest.mark.asyncio
async def test_probe_device(simulator, coap):
    vent = simulator.vents[0]
    device = await coap.probe_device(f"[::1]:{vent.port}")
    assert device is not None
    assert device.eui64 == vent.eui64
    assert device.angle == 90
