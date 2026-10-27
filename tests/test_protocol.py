"""Frame encoding and decoding, checked against frames captured from a real unit."""

from __future__ import annotations

from datetime import datetime

import pytest

from vmi_plus_ble import (
    BypassState,
    GtcState,
    Probes,
    Sensors,
    Speed,
    Status,
    TimeSlot,
    TimeSlots,
    build_command,
    parse_frame,
)
from vmi_plus_ble.protocol import build_date_frame, build_time_slot_frame

STATUS = bytes.fromhex(
    "a5b601063778563412001fffffffff00012832026411c80001003c04000000"
    "0009000112140518b11d160b00000000c20102010200013400100b0000c7"
)
STATUS_PREHEAT_OFF = bytes.fromhex(
    "a5b601063778563412001fffffffff00012832026411c80001003c04000000"
    "0009000100000518b11d160b00000000c20102010200003400100b0000c0"
)
SENSORS = bytes.fromhex(
    "a5b602067aefbeadde030314004c00ff000000000000000000ff000000000000000000"
    "ff000000000000000000ff000000000000000000ff000000000000000000ff00000000"
    "0000000000ff000000000000000000ff000000000000000000ff000000000000000000"
    "ff0000000000000000000000000000000000000000009d"
)
TIME_SLOTS = bytes.fromhex(
    "a5b605066a000701ffffff00ffff00ffff00ffff00ff0000ff0000ffff00ff0000"
    "ff0000ff0000ff0000ff0000ff0000ff0000ff0000ff0000ff0000ff0000ff0000"
    "ff00ffff0000ff0000ffff00ff0000ff0000ff0000ff0000ff0000ff0000ff0000"
    "ff0000ff0000ff0000ff00006f"
)
BYPASS = bytes.fromhex("a5b61806126400001c1000ff00000000000000000000649b")


@pytest.mark.parametrize(
    ("register", "value", "frame"),
    [
        (0x18, 0, "a5b610060518000000000b"),
        (0x18, 1, "a5b610060518000000010a"),
        (0x18, 2, "a5b6100605180000000209"),
        (0x19, 1, "a5b610060519000000010b"),
        (0x19, 0, "a5b610060519000000000a"),
        (0x2F, 1, "a5b61006052f000000013d"),
        (0x2F, 0, "a5b61006052f000000003c"),
        (0x0B, 0, "a5b61006050b0000000018"),
        (0x17, 26, "a5b6100605170000001a1e"),
        (0x17, 24, "a5b610060517000000181c"),
        (0x1C, 0, "a5b61006051c000000000f"),
        (0x1C, 18, "a5b61006051c000000121d"),
    ],
)
def test_build_command(register: int, value: int, frame: str) -> None:
    assert build_command(register, value).hex() == frame


def test_build_date_frame() -> None:
    assert build_date_frame(datetime(2026, 10, 27, 15, 50, 1)).hex() == "a5b61a06061a0a1b0f32012d"


def test_build_time_slot_frame_empty_day() -> None:
    assert build_time_slot_frame(1, []).hex() == "a5b619061001ff0000ff0000ff0000ff0000ff0000f1"


def test_build_time_slot_frame_sorts_and_offsets_speed() -> None:
    frame = build_time_slot_frame(2, [TimeSlot(22, Speed.LOW), TimeSlot(7, Speed.MEDIUM, 16)])
    assert frame[5:12] == bytes([2, 7, 2, 16, 22, 1, 0xFF])
    assert frame[12:15] == bytes([0xFF, 0, 0])


@pytest.mark.parametrize(
    ("day", "slots"),
    [
        (0, []),
        (8, []),
        (1, [TimeSlot(24, Speed.LOW)]),
        (1, [TimeSlot(hour, Speed.LOW) for hour in range(6)]),
    ],
)
def test_build_time_slot_frame_rejects_bad_input(day: int, slots: list[TimeSlot]) -> None:
    with pytest.raises(ValueError, match=r"must be|at most"):
        build_time_slot_frame(day, slots)


@pytest.mark.parametrize(
    "data",
    [b"", b"\xa5\xb6", bytes([0, 0, 1]) + bytes(60), bytes([0xA5, 0xB6, 0x99]) + bytes(40)],
)
def test_parse_rejects_unknown_frames(data: bytes) -> None:
    assert parse_frame(data) is None


