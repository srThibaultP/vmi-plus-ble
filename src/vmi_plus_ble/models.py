"""Decoded frames."""

from __future__ import annotations

from dataclasses import dataclass, field

from .const import Speed


@dataclass(frozen=True, slots=True)
class Status:
    """State frame (0x01), answer to register 0x03."""

    serial: str
    box: str | None
    software_version: str
    electronic_version: int
    board_software_version: int
    mechanical_version: int
    action_in_progress: bool
    self_test: int
    self_test_details: str
    gtc: bool
    surface: int
    volume: int
    preheat_type: str | None
    bypass_open: bool
    operating_days: int
    filter_days: int
    night_boost: bool
    speed: Speed | None
    preheat_target: int
    summer_limit: int
    holiday: bool
    boost: bool
    fixed_flow: bool
    time_slots: bool
    air_flow: float
    season: str | None
    turbo_heater: bool
    preheat: bool

    @property
    def self_test_ok(self) -> bool:
        """True when the 5 self-tests of the Diagnostic screen passed."""
        return self.self_test == 0x1F


@dataclass(frozen=True, slots=True)
class Probe:
    """One wired probe of a ProbesState frame."""

    slot: int
    location: int
    temperature: int
    humidity: int


@dataclass(frozen=True, slots=True)
class Probes:
    """ProbesState frame (0x03), answer to register 0x07."""

    probes: list[Probe]

    @property
    def main(self) -> Probe | None:
        """First probe (the one the app shows as "Probe n°1")."""
        return self.probes[0] if self.probes else None


@dataclass(frozen=True, slots=True)
class Sensor:
    """One wireless sensor of a SensorsState frame."""

    slot: int
    id: str
    room: str
    kind: str
    temperature: int | None
    co2: int | None
    humidity: int
    data_c: int


@dataclass(frozen=True, slots=True)
class Sensors:
    """SensorsState frame (0x02), answer to register 0x06."""

    sensors: list[Sensor]

    @property
    def remote_control(self) -> Sensor | None:
        """The remote control, which carries the room temperature and humidity."""
        return next((sensor for sensor in self.sensors if sensor.kind == "remote_control"), None)


@dataclass(frozen=True, slots=True)
class TimeSlot:
    """One time slot: start hour, speed and preheat setpoint."""

    start: int
    speed: Speed
    temperature: int = 0xFF


@dataclass(frozen=True, slots=True)
class TimeSlots:
    """TimeSlotState frame (0x05): weekly programme, Monday first."""

    enabled: bool
    days: list[list[TimeSlot]]


@dataclass(frozen=True, slots=True)
class BypassState:
    """ByPassState frame (0x18), answer to register 0x14."""

    position: int
    bypass_type: int
    temperature: int
    id: str
    forced: int
    requested_position: int


@dataclass(frozen=True, slots=True)
class GtcState:
    """ErpState frame (0x16): building management (Modbus) settings."""

    mode: int
    address: int
    baudrate: int
    parity: int
    stop_bit: int


Frame = Status | Probes | Sensors | TimeSlots | BypassState | GtcState


@dataclass(slots=True)
class VmiPlusState:
    """Latest decoded value of each frame class."""

    status: Status | None = None
    probes: Probes | None = None
    sensors: Sensors | None = None
    time_slots: TimeSlots | None = None
    bypass: BypassState | None = None
    gtc: GtcState | None = None
    _fields: dict[type, str] = field(
        default_factory=lambda: {
            Status: "status",
            Probes: "probes",
            Sensors: "sensors",
            TimeSlots: "time_slots",
            BypassState: "bypass",
            GtcState: "gtc",
        },
        repr=False,
        compare=False,
    )

    def update(self, frame: Frame) -> None:
        """Stores a decoded frame."""
        setattr(self, self._fields[type(frame)], frame)
