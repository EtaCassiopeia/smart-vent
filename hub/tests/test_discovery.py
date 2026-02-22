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


DATASET_OUTPUT = """\
Active Timestamp: 1
Channel: 15
Channel Mask: 0x07fff800
Ext PAN ID: dead00beef00cafe
Mesh Local Prefix: fddb:30d6:d32f:d61f::/64
Network Key: 00112233445566778899aabbccddeeff
Network Name: OpenThread-test
PAN ID: 0x1234
PSKc: 00000000000000000000000000000000
Security Policy: 672 onrc 0
Done
"""

CHILD_TABLE_OUTPUT = """\
| ID  | RLOC16 | Timeout    | Age        | LQ In | C_VN |R|D|N|Ver|CSL|QMsgCnt| Extended MAC     |
+-----+--------+------------+------------+-------+------+-+-+-+---+---+-------+------------------+
|   1 | 0xa801 |        240 |         42 |     3 |   33 |1|1|1|  4| 0 |     0 | 1a2b3c4d5e6f7a8b |
Done
"""

CHILD_TABLE_MULTI = """\
| ID  | RLOC16 | Timeout    | Age        | LQ In | C_VN |R|D|N|Ver|CSL|QMsgCnt| Extended MAC     |
+-----+--------+------------+------------+-------+------+-+-+-+---+---+-------+------------------+
|   1 | 0xa801 |        240 |         42 |     3 |   33 |1|1|1|  4| 0 |     0 | 1a2b3c4d5e6f7a8b |
|   2 | 0xa802 |        240 |         10 |     3 |   33 |1|1|1|  4| 0 |     0 | 2b3c4d5e6f7a8b9c |
Done
"""


@pytest.mark.asyncio
async def test_discover_new_devices(discovery, mock_coap, empty_registry):
    """Discover a new device from ot-ctl child table."""
    device = VentDevice(
        eui64="aa:bb:cc:dd:ee:ff:00:99",
        ipv6_address="fddb:30d6:d32f:d61f:0:ff:fe00:a801",
        room="",
        floor="",
        name="",
        angle=90,
        state=VentState.CLOSED,
        firmware_version="0.1.0",
    )
    mock_coap.probe_device = AsyncMock(return_value=device)

    state_proc = _mock_subprocess("leader\nDone\n")
    dataset_proc = _mock_subprocess(DATASET_OUTPUT)
    child_proc = _mock_subprocess(CHILD_TABLE_OUTPUT)

    with patch("vent_hub.discovery.asyncio.create_subprocess_exec") as mock_exec:
        mock_exec.side_effect = [state_proc, dataset_proc, child_proc]
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
    state_proc = _mock_subprocess("detached\nDone\n")

    with patch("vent_hub.discovery.asyncio.create_subprocess_exec") as mock_exec:
        mock_exec.side_effect = [state_proc]
        new_devices = await discovery.discover()

    assert len(new_devices) == 0


@pytest.mark.asyncio
async def test_discover_multiple_children(discovery, mock_coap, empty_registry):
    """Discover multiple devices from child table output."""
    device1 = VentDevice(
        eui64="aa:bb:cc:dd:ee:ff:00:01",
        ipv6_address="fddb:30d6:d32f:d61f:0:ff:fe00:a801",
        angle=90,
        state=VentState.CLOSED,
    )
    device2 = VentDevice(
        eui64="aa:bb:cc:dd:ee:ff:00:02",
        ipv6_address="fddb:30d6:d32f:d61f:0:ff:fe00:a802",
        angle=180,
        state=VentState.OPEN,
    )
    mock_coap.probe_device = AsyncMock(side_effect=[device1, device2])

    state_proc = _mock_subprocess("router\nDone\n")
    dataset_proc = _mock_subprocess(DATASET_OUTPUT)
    child_proc = _mock_subprocess(CHILD_TABLE_MULTI)

    with patch("vent_hub.discovery.asyncio.create_subprocess_exec") as mock_exec:
        mock_exec.side_effect = [state_proc, dataset_proc, child_proc]
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
