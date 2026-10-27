"""Client behaviour with a fake GATT connection."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError

from vmi_plus_ble import (
    Speed,
    Status,
    TimeSlot,
    TimeSlots,
    VmiPlusClient,
    VmiPlusConnectionError,
    VmiPlusState,
    VmiPlusTimeoutError,
)
from vmi_plus_ble.const import CHAR_CONTROL_UUID

from .test_protocol import BYPASS, SENSORS, STATUS, TIME_SLOTS

PROBES = bytes([0xA5, 0xB6, 0x03, 0x06, 0x05, 0x01, 28, 0, 56, 0])
ANSWERS = {0x03: STATUS, 0x06: SENSORS, 0x07: PROBES, 0x14: BYPASS, 0x1D: TIME_SLOTS}


class FakeUnit:
    """Answers read commands the way a real unit does."""

    def __init__(self) -> None:
        self.written: list[bytes] = []
        self.notify: Callable[[Any, bytearray], None] | None = None
        self.disconnected: Callable[[Any], None] | None = None
        self.silent = False
        self.status = bytearray(STATUS)
        self.gatt = MagicMock()
        self.gatt.is_connected = True
        self.gatt.write_gatt_char = AsyncMock(side_effect=self._write)
        self.gatt.start_notify = AsyncMock(side_effect=self._start_notify)
        self.gatt.disconnect = AsyncMock()

    async def _start_notify(self, _uuid: str, callback: Callable[[Any, bytearray], None]) -> None:
        self.notify = callback

    async def _write(self, uuid: str, frame: bytes, response: bool) -> None:
        assert uuid == CHAR_CONTROL_UUID
        assert response
        self.written.append(frame)
        register = frame[5]
        if frame[2] == 0x10 and register == 0x0B:
            self.status[33] ^= 0x01
        answer = bytes(self.status) if register == 0x03 else ANSWERS.get(register)
        if frame[2] == 0x10 and answer and not self.silent and self.notify:
            self.notify(None, bytearray(answer))


@pytest.fixture
def unit() -> Iterator[FakeUnit]:
    fake = FakeUnit()

    async def establish(*_args: Any, disconnected_callback: Any, **_kwargs: Any) -> MagicMock:
        fake.disconnected = disconnected_callback
        return fake.gatt

    with patch("vmi_plus_ble.client.establish_connection", side_effect=establish):
        yield fake


@pytest.fixture
def ble_device() -> BLEDevice:
    return BLEDevice("AA:BB:CC:DD:EE:FF", "Urban", None)


def registers(unit: FakeUnit) -> list[tuple[int, int]]:
    return [(frame[5], frame[9]) for frame in unit.written if frame[2] == 0x10]


async def test_update(unit: FakeUnit, ble_device: BLEDevice) -> None:
    updates: list[VmiPlusState] = []
    client = VmiPlusClient(ble_device, on_update=updates.append)
    state = await client.update(bypass=True)
    assert client.is_connected
    assert client.address == "AA:BB:CC:DD:EE:FF"
    assert isinstance(state.status, Status)
    assert state.status.speed is Speed.MEDIUM
    assert state.probes is not None
    assert state.probes.main is not None
    assert state.probes.main.temperature == 28
    assert state.sensors is not None
    assert state.bypass is not None
    assert state.bypass.position == 100
    assert registers(unit) == [(0x03, 0), (0x07, 0), (0x06, 0), (0x14, 0)]
    assert len(updates) == 4
    unit.gatt.start_notify.assert_awaited_once()


@pytest.mark.parametrize(
    ("method", "args", "expected"),
    [
        ("set_speed", (Speed.HIGH,), (0x18, 2)),
        ("set_boost", (True,), (0x19, 1)),
        ("set_preheat", (False,), (0x2F, 0)),
        ("set_holiday", (True,), (0x1A, 1)),
        ("set_fixed_flow", (False,), (0x1B, 0)),
        ("set_summer_limit", (26,), (0x17, 26)),
        ("set_preheat_target", (0,), (0x1C, 0)),
        ("set_preheat_target", (16,), (0x1C, 16)),
        ("locate", (), (0x02, 0)),
        ("declare_new_filter", (12,), (0x05, 12)),
    ],
)
async def test_commands(
    unit: FakeUnit,
    ble_device: BLEDevice,
    method: str,
    args: tuple[Any, ...],
    expected: tuple[int, int],
) -> None:
    client = VmiPlusClient(ble_device)
    await getattr(client, method)(*args)
    assert registers(unit) == [expected]


@pytest.mark.parametrize(
    ("method", "value"),
    [
        ("set_summer_limit", 21),
        ("set_summer_limit", 36),
        ("set_preheat_target", 10),
        ("set_preheat_target", 19),
        ("declare_new_filter", 3),
    ],
)
async def test_commands_reject_out_of_range(
    unit: FakeUnit, ble_device: BLEDevice, method: str, value: int
) -> None:
    client = VmiPlusClient(ble_device)
    with pytest.raises(ValueError, match="must be"):
        await getattr(client, method)(value)
    assert unit.written == []


async def test_night_boost_toggles_only_when_needed(unit: FakeUnit, ble_device: BLEDevice) -> None:
    client = VmiPlusClient(ble_device)
    await client.set_night_boost(True)  # already on in the captured frame
    assert registers(unit) == [(0x03, 0)]
    await client.set_night_boost(False)
    assert registers(unit) == [(0x03, 0), (0x03, 0), (0x0B, 0)]
    await client.update()
    assert client.state.status is not None
    assert not client.state.status.night_boost


async def test_time_slots(unit: FakeUnit, ble_device: BLEDevice) -> None:
    client = VmiPlusClient(ble_device)
    programme = await client.set_time_slots(False)
    assert isinstance(programme, TimeSlots)
    assert programme.days[0] == [TimeSlot(7, Speed.MEDIUM, 0xFF)]
    await client.set_day_schedule(1, [])
    assert unit.written[-1].hex() == "a5b619061001ff0000ff0000ff0000ff0000ff0000f1"


async def test_sync_clock(unit: FakeUnit, ble_device: BLEDevice) -> None:
    client = VmiPlusClient(ble_device)
    await client.sync_clock(datetime(2026, 10, 27, 15, 50, 1))
    assert unit.written == [bytes.fromhex("a5b61a06061a0a1b0f32012d")]
    await client.sync_clock()
    assert unit.written[-1][2] == 0x1A


async def test_timeout(unit: FakeUnit, ble_device: BLEDevice) -> None:
    unit.silent = True
    client = VmiPlusClient(ble_device, timeout=0.01)
    with pytest.raises(VmiPlusTimeoutError):
        await client.update()


async def test_connection_error(ble_device: BLEDevice) -> None:
    client = VmiPlusClient(ble_device)
    with (
        patch("vmi_plus_ble.client.establish_connection", side_effect=BleakError("gone")),
        pytest.raises(VmiPlusConnectionError, match="Cannot connect"),
    ):
        await client.connect()


async def test_write_error(unit: FakeUnit, ble_device: BLEDevice) -> None:
    client = VmiPlusClient(ble_device)
    await client.connect()
    unit.gatt.write_gatt_char.side_effect = BleakError("write failed")
    with pytest.raises(VmiPlusConnectionError, match="Write"):
        await client.set_boost(True)


async def test_disconnect_fails_pending_requests(unit: FakeUnit, ble_device: BLEDevice) -> None:
    lost: list[bool] = []
    unit.silent = True
    client = VmiPlusClient(ble_device, on_disconnect=lambda: lost.append(True))
    await client.connect()

    async def drop(*_args: Any, **_kwargs: Any) -> None:
        assert unit.disconnected is not None
        unit.disconnected(unit.gatt)

    unit.gatt.write_gatt_char.side_effect = drop
    with pytest.raises(VmiPlusConnectionError, match="lost"):
        await client.update()
    assert lost == [True]
    assert not client.is_connected


async def test_reconnects_and_disconnects(unit: FakeUnit, ble_device: BLEDevice) -> None:
    client = VmiPlusClient(ble_device)
    await client.connect()
    await client.connect()  # already connected: no second connection
    unit.gatt.start_notify.assert_awaited_once()
    client.set_ble_device(BLEDevice("AA:BB:CC:DD:EE:FF", None, None))
    await client.disconnect()
    unit.gatt.disconnect.assert_awaited_once()
    assert not client.is_connected
    await client.disconnect()  # no-op


async def test_ignores_unknown_notifications(unit: FakeUnit, ble_device: BLEDevice) -> None:
    updates: list[VmiPlusState] = []
    client = VmiPlusClient(ble_device, on_update=updates.append)
    await client.connect()
    assert unit.notify is not None
    unit.notify(None, bytearray(b"\xa5\xb6\x50\x00"))
    assert updates == []
