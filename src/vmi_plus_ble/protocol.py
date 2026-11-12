"""Frame encoding and decoding (no I/O).

Every frame is ``A5 B6 [class] 06 [len] [payload] [crc]``. Offsets below are
indexes in the raw frame, header included.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from .const import (
    BOXES,
    EMPTY_SLOT_START,
    MAGIC,
    PREHEAT_TYPES,
    ROOMS,
    SEASONS,
    SENSOR_KINDS,
    TIME_SLOT_DAYS,
    TIME_SLOTS_PER_DAY,
    FrameClass,
    Speed,
)
from .models import (
    BypassState,
    Frame,
    GtcState,
    Probe,
    Probes,
    Sensor,
    Sensors,
    Status,
    TimeSlot,
    TimeSlots,
)

STATUS_MIN_LENGTH = 54
SENSOR_SLOT_SIZE = 10
SENSOR_SLOTS = 10
PROBE_SLOT_SIZE = 5
PROBE_SLOTS = 5


def checksum(data: bytes) -> int:
    """Checksum of a frame: CRC-8 (polynomial 0x01, init 0) XOR 0x13."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 1) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc ^ 0x13


def build_frame(frame_class: int, payload: bytes) -> bytes:
    """Builds any app -> unit frame."""
    data = MAGIC + bytes([frame_class, 0x06, len(payload)]) + payload
    return data + bytes([checksum(data)])


def build_command(register: int, value: int = 0) -> bytes:
    """Builds a command frame (class 0x10): payload ``[register, 0, 0, 0, value]``."""
    return build_frame(FrameClass.COMMAND, bytes([register, 0, 0, 0, value]))


def build_time_slot_frame(day: int, slots: Sequence[TimeSlot]) -> bytes:
    """Builds a ConfigTimeSlot frame for one day (1 = Monday, up to 5 slots).

    The unit stores the speed byte minus one: the app sends 1/2/3 and the
    TimeSlotState frame reports 0/1/2.
    """
    if not 1 <= day <= TIME_SLOT_DAYS:
        raise ValueError(f"day must be 1-{TIME_SLOT_DAYS}, got {day}")
    if len(slots) > TIME_SLOTS_PER_DAY:
        raise ValueError(f"at most {TIME_SLOTS_PER_DAY} slots per day")
    payload = [day]
    for slot in sorted(slots, key=lambda slot: slot.start):
        if not 0 <= slot.start <= 23:
            raise ValueError(f"start hour must be 0-23, got {slot.start}")
        payload += [slot.start, slot.speed + 1, slot.temperature]
    payload += [EMPTY_SLOT_START, 0x00, 0x00] * (TIME_SLOTS_PER_DAY - len(slots))
    return build_frame(FrameClass.CONFIG_TIME_SLOT, bytes(payload))


def build_date_frame(moment: datetime) -> bytes:
    """Builds the clock-sync frame (class 0x1a) the app sends on every connection."""
    return build_frame(
        FrameClass.UPDATE_DATE,
        bytes(
            [
                moment.year % 100,
                moment.month,
                moment.day,
                moment.hour,
                moment.minute,
                moment.second,
            ]
        ),
    )


def parse_frame(data: bytes) -> Frame | None:
    """Decodes a notification, or returns None for an unknown or short frame."""
    if len(data) < 3 or data[:2] != MAGIC:
        return None
    match data[2]:
        case FrameClass.STATE if len(data) >= STATUS_MIN_LENGTH:
            return _parse_status(data)
        case FrameClass.PROBES_STATE if len(data) >= 9:
            return _parse_probes(data)
        case FrameClass.SENSORS_STATE if len(data) >= 14:
            return _parse_sensors(data)
        case FrameClass.TIME_SLOT_STATE if len(data) >= 6:
            return _parse_time_slots(data)
        case FrameClass.BYPASS_STATE if len(data) >= 23:
            return _parse_bypass(data)
        case FrameClass.ERP_STATE if len(data) >= 10:
            return _parse_gtc(data)
    return None


def _signed(value: int) -> int:
    """Temperatures >= 128 are negative (value - 255, as the app does)."""
    return value - 0xFF if value >= 0x80 else value


def _le(data: bytes) -> int:
    return int.from_bytes(data, "little")


