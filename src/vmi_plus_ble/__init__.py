"""Bluetooth Low Energy client for Ventilairsec VMI+ / VMCI ventilation units."""

from __future__ import annotations

from importlib.metadata import version

from .client import VmiPlusClient
from .const import SERVICE_CONTROL_UUID, Register, Speed
from .exceptions import VmiPlusConnectionError, VmiPlusError, VmiPlusTimeoutError
from .models import (
    BypassState,
    GtcState,
    Probe,
    Probes,
    Sensor,
    Sensors,
    Status,
    TimeSlot,
    TimeSlots,
    VmiPlusState,
)
from .protocol import build_command, checksum, parse_frame

__version__ = version("vmi-plus-ble")

__all__ = [
    "SERVICE_CONTROL_UUID",
    "BypassState",
    "GtcState",
    "Probe",
    "Probes",
    "Register",
    "Sensor",
    "Sensors",
    "Speed",
    "Status",
    "TimeSlot",
    "TimeSlots",
    "VmiPlusClient",
    "VmiPlusConnectionError",
    "VmiPlusError",
    "VmiPlusState",
    "VmiPlusTimeoutError",
    "build_command",
    "checksum",
    "parse_frame",
]
