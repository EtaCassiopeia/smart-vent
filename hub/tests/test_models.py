"""Tests for data models."""

from vent_hub.models import Floor, PowerSource, Room, VentDevice, VentState


def test_vent_device_position_pct_closed():
    d = VentDevice(eui64="test", angle=90)
    assert d.position_pct == 0


def test_vent_device_position_pct_open():
    d = VentDevice(eui64="test", angle=180)
    assert d.position_pct == 100


def test_vent_device_position_pct_partial():
    d = VentDevice(eui64="test", angle=135)
    assert d.position_pct == 50


def test_vent_device_from_row():
    row = {
        "eui64": "aa:bb:cc:dd:ee:ff:00:01",
        "ipv6_address": "fd00::1",
        "room": "bedroom",
        "floor": "2",
        "name": "test",
        "angle": 120,
        "state": "partial",
        "firmware_version": "0.1.0",
        "last_seen": "2025-01-01T00:00:00+00:00",
        "rssi": -50,
        "power_source": "usb",
        "poll_period_ms": 0,
    }
    device = VentDevice.from_row(row)
    assert device.eui64 == "aa:bb:cc:dd:ee:ff:00:01"
    assert device.angle == 120
    assert device.state == VentState.PARTIAL
    assert device.last_seen is not None


def test_vent_device_from_row_defaults():
    row = {"eui64": "test"}
    device = VentDevice.from_row(row)
    assert device.room == ""
    assert device.angle == 90
    assert device.state == VentState.CLOSED


def test_room_average_angle():
    d1 = VentDevice(eui64="a", angle=90)
    d2 = VentDevice(eui64="b", angle=180)
    room = Room(name="test", floor="1", devices=[d1, d2])
    assert room.average_angle == 135


def test_room_average_angle_empty():
    room = Room(name="test", floor="1")
    assert room.average_angle == 90


def test_floor_all_devices():
    d1 = VentDevice(eui64="a", angle=90)
    d2 = VentDevice(eui64="b", angle=180)
    r1 = Room(name="r1", floor="1", devices=[d1])
    r2 = Room(name="r2", floor="1", devices=[d2])
    floor = Floor(name="1", rooms=[r1, r2])
    assert len(floor.all_devices) == 2
