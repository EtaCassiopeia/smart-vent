"""Tests for device discovery."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from vent_hub.coap_client import CoapClient
from vent_hub.discovery import DeviceDiscovery
from vent_hub.models import PowerSource, VentDevice, VentState


@pytest.fixture
def mock_coap():
    coap = MagicMock(spec=CoapClient)
    return coap


@pytest.fixture
def discovery(empty_registry, mock_coap):
    return DeviceDiscovery(empty_registry, mock_coap, "docker exec otbr ot-ctl")


def _mock_subprocess(stdout: str, returncode: int = 0):
    """Create a mock process that returns given stdout."""
    proc = AsyncMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout.encode(), b""))
    return proc


@pytest.mark.asyncio
async def test_discover_new_devices(discovery, mock_coap, empty_registry):
    """Discover a new device from ot-ctl childip6."""
    device = VentDevice(
        eui64="aa:bb:cc:dd:ee:ff:00:99",
        ipv6_address="fd00::99",
        room="",
        floor="",
        name="",
        angle=90,
        state=VentState.CLOSED,
        firmware_version="0.1.0",
    )
    mock_coap.probe_device = AsyncMock(return_value=device)

    state_proc = _mock_subprocess("leader\n")
    childip6_proc = _mock_subprocess("0xa801: fd00::99\n")

    with patch("vent_hub.discovery.asyncio.create_subprocess_exec") as mock_exec:
        mock_exec.side_effect = [state_proc, childip6_proc]
        new_devices = await discovery.discover()

    assert len(new_devices) == 1
    assert new_devices[0].eui64 == "aa:bb:cc:dd:ee:ff:00:99"

    # Verify it was stored
    stored = await empty_registry.get("aa:bb:cc:dd:ee:ff:00:99")
    assert stored is not None


@pytest.mark.asyncio
async def test_discover_no_otbr(discovery, mock_coap):
    """Handle ot-ctl being unreachable."""
    with patch("vent_hub.discovery.asyncio.create_subprocess_exec") as mock_exec:
        mock_exec.side_effect = FileNotFoundError("docker not found")
        new_devices = await discovery.discover()

    assert len(new_devices) == 0


@pytest.mark.asyncio
async def test_discover_detached(discovery, mock_coap):
    """Handle OTBR in detached state."""
    state_proc = _mock_subprocess("detached\n")

    with patch("vent_hub.discovery.asyncio.create_subprocess_exec") as mock_exec:
        mock_exec.side_effect = [state_proc]
        new_devices = await discovery.discover()

    assert len(new_devices) == 0


@pytest.mark.asyncio
async def test_discover_multiple_children(discovery, mock_coap, empty_registry):
    """Discover multiple devices from childip6 output."""
    device1 = VentDevice(
        eui64="aa:bb:cc:dd:ee:ff:00:01",
        ipv6_address="fd00::1",
        angle=90,
        state=VentState.CLOSED,
    )
    device2 = VentDevice(
        eui64="aa:bb:cc:dd:ee:ff:00:02",
        ipv6_address="fd00::2",
        angle=180,
        state=VentState.OPEN,
    )
    mock_coap.probe_device = AsyncMock(side_effect=[device1, device2])

    state_proc = _mock_subprocess("router\n")
    childip6_proc = _mock_subprocess(
        "0xa801: fd00::1\n"
        "0xa802: fd00::2\n"
    )

    with patch("vent_hub.discovery.asyncio.create_subprocess_exec") as mock_exec:
        mock_exec.side_effect = [state_proc, childip6_proc]
        new_devices = await discovery.discover()

    assert len(new_devices) == 2


@pytest.mark.asyncio
async def test_poll_all(discovery, mock_coap, empty_registry):
    """Poll updates existing devices."""
    device = VentDevice(
        eui64="aa:bb:cc:dd:ee:ff:00:01",
        ipv6_address="fd00::1",
        angle=90,
        state=VentState.CLOSED,
    )
    await empty_registry.upsert(device)

    updated_device = VentDevice(
        eui64="aa:bb:cc:dd:ee:ff:00:01",
        ipv6_address="fd00::1",
        angle=135,
        state=VentState.PARTIAL,
    )
    mock_coap.probe_device = AsyncMock(return_value=updated_device)

    count = await discovery.poll_all()
    assert count == 1

    stored = await empty_registry.get("aa:bb:cc:dd:ee:ff:00:01")
    assert stored.angle == 135
