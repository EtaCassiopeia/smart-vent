"""CLI for the vent device simulator."""

from __future__ import annotations

import asyncio
import logging

import click

from .simulator import VentSimulator


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
def main(verbose):
    """Vent Device Simulator — mock vent devices for testing."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@main.command()
@click.option("--count", "-n", default=3, help="Number of virtual vents")
@click.option("--base-port", "-p", default=5683, help="Base CoAP port")
@click.option("--bind", "-b", default="::1", help="Bind address")
def start(count, base_port, bind):
    """Start simulated vent devices."""
    sim = VentSimulator(base_port=base_port, bind_address=bind)

    # Create vents with varied configurations
    rooms = ["bedroom", "living-room", "kitchen", "office", "bathroom"]
    floors = ["1", "1", "1", "2", "2"]

    for i in range(count):
        room = rooms[i % len(rooms)]
        floor = floors[i % len(floors)]
        vent = sim.add_vent(room=room, floor=floor)
        click.echo(f"  Vent {vent.eui64} -> {room} (floor {floor}) on port {vent.port}")

    click.echo(f"\nStarting {count} virtual vent(s) on [{bind}]:{base_port}-{base_port + count - 1}")

    try:
        asyncio.run(sim.run_forever())
    except KeyboardInterrupt:
        click.echo("\nSimulator stopped.")


if __name__ == "__main__":
    main()
