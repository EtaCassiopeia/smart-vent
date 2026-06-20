"""smart-vent-provision: provider-side CLI for prepping kits.

Run `smart-vent-provision --help` for the command list.
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

import click

from . import __version__, devices, flasher, kit_card, labels, release, serial_capture
from .inventory import Inventory, Vent

DEFAULT_KIT_ROOT = Path.cwd() / "kits"


@click.group()
@click.version_option(__version__, prog_name="smart-vent-provision")
def main() -> None:
    """Prep smart-vent kits: bulk flash, label, kit-card."""


# ----------------------------------------------------------------- flash
@main.command()
@click.option("--count", "-n", type=int, required=True, help="Number of vents in this batch.")
@click.option(
    "--kit-id",
    type=str,
    default=None,
    help="Kit identifier. Defaults to kit-<yyyymmdd>-<short-uid>.",
)
@click.option(
    "--kit-root",
    type=click.Path(file_okay=False, path_type=Path),
    default=DEFAULT_KIT_ROOT,
    help="Where kit inventories are stored (default: ./kits).",
)
@click.option(
    "--firmware-tag",
    type=str,
    default=None,
    help="Pin to a specific release tag (default: latest firmware-v*).",
)
@click.option(
    "--port",
    type=str,
    default=None,
    help="Force a specific /dev/tty path; otherwise auto-detect the single XIAO.",
)
@click.option(
    "--rooms",
    type=str,
    default=None,
    help="Comma-separated room hints to pre-fill (e.g. 'living_room,study,bedroom_1'). "
    "Applied in order; extras are ignored, shortages get blank.",
)
def flash(
    count: int,
    kit_id: str | None,
    kit_root: Path,
    firmware_tag: str | None,
    port: str | None,
    rooms: str | None,
) -> None:
    """Flash N vents one at a time, capturing QR + EUI into the kit inventory."""

    if count <= 0:
        raise click.BadParameter("count must be >= 1")

    bundle = release.fetch(firmware_tag)
    click.echo(f"Using firmware {bundle.version} (commit {bundle.commit[:7]}, chip {bundle.chip}).")

    kit_id = kit_id or _default_kit_id()
    inventory_path = kit_root / kit_id / "inventory.json"
    inventory = _load_or_create(inventory_path, kit_id, bundle.version)

    room_hints = _split_rooms(rooms)

    for i in range(count):
        seq = len(inventory.vents) + 1
        click.echo("")
        click.echo(click.style(f"=== vent {seq} of {len(inventory.vents) + count} ===", bold=True))
        if port:
            _ = devices.find_existing_port(port)
            board_port = port
        else:
            click.echo("Plug the XIAO directly into a USB port (not a hub).")
            click.echo("Hold BOOT, replug, release BOOT — then press <enter>.")
            click.pause(info="(press enter once it's in download mode)")
            board = devices.find_single_board()
            board_port = board.port
            click.echo(f"  Found {board}")

        click.echo("Flashing... (~10s)")
        flasher.flash(bundle, port=board_port)

        click.echo("Power-cycle the board (unplug + replug, NO BOOT hold) to boot the new firmware.")
        click.pause(info="(press enter once the board is back, then wait for the boot banner)")

        click.echo("Reading serial for QR + EUI...")
        try:
            boot = serial_capture.capture(board_port, timeout_s=45.0)
        except serial_capture.CaptureTimeout as e:
            raise click.ClickException(str(e)) from None

        hint = room_hints[i] if i < len(room_hints) else ""
        vent = Vent(eui64=boot.eui64, qr=boot.qr, manual_code=boot.manual_code, label_hint=hint)
        try:
            inventory.add_vent(vent)
        except ValueError as e:
            raise click.ClickException(str(e)) from None

        inventory.save(inventory_path)
        click.echo(click.style(
            f"  ok: eui …{vent.eui_short} | code {vent.manual_code} | {hint or '(no room hint)'}",
            fg="green",
        ))

    click.echo("")
    click.echo(click.style(
        f"Wrote {len(inventory.vents)} vents to {inventory_path}",
        bold=True,
    ))


# ---------------------------------------------------------------- labels
@main.command()
@click.option("--kit", required=True, type=str, help="Kit ID (subdir of --kit-root).")
@click.option(
    "--kit-root",
    type=click.Path(file_okay=False, path_type=Path),
    default=DEFAULT_KIT_ROOT,
)
@click.option(
    "--out",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Output PDF path (default: <kit>/labels.pdf).",
)
def labels_cmd(kit: str, kit_root: Path, out: Path | None) -> None:
    """Render an Avery 5160 sheet of QR stickers for a kit."""
    inv_path = kit_root / kit / "inventory.json"
    if not inv_path.exists():
        raise click.ClickException(f"inventory not found: {inv_path}")
    if out is None:
        out = kit_root / kit / "labels.pdf"
    labels.render_pdf_from_path(inv_path, out)
    click.echo(f"Wrote {out}")


main.add_command(labels_cmd, name="labels")


# -------------------------------------------------------------- kit-card
@main.command(name="kit-card")
@click.option("--kit", required=True, type=str)
@click.option(
    "--kit-root",
    type=click.Path(file_okay=False, path_type=Path),
    default=DEFAULT_KIT_ROOT,
)
@click.option(
    "--out",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Output PDF path (default: <kit>/kit-card.pdf).",
)
@click.option(
    "--ap-password",
    type=str,
    default="",
    help="If set, printed on the card as the first-boot AP-mode WiFi password.",
)
@click.option(
    "--support-contact",
    type=str,
    default="support@example.com",
    help="Support email or phone shown at the bottom of the card.",
)
def kit_card_cmd(
    kit: str,
    kit_root: Path,
    out: Path | None,
    ap_password: str,
    support_contact: str,
) -> None:
    """Render a one-page client quick-start card."""
    inv_path = kit_root / kit / "inventory.json"
    if not inv_path.exists():
        raise click.ClickException(f"inventory not found: {inv_path}")
    if out is None:
        out = kit_root / kit / "kit-card.pdf"
    kit_card.render_pdf_from_path(
        inv_path,
        out,
        ap_password=ap_password,
        support_contact=support_contact,
    )
    click.echo(f"Wrote {out}")


# --------------------------------------------------------------- helpers
def _default_kit_id() -> str:
    import uuid

    today = datetime.date.today().isoformat()
    return f"kit-{today}-{uuid.uuid4().hex[:6]}"


def _split_rooms(spec: str | None) -> list[str]:
    if not spec:
        return []
    return [s.strip() for s in spec.split(",") if s.strip()]


def _load_or_create(
    inventory_path: Path, kit_id: str, firmware_version: str
) -> Inventory:
    if inventory_path.exists():
        existing = Inventory.load(inventory_path)
        if existing.kit_id != kit_id:
            click.echo(
                click.style(
                    f"warning: existing inventory has kit_id={existing.kit_id}, "
                    f"continuing with that (your --kit-id={kit_id} is ignored)",
                    fg="yellow",
                ),
                err=True,
            )
        return existing
    return Inventory(kit_id=kit_id, firmware_version=firmware_version)


if __name__ == "__main__":
    sys.exit(main())
