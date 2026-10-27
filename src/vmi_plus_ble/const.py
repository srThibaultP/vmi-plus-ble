"""GATT UUIDs, frame classes and command registers of VMI+ units.

See PROTOCOL.md in https://github.com/srThibaultP/ha-vmi-plus for the details.
"""

from __future__ import annotations

from enum import IntEnum

SERVICE_CONTROL_UUID = "0003cbbb-0000-1000-8000-00805f9b0131"
CHAR_CONTROL_UUID = "0003cbb1-0000-1000-8000-00805f9b0131"
SERVICE_TELEMETRY_UUID = "0003cab5-0000-1000-8000-00805f9b0131"
CHAR_TELEMETRY_UUID = "0003caa2-0000-1000-8000-00805f9b0131"

MAGIC = b"\xa5\xb6"


class FrameClass(IntEnum):
    """Byte [2] of a frame."""

    # Unit -> app
    STATE = 0x01
    SENSORS_STATE = 0x02
    PROBES_STATE = 0x03
    TIME_SLOT_STATE = 0x05
    ERP_STATE = 0x16
    BYPASS_STATE = 0x18
    # App -> unit
    COMMAND = 0x10
    CONFIG_TIME_SLOT = 0x19
    UPDATE_DATE = 0x1A


class Register(IntEnum):
    """Command registers (class 0x10) that are safe to send.

    Factory reset (0x13), firmware update, calibration, serialisation and the
    after-sales registers (0xf9-0xff) are deliberately left out.
    """

    LOCATE = 0x02
    STATE = 0x03
    NEW_FILTER = 0x05
    SENSORS = 0x06
    PROBES = 0x07
    NIGHT_BOOST_TOGGLE = 0x0B
    ERP_STATE = 0x12
    BYPASS = 0x14
    SUMMER_LIMIT = 0x17
    SPEED = 0x18
    BOOST = 0x19
    HOLIDAY = 0x1A
    FIXED_FLOW = 0x1B
    PREHEAT_TARGET = 0x1C
    TIME_SLOTS = 0x1D
    PREHEAT = 0x2F


class Speed(IntEnum):
    """Ventilation speed (register 0x18, status [34])."""

    LOW = 0
    MEDIUM = 1
    HIGH = 2


SUMMER_LIMIT_MIN = 22
SUMMER_LIMIT_MAX = 35
PREHEAT_TARGET_MIN = 12
PREHEAT_TARGET_MAX = 18
PREHEAT_OFF = 0
FILTER_LIFESPANS = (6, 12)

TIME_SLOT_DAYS = 7
TIME_SLOTS_PER_DAY = 5
EMPTY_SLOT_START = 0xFF
NO_SLOT_TEMPERATURE = 0xFF

SEASONS = {0x00: "summer", 0x01: "winter", 0x02: "intermediate"}
BOXES = {0x01: "Purevent", 0x02: "Urban", 0x03: "PRO", 0x05: "Cube"}
PREHEAT_TYPES = {
    0x01: "electric",
    0x02: "solar",
    0x03: "smart",
    0x04: "smart_partner",
    0x05: "partner",
}
SENSOR_KINDS = {
    0x00: "absent",
    0x01: "nexelec_co2",
    0x02: "nexelec_temperature",
    0x03: "remote_control",
    0x04: "box",
    0x05: "nanosense",
}
ROOMS = {
    0x00: "unknown",
    0x01: "living_room",
    0x02: "kitchen",
    0x03: "bathroom_1",
    0x04: "bathroom_2",
    0x05: "bedroom_1",
    0x06: "bedroom_2",
    0x07: "bedroom_3",
    0x08: "bedroom_4",
    0x09: "cellar",
}
