"""Tests for the CoAP client (mocked)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, PropertyMock

from vent_hub.coap_client import CoapClient, CoapError
from vent_hub.models import VentState


@pytest.fixture
def coap_client():
    client = CoapClient()
    client._context = MagicMock()
    return client


def _setup_mock_response(coap_client, payload_bytes, code_successful=True):
    """Set up mock for aiocoap's request().response pattern."""
    resp = MagicMock()
    resp.code.is_successful.return_value = code_successful
    resp.payload = payload_bytes

    # aiocoap: context.request(msg) returns a Request object
    # whose .response is a coroutine/future
    mock_request_obj = MagicMock()
    mock_request_obj.response = AsyncMock(return_value=resp)()
    # Make .response an awaitable that returns resp
    response_future = AsyncMock(return_value=resp)
    mock_request_obj.response = response_future()

    coap_client._context.request.return_value = mock_request_obj
    return resp


@pytest.mark.asyncio
async def test_get_position(coap_client):
    import cbor2

    payload = cbor2.dumps({0: 135, 1: 2})  # angle=135, state=partial(2)
    _setup_mock_response(coap_client, payload)

    angle, state = await coap_client.get_position("fd00::1")
    assert angle == 135
    assert state == VentState.PARTIAL


@pytest.mark.asyncio
async def test_set_target(coap_client):
    import cbor2

    payload = cbor2.dumps({0: 120, 1: 3, 2: 90})  # angle, moving, prev
    _setup_mock_response(coap_client, payload)

    result = await coap_client.set_target("fd00::1", 120)
    assert result[0] == 120


@pytest.mark.asyncio
async def test_set_target_clamps(coap_client):
    import cbor2

    payload = cbor2.dumps({0: 180, 1: 3, 2: 90})
    _setup_mock_response(coap_client, payload)

    result = await coap_client.set_target("fd00::1", 999)
    # Verify the angle was clamped to 180 in the call
    call_args = coap_client._context.request.call_args
    sent_msg = call_args[0][0]
    sent_payload = cbor2.loads(sent_msg.payload)
    assert sent_payload[0] == 180


@pytest.mark.asyncio
async def test_get_identity(coap_client):
    import cbor2

    payload = cbor2.dumps({0: "aa:bb:cc:dd", 1: "0.1.0", 2: 3600})
    _setup_mock_response(coap_client, payload)

    result = await coap_client.get_identity("fd00::1")
    assert result["eui64"] == "aa:bb:cc:dd"
    assert result["firmware_version"] == "0.1.0"
    assert result["uptime_s"] == 3600


@pytest.mark.asyncio
async def test_coap_error_on_failure(coap_client):
    resp = _setup_mock_response(coap_client, b"", code_successful=False)
    resp.code.__str__ = lambda self: "4.04"

    with pytest.raises(CoapError):
        await coap_client.get_identity("fd00::1")
