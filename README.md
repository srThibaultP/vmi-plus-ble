# vmi-plus-ble

Asynchronous Python client for **Ventilairsec VMI+ / VMCI** ventilation units over Bluetooth Low
Energy (tested on an Urban unit). It powers the
[ha-vmi-plus](https://github.com/srThibaultP/ha-vmi-plus) Home Assistant integration.

The protocol was reverse-engineered from the official VMI+ app and is documented in
[PROTOCOL.md](https://github.com/srThibaultP/ha-vmi-plus/blob/main/PROTOCOL.md).

## Install

```bash
pip install vmi-plus-ble
```

Python 3.12+, built on [bleak](https://github.com/hbldh/bleak) and
[bleak-retry-connector](https://github.com/Bluetooth-Devices/bleak-retry-connector).

## Usage

```python
import asyncio

from bleak import BleakScanner
from vmi_plus_ble import SERVICE_CONTROL_UUID, Speed, VmiPlusClient


async def main() -> None:
    devices = await BleakScanner.discover(service_uuids=[SERVICE_CONTROL_UUID])
    client = VmiPlusClient(devices[0])
    try:
        state = await client.update()
        print(state.status.speed, state.status.filter_days, state.probes.main)
        await client.set_speed(Speed.HIGH)
    finally:
        await client.disconnect()


asyncio.run(main())
```

The unit accepts **one connection at a time**: disconnect before using the official app.

| Method | Effect |
|---|---|
| `update(bypass=False)` | reads the status, probes and wireless sensors (and the bypass state) |
| `set_speed(Speed)` | low / medium / high |
| `set_boost(bool)` | 30 min boost |
| `set_preheat(bool)` | preheat button |
| `set_holiday(bool)` | holiday mode |
| `set_night_boost(bool)` | night ventilation boost |
| `set_fixed_flow(bool)` | fixed air flow (radon) mode |
| `set_time_slots(bool)` | weekly programme on/off, returns the programme |
| `set_day_schedule(day, slots)` | programmes one day (up to 5 `TimeSlot`) |
| `set_summer_limit(°C)` | summer supply-air limit, 22–35 |
| `set_preheat_target(°C)` | preheat target, 12–18, 0 = off |
| `locate()` | blinks the LED |
| `declare_new_filter(months)` | new filter (6 or 12 months, sent to the unit as 26 or 52 weeks), restarts the filter counter |
| `sync_clock()` | sets the unit's clock |
| `set_sensor_period(sensor_id, minutes)` | measurement period of a paired wireless sensor (10, 20, 30, 40 or 50 minutes); write-only, and it restarts a VOC sensor's measurement |

Errors are raised as `VmiPlusConnectionError` or `VmiPlusTimeoutError` (both `VmiPlusError`).
Factory reset, firmware update and after-sales commands are deliberately not implemented.

`parse_frame()` and `build_command()` give access to the frame codec without any I/O.

## Command line

```bash
vmi-plus-ble scan
vmi-plus-ble status AA:BB:CC:DD:EE:FF
vmi-plus-ble speed AA:BB:CC:DD:EE:FF high
```

## Development

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest --cov
.venv/bin/mypy
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

Releases are published to PyPI by GitHub Actions when a `v*` tag is pushed.

## Disclaimer

Not affiliated with Ventilairsec. MIT licence.
