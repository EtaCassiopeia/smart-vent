"""Click CLI for the vent hub service."""

from __future__ import annotations

import asyncio
import logging
import sys

import click

from .coap_client import CoapClient
from .config import HubConfig
from .device_registry import DeviceRegistry
from .discovery import DeviceDiscovery
from .group_manager import GroupManager


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


@click.group()
@click.option("--config", "-c", default="config.yaml", help="Config file path")
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
@click.pass_context
def main(ctx, config, verbose):
    """Vent Hub CLI — control smart HVAC vents."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    ctx.ensure_object(dict)
    ctx.obj["config"] = HubConfig.load(config)


async def _get_services(config: HubConfig):
    """Initialize and return hub services."""
    registry = DeviceRegistry(config.db_path)
    await registry.open()
    coap = CoapClient()
    await coap.start()
    discovery = DeviceDiscovery(registry, coap, config.otbr_cmd)
    group_mgr = GroupManager(registry, coap)
    return registry, coap, discovery, group_mgr


@main.command()
@click.pass_context
def discover(ctx):
    """Discover vent devices on the Thread network."""

    async def _discover():
        config = ctx.obj["config"]
        registry, coap, discovery, _ = await _get_services(config)
        try:
            new = await discovery.discover()
            if new:
                click.echo(f"Discovered {len(new)} new device(s):")
                for d in new:
                    click.echo(f"  {d.eui64} at {d.ipv6_address}")
            else:
                click.echo("No new devices found.")
        finally:
            await coap.close()
            await registry.close()

    _run(_discover())


@main.command("list")
@click.pass_context
def list_devices(ctx):
    """List all registered vent devices."""

    async def _list():
        config = ctx.obj["config"]
        registry = DeviceRegistry(config.db_path)
        await registry.open()
        try:
            devices = await registry.list_all()
            if not devices:
                click.echo("No devices registered.")
                return
            click.echo(f"{'EUI-64':<26} {'Room':<15} {'Floor':<8} {'Angle':<7} {'State':<10}")
            click.echo("-" * 70)
            for d in devices:
                click.echo(
                    f"{d.eui64:<26} {d.room:<15} {d.floor:<8} {d.angle:<7} {d.state.value:<10}"
                )
        finally:
            await registry.close()

    _run(_list())


@main.command()
@click.argument("eui64")
@click.pass_context
def get(ctx, eui64):
    """Get details for a specific vent device."""

    async def _get():
        config = ctx.obj["config"]
        registry, coap, _, _ = await _get_services(config)
        try:
            device = await registry.get(eui64)
            if not device:
                click.echo(f"Device {eui64} not found.")
                return

            # Try live query if we have an address
            if device.ipv6_address:
                live = await coap.probe_device(device.ipv6_address)
                if live:
                    device = live

            click.echo(f"EUI-64:   {device.eui64}")
            click.echo(f"IPv6:     {device.ipv6_address}")
            click.echo(f"Room:     {device.room}")
            click.echo(f"Floor:    {device.floor}")
            click.echo(f"Name:     {device.name}")
            click.echo(f"Angle:    {device.angle}°")
            click.echo(f"State:    {device.state.value}")
            click.echo(f"Firmware: {device.firmware_version}")
            click.echo(f"RSSI:     {device.rssi} dBm")
            click.echo(f"Power:    {device.power_source.value}")
        finally:
            await coap.close()
            await registry.close()

    _run(_get())


@main.command()
@click.argument("eui64")
@click.argument("angle", type=int)
@click.pass_context
def set(ctx, eui64, angle):
    """Set vent angle for a specific device (90=closed, 180=open)."""

    async def _set():
        config = ctx.obj["config"]
        registry, coap, _, _ = await _get_services(config)
        try:
            device = await registry.get(eui64)
            if not device:
                click.echo(f"Device {eui64} not found.")
                return
            if not device.ipv6_address:
                click.echo(f"No IPv6 address for {eui64}.")
                return

            result = await coap.set_target(device.ipv6_address, angle)
            await registry.update_position(eui64, angle, "moving")
            click.echo(f"Target set to {angle}° for {eui64}")
        finally:
            await coap.close()
            await registry.close()

    _run(_set())


@main.command("set-room")
@click.argument("room")
@click.argument("angle", type=int)
@click.pass_context
def set_room(ctx, room, angle):
    """Set all vents in a room to the given angle."""

    async def _set_room():
        config = ctx.obj["config"]
        registry, coap, _, group_mgr = await _get_services(config)
        try:
            updated = await group_mgr.set_room_angle(room, angle)
            click.echo(f"Set {len(updated)} vent(s) in '{room}' to {angle}°")
        finally:
            await coap.close()
            await registry.close()

    _run(_set_room())


@main.command("set-floor")
@click.argument("floor")
@click.argument("angle", type=int)
@click.pass_context
def set_floor(ctx, floor, angle):
    """Set all vents on a floor to the given angle."""

    async def _set_floor():
        config = ctx.obj["config"]
        registry, coap, _, group_mgr = await _get_services(config)
        try:
            updated = await group_mgr.set_floor_angle(floor, angle)
            click.echo(f"Set {len(updated)} vent(s) on floor '{floor}' to {angle}°")
        finally:
            await coap.close()
            await registry.close()

    _run(_set_floor())


@main.command()
@click.argument("eui64")
@click.argument("room")
@click.argument("floor")
@click.pass_context
def assign(ctx, eui64, room, floor):
    """Assign a vent device to a room and floor."""

    async def _assign():
        config = ctx.obj["config"]
        registry, coap, _, _ = await _get_services(config)
        try:
            device = await registry.get(eui64)
            if not device:
                click.echo(f"Device {eui64} not found.")
                return

            # Update on-device config if reachable
            if device.ipv6_address:
                try:
                    await coap.set_config(device.ipv6_address, room=room, floor=floor)
                except Exception:
                    click.echo("Warning: could not update device config (device offline?)")

            await registry.update_assignment(eui64, room, floor)
            click.echo(f"Assigned {eui64} to room='{room}', floor='{floor}'")
        finally:
            await coap.close()
            await registry.close()

    _run(_assign())


if __name__ == "__main__":
    main()
