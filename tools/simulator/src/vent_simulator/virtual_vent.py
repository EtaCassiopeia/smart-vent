"""Single virtual vent device with CoAP resource tree."""

from __future__ import annotations

import time

import aiocoap
import aiocoap.resource
import cbor2


class VirtualVent:
    """State for a single simulated vent device."""

    def __init__(self, eui64: str, port: int) -> None:
        self.eui64 = eui64
        self.port = port
        self.angle: int = 90
        self.state: str = "closed"
        self.room: str = ""
        self.floor: str = ""
        self.name: str = ""
        self.start_time: float = time.time()
        self.firmware_version: str = "0.1.0-sim"
        self.power_source: str = "usb"
        self.poll_period_ms: int = 0

    def set_angle(self, angle: int) -> int:
        prev = self.angle
        self.angle = max(90, min(180, angle))
        if self.angle == 90:
            self.state = "closed"
        elif self.angle == 180:
            self.state = "open"
        else:
            self.state = "partial"
        return prev

    @property
    def uptime_s(self) -> int:
        return int(time.time() - self.start_time)

    def build_resource_tree(self) -> aiocoap.resource.Site:
        root = aiocoap.resource.Site()
        root.add_resource(
            ["vent", "position"], VentPositionResource(self)
        )
        root.add_resource(
            ["vent", "target"], VentTargetResource(self)
        )
        root.add_resource(
            ["device", "identity"], DeviceIdentityResource(self)
        )
        root.add_resource(
            ["device", "config"], DeviceConfigResource(self)
        )
        root.add_resource(
            ["device", "health"], DeviceHealthResource(self)
        )
        return root


class VentPositionResource(aiocoap.resource.Resource):
    def __init__(self, vent: VirtualVent) -> None:
        super().__init__()
        self._vent = vent

    async def render_get(self, request):
        state_map = {"open": 0, "closed": 1, "partial": 2, "moving": 3}
        payload = cbor2.dumps({
            0: self._vent.angle,
            1: state_map.get(self._vent.state, 1),
        })
        return aiocoap.Message(payload=payload, content_format=60)


class VentTargetResource(aiocoap.resource.Resource):
    def __init__(self, vent: VirtualVent) -> None:
        super().__init__()
        self._vent = vent

    async def render_put(self, request):
        data = cbor2.loads(request.payload)
        target_angle = data.get(0, 90)
        prev = self._vent.set_angle(target_angle)
        state_map = {"open": 0, "closed": 1, "partial": 2, "moving": 3}
        payload = cbor2.dumps({
            0: self._vent.angle,
            1: state_map.get(self._vent.state, 1),
            2: prev,
        })
        return aiocoap.Message(payload=payload, content_format=60)


class DeviceIdentityResource(aiocoap.resource.Resource):
    def __init__(self, vent: VirtualVent) -> None:
        super().__init__()
        self._vent = vent

    async def render_get(self, request):
        payload = cbor2.dumps({
            0: self._vent.eui64,
            1: self._vent.firmware_version,
            2: self._vent.uptime_s,
        })
        return aiocoap.Message(payload=payload, content_format=60)


class DeviceConfigResource(aiocoap.resource.Resource):
    def __init__(self, vent: VirtualVent) -> None:
        super().__init__()
        self._vent = vent

    async def render_get(self, request):
        payload = cbor2.dumps({
            0: self._vent.room,
            1: self._vent.floor,
            2: self._vent.name,
        })
        return aiocoap.Message(payload=payload, content_format=60)

    async def render_put(self, request):
        data = cbor2.loads(request.payload)
        if 0 in data:
            self._vent.room = data[0]
        if 1 in data:
            self._vent.floor = data[1]
        if 2 in data:
            self._vent.name = data[2]
        return await self.render_get(request)


class DeviceHealthResource(aiocoap.resource.Resource):
    def __init__(self, vent: VirtualVent) -> None:
        super().__init__()
        self._vent = vent

    async def render_get(self, request):
        power_map = {"usb": 0, "battery": 1}
        payload = cbor2.dumps({
            0: -55,  # simulated RSSI
            1: self._vent.poll_period_ms,
            2: power_map.get(self._vent.power_source, 0),
            3: 200000,  # fake free heap
            4: None,  # no battery
        })
        return aiocoap.Message(payload=payload, content_format=60)
