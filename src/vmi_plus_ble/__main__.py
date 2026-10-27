"""Command-line tool: ``python -m vmi_plus_ble`` (or ``vmi-plus-ble``)."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict

from bleak import BleakScanner

from .client import VmiPlusClient
from .const import SERVICE_CONTROL_UUID, Speed


async def _scan(_args: argparse.Namespace) -> None:
    devices = await BleakScanner.discover(timeout=10, service_uuids=[SERVICE_CONTROL_UUID])
    for device in devices:
        print(f"{device.address}  {device.name}")
    if not devices:
        print("No unit found (is the official app or Home Assistant connected to it?)")


async def _client(address: str) -> VmiPlusClient:
    device = await BleakScanner.find_device_by_address(address, timeout=20)
    if device is None:
        raise SystemExit(f"{address} not found")
    return VmiPlusClient(device)


async def _run(args: argparse.Namespace) -> None:
    client = await _client(args.address)
    try:
        match args.command:
            case "status":
                state = await client.update(bypass=True)
                for name in ("status", "probes", "sensors", "bypass"):
                    value = getattr(state, name)
                    print(f"{name}: {asdict(value) if value else None}")
            case "speed":
                await client.set_speed(Speed[args.level.upper()])
            case "boost":
                await client.set_boost(args.state == "on")
            case "preheat":
                await client.set_preheat(args.state == "on")
            case "locate":
                await client.locate()
    finally:
        await client.disconnect()


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(prog="vmi-plus-ble", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("scan", help="list the units in range")
    for name in ("status", "locate"):
        sub.add_parser(name).add_argument("address")
    speed = sub.add_parser("speed")
    speed.add_argument("address")
    speed.add_argument("level", choices=["low", "medium", "high"])
    for name in ("boost", "preheat"):
        command = sub.add_parser(name)
        command.add_argument("address")
        command.add_argument("state", choices=["on", "off"])
    args = parser.parse_args()
    asyncio.run(_scan(args) if args.command == "scan" else _run(args))


if __name__ == "__main__":
    main()
