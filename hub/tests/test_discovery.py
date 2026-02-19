"""Tests for device discovery."""

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
    return DeviceDiscovery(empty_registry, mock_coap, "http://localhost:8081")


@pytest.mark.asyncio
async def test_discover_new_devices(discovery, mock_coap, empty_registry):
    """Discover a new device from OTBR neighbor table."""
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

    with patch("vent_hub.discovery.aiohttp") as mock_aiohttp:
        mock_session = AsyncMock()
        mock_aiohttp.ClientSession.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_aiohttp.ClientSession.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_aiohttp.ClientTimeout = MagicMock()

        # Mock dataset response
        dataset_resp = AsyncMock()
        dataset_resp.status = 200
        dataset_resp.__aenter__ = AsyncMock(return_value=dataset_resp)
        dataset_resp.__aexit__ = AsyncMock(return_value=False)

        # Mock neighbor table response
        neighbor_resp = AsyncMock()
        neighbor_resp.status = 200
        neighbor_resp.json = AsyncMock(return_value=[{"IPv6Address": "fd00::99"}])
        neighbor_resp.__aenter__ = AsyncMock(return_value=neighbor_resp)
        neighbor_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session.get = MagicMock(side_effect=[dataset_resp, neighbor_resp])

        new_devices = await discovery.discover()

    assert len(new_devices) == 1
    assert new_devices[0].eui64 == "aa:bb:cc:dd:ee:ff:00:99"

    # Verify it was stored
    stored = await empty_registry.get("aa:bb:cc:dd:ee:ff:00:99")
    assert stored is not None


@pytest.mark.asyncio
async def test_discover_no_otbr(discovery, mock_coap):
    """Handle OTBR being unreachable."""
    with patch("vent_hub.discovery.aiohttp") as mock_aiohttp:
        mock_session = AsyncMock()
        mock_aiohttp.ClientSession.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_aiohttp.ClientSession.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_aiohttp.ClientTimeout = MagicMock()

        mock_session.get = MagicMock(side_effect=Exception("Connection refused"))

        new_devices = await discovery.discover()

    assert len(new_devices) == 0


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
