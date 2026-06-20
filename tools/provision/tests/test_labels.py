"""Sanity tests for the labels PDF generator.

We don't visually verify — too brittle. We do confirm that the PDF
is created, is non-empty, and starts with %PDF-.
"""

from pathlib import Path

from smart_vent_provision.inventory import Inventory, Vent
from smart_vent_provision.labels import render_pdf


def _inventory(n: int) -> Inventory:
    inv = Inventory(kit_id="kit-test", firmware_version="firmware-v0.1.0")
    for i in range(n):
        inv.add_vent(
            Vent(
                eui64=f"58:e6:c5:01:0a:{i:02x}",
                qr=f"MT:TEST{i:03d}",
                manual_code=f"{1000 + i}",
                label_hint=f"room {i + 1}",
            )
        )
    return inv


def test_render_single_label(tmp_path: Path):
    inv = _inventory(1)
    out = tmp_path / "labels.pdf"
    render_pdf(inv, out)
    data = out.read_bytes()
    assert data.startswith(b"%PDF-")
    assert len(data) > 1024  # something more than an empty PDF


def test_render_full_page_of_labels(tmp_path: Path):
    inv = _inventory(30)
    out = tmp_path / "labels.pdf"
    render_pdf(inv, out)
    assert out.read_bytes().startswith(b"%PDF-")


def test_render_multipage(tmp_path: Path):
    inv = _inventory(31)  # 30 on page 1, 1 on page 2
    out = tmp_path / "labels.pdf"
    render_pdf(inv, out)
    # Both pages exist in a single PDF; we just need it to be longer
    # than the single-page output.
    single = tmp_path / "labels-single.pdf"
    render_pdf(_inventory(30), single)
    assert out.stat().st_size > single.stat().st_size