def _speed(value: int) -> Speed | None:
    try:
        return Speed(value)
    except ValueError:
        return None


def _parse_status(data: bytes) -> Status:
    return Status(
        serial=f"{_le(data[5:9]):08X}",
        action_in_progress=data[9] == 0x01,
        self_test=data[10],
        self_test_details=data[11:15].hex(),
        gtc=data[15] == 0x01,
        surface=data[17] * 2,
        box=BOXES.get(data[19]),
        software_version=f"{data[20] >> 4}.{data[20] & 0x0F}.{data[49]:03d}",
        electronic_version=data[21] >> 4,
        board_software_version=data[21] & 0x0F,
        volume=_le(data[22:24]),
        preheat_type=PREHEAT_TYPES.get(data[24]),
        bypass_open=data[25] == 0x01,
        operating_days=_le(data[26:28]),
        filter_days=_le(data[28:30]),
        night_boost=data[33] == 0x00,  # inverted
        speed=_speed(data[34]),
        preheat_target=data[35],
        summer_limit=data[38],
        holiday=data[43] == 0x01,
        boost=data[44] == 0x01,
        fixed_flow=data[45] == 0x01,
        time_slots=data[46] == 0x01,
        air_flow=_le(data[47:49]) / 5,
        mechanical_version=data[50],
        season=SEASONS.get(data[51]),
        turbo_heater=data[52] == 0x01,
        preheat=data[53] == 0x01,
    )


def _parse_probes(data: bytes) -> Probes:
    probes = []
    for slot in range(PROBE_SLOTS):
        offset = 5 + slot * PROBE_SLOT_SIZE
        if offset + 3 >= len(data):
            break
        probes.append(
            Probe(
                slot=slot,
                location=data[offset],
                temperature=_signed(data[offset + 1]),
                humidity=data[offset + 3],
            )
        )
    return Probes(probes=probes)


def _parse_sensors(data: bytes) -> Sensors:
    sensors = []
    for slot in range(SENSOR_SLOTS):
        offset = 5 + slot * SENSOR_SLOT_SIZE
        if offset + SENSOR_SLOT_SIZE > len(data):
            break
        kind = SENSOR_KINDS.get(data[offset + 5], "unknown")
        if kind == "absent" or data[offset : offset + 4] == bytes(4):
            continue
        is_co2 = kind == "nexelec_co2"
        # The air-quality sensor (cov) carries its index at +6 and reports its
        # own temperature at +9, where the other sensors keep the temperature.
        is_cov = kind == "cov"
        sensors.append(
            Sensor(
                slot=slot,
                id=f"{_le(data[offset : offset + 4]):08X}",
                room=ROOMS.get(data[offset + 4], "unknown"),
                kind=kind,
                temperature=_signed(data[offset + 9 if is_cov else offset + 6])
                if not is_co2
                else None,
                co2=_le(data[offset + 6 : offset + 8]) if is_co2 else None,
                voc=data[offset + 6] if is_cov else None,
                humidity=data[offset + 8],
                data_c=data[offset + 9],
            )
        )
    return Sensors(sensors=sensors)


def _parse_time_slots(data: bytes) -> TimeSlots:
    days = []
    for day in range(TIME_SLOT_DAYS):
        slots = []
        for slot in range(TIME_SLOTS_PER_DAY):
            offset = 6 + (day * TIME_SLOTS_PER_DAY + slot) * 3
            if offset + 2 >= len(data) or data[offset] == EMPTY_SLOT_START:
                continue
            speed = _speed(data[offset + 1])
            if speed is None:
                continue
            slots.append(TimeSlot(data[offset], speed, data[offset + 2]))
        days.append(slots)
    return TimeSlots(enabled=data[5] == 0x01, days=days)


def _parse_bypass(data: bytes) -> BypassState:
    return BypassState(
        position=data[5],
        bypass_type=data[6],
        temperature=_signed(data[8]),
        id=f"{_le(data[17:21]):08X}",
        forced=data[21],
        requested_position=data[22],
    )


def _parse_gtc(data: bytes) -> GtcState:
    return GtcState(
        mode=data[5],
        address=data[6],
        baudrate=data[7],
        parity=data[8],
        stop_bit=data[9],
    )
