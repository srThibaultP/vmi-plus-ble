"""Asynchronous BLE client for a VMI+ unit."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from datetime import datetime

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    establish_connection,
)

from .const import (
    CHAR_CONTROL_UUID,
    CHAR_TELEMETRY_UUID,
    FILTER_LIFESPAN_WEEKS,
    FILTER_LIFESPANS,
    PREHEAT_OFF,
    PREHEAT_TARGET_MAX,
    PREHEAT_TARGET_MIN,
    SENSOR_PERIODS,
    SUMMER_LIMIT_MAX,
    SUMMER_LIMIT_MIN,
    Register,
    Speed,
)
from .exceptions import VmiPlusConnectionError, VmiPlusTimeoutError
from .models import (
    BypassState,
    Frame,
    Probes,
    Sensors,
    Status,
    TimeSlot,
    TimeSlots,
    VmiPlusState,
)
from .protocol import (
    build_command,
    build_date_frame,
    build_sensor_period_frame,
    build_time_slot_frame,
    parse_frame,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10.0

# Read register -> frame type the unit answers with.
_ANSWERS: dict[Register, type[Frame]] = {
    Register.STATE: Status,
    Register.PROBES: Probes,
    Register.SENSORS: Sensors,
    Register.BYPASS: BypassState,
    Register.TIME_SLOTS: TimeSlots,
}


class VmiPlusClient:
    """Talks to one unit over a single GATT connection.

    The unit accepts only one central at a time: while this client is
    connected, the official app cannot connect.
    """

    def __init__(
        self,
        ble_device: BLEDevice,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        on_update: Callable[[VmiPlusState], None] | None = None,
        on_disconnect: Callable[[], None] | None = None,
    ) -> None:
        self._ble_device = ble_device
        self._timeout = timeout
        self._on_update = on_update
        self._on_disconnect = on_disconnect
        self._client: BleakClientWithServiceCache | None = None
        self._lock = asyncio.Lock()
        self._waiters: dict[type[Frame], list[asyncio.Future[Frame]]] = {}
        self.state = VmiPlusState()

    @property
    def address(self) -> str:
        """Bluetooth address of the unit."""
        return self._ble_device.address

    @property
    def is_connected(self) -> bool:
        """True while the GATT connection is up."""
        return self._client is not None and self._client.is_connected

    def set_ble_device(self, ble_device: BLEDevice) -> None:
        """Updates the BLEDevice used for the next connection (e.g. another adapter)."""
        self._ble_device = ble_device

    async def connect(self) -> None:
        """Connects and subscribes to the telemetry notifications."""
        async with self._lock:
            await self._ensure_connected()

    async def disconnect(self) -> None:
        """Closes the connection, which frees the unit for the official app."""
        async with self._lock:
            client, self._client = self._client, None
            if client is not None:
                try:
                    await client.disconnect()
                except BleakError as err:  # pragma: no cover - best effort
                    _LOGGER.debug("Error while disconnecting from %s: %s", self.address, err)

    async def update(self, *, bypass: bool = False) -> VmiPlusState:
        """Reads the status, probes and sensors (and the bypass state if asked)."""
        registers = [Register.STATE, Register.PROBES, Register.SENSORS]
        if bypass:
            registers.append(Register.BYPASS)
        for register in registers:
            await self._request(register)
        return self.state

    async def set_speed(self, speed: Speed) -> None:
        """Sets the ventilation speed."""
        await self._write(Register.SPEED, Speed(speed))

    async def set_boost(self, on: bool) -> None:
        """Turns the 30 min boost on or off."""
        await self._write(Register.BOOST, int(on))

    async def set_preheat(self, on: bool) -> None:
        """Turns preheating on or off (home screen button)."""
        await self._write(Register.PREHEAT, int(on))

    async def set_holiday(self, on: bool) -> None:
        """Turns holiday mode on or off."""
        await self._write(Register.HOLIDAY, int(on))

    async def set_fixed_flow(self, on: bool) -> None:
        """Turns the fixed air flow (radon) mode on or off."""
        await self._write(Register.FIXED_FLOW, int(on))

    async def set_night_boost(self, on: bool) -> None:
        """Turns the night ventilation boost on or off.

        The unit only knows a toggle command, so the current state is read
        first and the toggle is sent only when it differs.
        """
        status = await self._request(Register.STATE)
        assert isinstance(status, Status)
        if status.night_boost != on:
            await self._write(Register.NIGHT_BOOST_TOGGLE, 0)

    async def set_time_slots(self, on: bool) -> TimeSlots:
        """Turns the weekly programme on or off and returns it.

        Turning it on applies the programme at once.
        """
        frame = await self._request(Register.TIME_SLOTS, int(on))
        assert isinstance(frame, TimeSlots)
        return frame

    async def set_day_schedule(self, day: int, slots: Sequence[TimeSlot]) -> None:
        """Programs one day (1 = Monday) with up to 5 slots; no slot clears the day."""
        await self._send(build_time_slot_frame(day, slots))

    async def set_summer_limit(self, temperature: int) -> None:
        """Sets the summer supply-air limit (22-35 °C)."""
        if not SUMMER_LIMIT_MIN <= temperature <= SUMMER_LIMIT_MAX:
            raise ValueError(f"summer limit must be {SUMMER_LIMIT_MIN}-{SUMMER_LIMIT_MAX} °C")
        await self._write(Register.SUMMER_LIMIT, temperature)

    async def set_preheat_target(self, temperature: int) -> None:
        """Sets the preheat target (12-18 °C, 0 = no preheating)."""
        if temperature != PREHEAT_OFF and not (
            PREHEAT_TARGET_MIN <= temperature <= PREHEAT_TARGET_MAX
        ):
            raise ValueError(
                f"preheat target must be 0 or {PREHEAT_TARGET_MIN}-{PREHEAT_TARGET_MAX} °C"
            )
        await self._write(Register.PREHEAT_TARGET, temperature)

    async def locate(self) -> None:
        """Blinks the unit's LED."""
        await self._write(Register.LOCATE, 0)

    async def declare_new_filter(self, months: int) -> None:
        """Declares a new filter; restarts the filter counter. Only after a real change."""
        if months not in FILTER_LIFESPANS:
            raise ValueError(f"filter lifespan must be one of {FILTER_LIFESPANS} months")
        await self._write(Register.NEW_FILTER, FILTER_LIFESPAN_WEEKS[months])

    async def set_sensor_period(self, sensor_id: str, minutes: int) -> None:
        """Sets how often a paired wireless sensor measures (10-50 minutes).

        The unit cannot report the period back. Changing it restarts the VOC
        sensor's measurement, which then needs about five periods to settle.
        """
        if minutes not in SENSOR_PERIODS:
            raise ValueError(f"sensor period must be one of {SENSOR_PERIODS} minutes")
        if len(sensor_id) != 8 or any(c not in "0123456789abcdefABCDEF" for c in sensor_id):
            raise ValueError(f"invalid sensor id {sensor_id!r}")
        await self._send(build_sensor_period_frame(sensor_id, minutes))

    async def sync_clock(self, moment: datetime | None = None) -> None:
        """Sets the unit's clock (the app does it on every connection)."""
        await self._send(build_date_frame(moment or datetime.now()))

    async def _write(self, register: Register, value: int) -> None:
        await self._send(build_command(register, value))

    async def _request(self, register: Register, value: int = 0) -> Frame:
        """Sends a command and waits for the frame the unit answers with."""
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Frame] = loop.create_future()
        waiters = self._waiters.setdefault(_ANSWERS[register], [])
        waiters.append(future)
        try:
            await self._send(build_command(register, value))
            async with asyncio.timeout(self._timeout):
                return await future
        except TimeoutError as err:
            raise VmiPlusTimeoutError(
                f"No answer from {self.address} to register {register:#04x}"
            ) from err
        finally:
            if future in waiters:
                waiters.remove(future)

    async def _send(self, frame: bytes) -> None:
        async with self._lock:
            client = await self._ensure_connected()
            try:
                await client.write_gatt_char(CHAR_CONTROL_UUID, frame, response=True)
            except BleakError as err:
                raise VmiPlusConnectionError(f"Write to {self.address} failed: {err}") from err

    async def _ensure_connected(self) -> BleakClientWithServiceCache:
        if self._client is not None and self._client.is_connected:
            return self._client
        _LOGGER.debug("Connecting to %s", self.address)
        try:
            client = await establish_connection(
                BleakClientWithServiceCache,
                self._ble_device,
                self._ble_device.name or self.address,
                disconnected_callback=self._handle_disconnect,
            )
            await client.start_notify(CHAR_TELEMETRY_UUID, self._handle_notification)
        except (BleakError, TimeoutError) as err:
            raise VmiPlusConnectionError(f"Cannot connect to {self.address}: {err}") from err
        self._client = client
        return client

    def _handle_disconnect(self, _client: object) -> None:
        _LOGGER.debug("Disconnected from %s", self.address)
        self._client = None
        for waiters in self._waiters.values():
            for future in waiters:
                if not future.done():
                    future.set_exception(VmiPlusConnectionError("Connection lost"))
        if self._on_disconnect is not None:
            self._on_disconnect()

    def _handle_notification(self, _char: BleakGATTCharacteristic, data: bytearray) -> None:
        frame = parse_frame(bytes(data))
        if frame is None:
            _LOGGER.debug("Ignored frame from %s: %s", self.address, data.hex())
            return
        self.state.update(frame)
        for future in self._waiters.pop(type(frame), []):
            if not future.done():
                future.set_result(frame)
        if self._on_update is not None:
            self._on_update(self.state)
