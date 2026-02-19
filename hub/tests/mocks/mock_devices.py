"""Mock device data for testing."""

from vent_hub.models import PowerSource, VentDevice, VentState

DEVICE_1 = VentDevice(
    eui64="aa:bb:cc:dd:ee:ff:00:01",
    ipv6_address="fd00::1",
    room="bedroom",
    floor="2",
    name="bedroom-east",
    angle=90,
    state=VentState.CLOSED,
    firmware_version="0.1.0",
    rssi=-55,
    power_source=PowerSource.USB,
    poll_period_ms=0,
)

DEVICE_2 = VentDevice(
    eui64="aa:bb:cc:dd:ee:ff:00:02",
    ipv6_address="fd00::2",
    room="bedroom",
    floor="2",
    name="bedroom-west",
    angle=180,
    state=VentState.OPEN,
    firmware_version="0.1.0",
    rssi=-60,
    power_source=PowerSource.USB,
    poll_period_ms=0,
)

DEVICE_3 = VentDevice(
    eui64="aa:bb:cc:dd:ee:ff:00:03",
    ipv6_address="fd00::3",
    room="living-room",
    floor="1",
    name="living-room-main",
    angle=135,
    state=VentState.PARTIAL,
    firmware_version="0.1.0",
    rssi=-70,
    power_source=PowerSource.BATTERY,
    poll_period_ms=5000,
)

ALL_DEVICES = [DEVICE_1, DEVICE_2, DEVICE_3]