def test_parse_rejects_short_status() -> None:
    assert parse_frame(STATUS[:40]) is None


def test_parse_status() -> None:
    status = parse_frame(STATUS)
    assert isinstance(status, Status)
    assert status.serial == "12345678"
    assert status.box == "Urban"
    assert status.software_version == "6.4.002"
    assert (status.electronic_version, status.board_software_version) == (1, 1)
    assert status.mechanical_version == 1
    assert status.volume == 200
    assert status.surface == 80
    assert status.preheat_type == "electric"
    assert status.operating_days == 1084
    assert status.filter_days == 0
    assert status.speed is Speed.MEDIUM
    assert status.night_boost
    assert status.preheat
    assert status.preheat_target == 18
    assert status.summer_limit == 24
    assert status.air_flow == 90
    assert status.season == "intermediate"
    assert status.self_test_ok
    assert not status.boost
    assert not status.holiday
    assert not status.fixed_flow
    assert not status.time_slots
    assert not status.gtc
    assert not status.turbo_heater
    assert not status.action_in_progress
    assert not status.bypass_open


def test_parse_status_preheat_off() -> None:
    status = parse_frame(STATUS_PREHEAT_OFF)
    assert isinstance(status, Status)
    assert status.preheat_target == 0
    assert not status.preheat


def test_parse_status_unknown_speed() -> None:
    data = bytearray(STATUS)
    data[34] = 7
    status = parse_frame(bytes(data))
    assert isinstance(status, Status)
    assert status.speed is None


def test_parse_probes() -> None:
    data = bytearray([0xA5, 0xB6, 0x03, 0x06, 0x19]) + bytearray(25)
    data[5:9] = bytes([0x01, 28, 0, 56])
    data[10:14] = bytes([0x08, 0xFB, 0, 0])
    probes = parse_frame(bytes(data))
    assert isinstance(probes, Probes)
    assert probes.main is not None
    assert (probes.main.temperature, probes.main.humidity) == (28, 56)
    assert probes.probes[1].temperature == -4
    assert len(probes.probes) == 5


def test_parse_probes_empty() -> None:
    probes = parse_frame(bytes([0xA5, 0xB6, 0x03]) + bytes(6))
    assert isinstance(probes, Probes)
    assert probes.main is not None
    assert len(probes.probes) == 1


def test_parse_sensors() -> None:
    sensors = parse_frame(SENSORS)
    assert isinstance(sensors, Sensors)
    assert len(sensors.sensors) == 1
    remote = sensors.remote_control
    assert remote is not None
    assert remote.id == "DEADBEEF"
    assert remote.room == "bathroom_1"
    assert (remote.temperature, remote.humidity, remote.co2) == (20, 76, None)


def test_parse_co2_sensor() -> None:
    data = bytearray([0xA5, 0xB6, 0x02, 0x06, 0x0A]) + bytearray(10)
    data[5:15] = bytes([0x20, 0x04, 0x00, 0x00, 0x01, 0x01, 0x20, 0x03, 45, 0])
    sensors = parse_frame(bytes(data))
    assert isinstance(sensors, Sensors)
    sensor = sensors.sensors[0]
    assert (sensor.kind, sensor.room, sensor.co2, sensor.temperature) == (
        "nexelec_co2",
        "living_room",
        800,
        None,
    )
    assert sensors.remote_control is None


def test_parse_time_slots() -> None:
    slots = parse_frame(TIME_SLOTS)
    assert isinstance(slots, TimeSlots)
    assert not slots.enabled
    assert slots.days[0] == [TimeSlot(7, Speed.MEDIUM, 0xFF)]
    assert slots.days[1:] == [[]] * 6


def test_parse_time_slots_skips_unknown_speed() -> None:
    data = bytearray(TIME_SLOTS)
    data[7] = 9
    slots = parse_frame(bytes(data))
    assert isinstance(slots, TimeSlots)
    assert slots.days[0] == []


def test_parse_bypass() -> None:
    bypass = parse_frame(BYPASS)
    assert bypass == BypassState(
        position=100, bypass_type=0, temperature=28, id="00000000", forced=0, requested_position=100
    )


def test_parse_gtc() -> None:
    gtc = parse_frame(bytes([0xA5, 0xB6, 0x16, 0x06, 0x05, 1, 10, 3, 0, 1]))
    assert gtc == GtcState(mode=1, address=10, baudrate=3, parity=0, stop_bit=1)
