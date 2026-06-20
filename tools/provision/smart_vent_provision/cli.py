"""smart-vent-provision: provider-side CLI for prepping kits.

Phases (separate by design — flashing and commissioning are not the
same thing):

  flash    — write firmware to N boards. Nothing else.
  capture  — read post-boot serial from one board; record its EUI-64,
             Matter QR payload, and manual pairing code into the kit
             inventory so we can print a sticker for it. Does NOT
             commission the device (that's the client's mobile app
             pairing the QR sticker into their HA fabric, including
             room/floor assignment).
  batch    — operator-convenience: walk N boards through flash + capture
             back to back.
  labels   — render an Avery 5160 sheet of stickers from the inventory.
  kit-card — render the one-page client quick-start PDF.

Run `smart-vent-provision <command> --help` for details.
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
    """Prep smart-vent kits: flash, capture, label, kit-card."""


# ----------------------------------------------------------------- flash
@main.command()
@click.option(
    "--count", "-n", type=int, default=1, show_default=True,
    help="Number of boards to flash one after another.",
)
@click.option(
    "--firmware-tag", type=str, default=None,
    help="Pin to a specific release tag (default: latest firmware-v*).",
)
@click.option(
    "--port", type=str, default=None,
    help="Force a specific /dev/tty path; otherwise auto-detect the single XIAO.",
)
def flash(count: int, firmware_tag: str | None, port: str | None) -> None:
    """Write firmware to N boards via espflash. Does not touch any inventory.

    Walk-through per board: BOOT-hold prompt -> espflash -> done.
    Commissioning (pairing to a Matter fabric, assigning to a room) is
    a separate step that the client does from their mobile app.
    """
    if count <= 0:
        raise click.BadParameter("count must be >= 1")

    bundle = release.fetch(firmware_tag)
    click.echo(f"Using firmware {bundle.version} (commit {bundle.commit[:7]}, chip {bundle.chip}).")

    for i in range(count):
        click.echo("")
        click.echo(click.style(f"=== board {i + 1} of {count} ===", bold=True))
        board_port = _prompt_and_resolve_port(port)
        click.echo("Flashing... (~10s)")
        flasher.flash(bundle, port=board_port)
        click.echo(click.style("  flashed.", fg="green"))


# --------------------------------------------------------------- capture
@main.command()
@click.option(
    "--kit-id", type=str, default=None,
    help="Kit identifier. Defaults to kit-<yyyymmdd>-<short-uid> when starting a new kit.",
)
@click.option(
    "--kit-root", type=click.Path(file_okay=False, path_type=Path), default=DEFAULT_KIT_ROOT,
    help="Where kit inventories are stored (default: ./kits).",
)
@click.option(
    "--firmware-version", type=str, default=None,
    help="Stamp this firmware version into a NEW inventory (informational).",
)
@click.option(
    "--port", type=str, default=None,
    help="Force a specific /dev/tty path; otherwise auto-detect the single XIAO.",
)
@click.option(
    "--label-hint", type=str, default="",
    help="Optional printed-sticker text for this vent (e.g. 'living room'). "
    "Purely cosmetic — does NOT assign the vent to a room. Room assignment "
    "is the client's mobile-app commissioning step.",
)
def capture(
    kit_id: str | None,
    kit_root: Path,
    firmware_version: str | None,
    port: str | None,
    label_hint: str,
) -> None:
    """Read one board's boot serial; append EUI/QR/pairing-code to the kit inventory.

    Assumes the board is already flashed and currently powered on. Power-
    cycle the board (no BOOT hold) first so the firmware emits a fresh
    boot banner with the values we need.
    """
    board_port = _prompt_and_resolve_port(port, instruction=
        "Power-cycle the board (unplug + replug, NO BOOT hold) so it emits a fresh boot banner."
    )

    click.echo(f"Reading {board_port} for QR + EUI + pairing code...")
    try:
        boot = serial_capture.capture(board_port, timeout_s=45.0)
    except serial_capture.CaptureTimeout as e:
        raise click.ClickException(str(e)) from None

    kit_id = kit_id or _default_kit_id()
    inventory_path = kit_root / kit_id / "inventory.json"
    inventory = _load_or_create(inventory_path, kit_id, firmware_version or "")

    vent = Vent(eui64=boot.eui64, qr=boot.qr, manual_code=boot.manual_code, label_hint=label_hint)
    try:
        inventory.add_vent(vent)
    except ValueError as e:
        raise click.ClickException(str(e)) from None

    inventory.save(inventory_path)
    click.echo(click.style(
        f"  appended: eui …{vent.eui_short} | code {vent.manual_code}"
        + (f" | hint '{label_hint}'" if label_hint else ""),
        fg="green",
    ))
    click.echo(f"  inventory: {inventory_path} ({len(inventory.vents)} vent(s))")


# ----------------------------------------------------------------- batch
@main.command()
@click.option("--count", "-n", type=int, required=True, help="Number of boards in this batch.")
@click.option(
    "--kit-id", type=str, default=None,
    help="Kit identifier. Defaults to kit-<yyyymmdd>-<short-uid>.",
)
@click.option(
    "--kit-root", type=click.Path(file_okay=False, path_type=Path), default=DEFAULT_KIT_ROOT,
)
@click.option(
    "--firmware-tag", type=str, default=None,
    help="Pin to a specific release tag (default: latest firmware-v*).",
)
@click.option(
    "--port", type=str, default=None,
    help="Force a specific /dev/tty path; otherwise auto-detect the single XIAO.",
)
@click.option(
    "--label-hints", type=str, default=None,
    help="Comma-separated cosmetic hints to print on each sticker (e.g. "
    "'living room,study,bedroom 1'). Applied in capture order; extras "
    "are ignored, shortages get blank.",
)
def batch(
    count: int,
    kit_id: str | None,
    kit_root: Path,
    firmware_tag: str | None,
    port: str | None,
    label_hints: str | None,
) -> None:
    """Convenience: walk N boards through flash + capture back-to-back.

    Equivalent to looping `flash` then `capture` per board, but with one
    cached firmware fetch and a single inventory file at the end.
    Commissioning (pairing + room assignment) is still entirely client-
    side via the mobile app.
    """
    if count <= 0:
        raise click.BadParameter("count must be >= 1")

    bundle = release.fetch(firmware_tag)
    click.echo(f"Using firmware {bundle.version} (commit {bundle.commit[:7]}, chip {bundle.chip}).")

    kit_id = kit_id or _default_kit_id()
    inventory_path = kit_root / kit_id / "inventory.json"
    inventory = _load_or_create(inventory_path, kit_id, bundle.version)
    hints = _split_csv(label_hints)

    for i in range(count):
        seq = len(inventory.vents) + 1
        click.echo("")
        click.echo(click.style(f"=== board {seq} (batch {i + 1} of {count}) ===", bold=True))
        board_port = _prompt_and_resolve_port(port,
            "Plug the XIAO directly into a USB port (not a hub).\n"
            "Hold BOOT, replug, release BOOT — then press <enter>.",
        )

        click.echo("Flashing...")
        flasher.flash(bundle, port=board_port)

        click.pause(info=
            "Now power-cycle the board (unplug + replug, NO BOOT hold), then press enter."
        )

        click.echo("Reading serial...")
        try:
            boot = serial_capture.capture(board_port, timeout_s=45.0)
        except serial_capture.CaptureTimeout as e:
            raise click.ClickException(str(e)) from None

        hint = hints[i] if i < len(hints) else ""
        vent = Vent(eui64=boot.eui64, qr=boot.qr, manual_code=boot.manual_code, label_hint=hint)
        try:
            inventory.add_vent(vent)
        except ValueError as e:
            raise click.ClickException(str(e)) from None

        inventory.save(inventory_path)
        click.echo(click.style(
            f"  ok: eui …{vent.eui_short} | code {vent.manual_code}"
            + (f" | hint '{hint}'" if hint else ""),
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


def _split_csv(spec: str | None) -> list[str]:
    if not spec:
        return []
    return [s.strip() for s in spec.split(",") if s.strip()]


def _prompt_and_resolve_port(
    explicit_port: str | None,
    instruction: str = (
        "Plug the XIAO directly into a USB port (not a hub).\n"
        "Hold BOOT, replug, release BOOT — then press <enter>."
    ),
) -> str:
    """Either trust an explicit port path or walk the operator through detection."""
    if explicit_port:
        devices.find_existing_port(explicit_port)
        return explicit_port
    click.echo(instruction)
    click.pause(info="(press enter once the board is ready)")
    board = devices.find_single_board()
    click.echo(f"  Found {board}")
    return board.port


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
