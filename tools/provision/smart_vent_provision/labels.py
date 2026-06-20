"""Generate a per-kit sticker sheet (Avery 5160).

Avery 5160: 30 labels per US-Letter page, 3 columns × 10 rows,
1" × 2.625" each. Tight fit — but a QR with EC=M scaled to ~0.75"
is still phone-scannable.

Each sticker shows:
  - QR code  (Matter payload, the only thing the mobile app cares about)
  - Last 4 of EUI-64  (so operator can match sticker to physical board)
  - Friendly label hint  ("study vent 1" etc.) when set on the Vent
"""

from __future__ import annotations

import io
from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .inventory import Inventory, Vent
from .qr import render

# Avery 5160 geometry.
PAGE_W, PAGE_H = LETTER
LABEL_W = 2.625 * inch
LABEL_H = 1.0 * inch
LABEL_COLS = 3
LABEL_ROWS = 10
HORIZONTAL_GAP = 0.125 * inch  # between columns
SIDE_MARGIN = 0.1875 * inch    # outer left/right
TOP_MARGIN = 0.5 * inch         # outer top (also bottom by symmetry)

LABELS_PER_PAGE = LABEL_COLS * LABEL_ROWS


def render_pdf(inventory: Inventory, output: Path) -> Path:
    """Render `inventory.vents` onto an Avery 5160 sheet at `output`."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(output), pagesize=LETTER)

    for page_offset in range(0, len(inventory.vents), LABELS_PER_PAGE):
        page_vents = inventory.vents[page_offset:page_offset + LABELS_PER_PAGE]
        _draw_page(pdf, page_vents, inventory.kit_id)
        pdf.showPage()

    pdf.save()
    return output


def _draw_page(pdf: canvas.Canvas, vents: list[Vent], kit_id: str) -> None:
    for slot, vent in enumerate(vents):
        col = slot % LABEL_COLS
        row = slot // LABEL_COLS

        x = SIDE_MARGIN + col * (LABEL_W + HORIZONTAL_GAP)
        # Y is measured from the bottom in ReportLab; row 0 is the
        # top, so flip.
        y = PAGE_H - TOP_MARGIN - (row + 1) * LABEL_H

        _draw_label(pdf, x, y, vent, kit_id)


def _draw_label(pdf: canvas.Canvas, x: float, y: float, vent: Vent, kit_id: str) -> None:
    qr_size = 0.75 * inch
    qr_padding = 0.05 * inch

    pdf.setLineWidth(0.25)
    pdf.rect(x, y, LABEL_W, LABEL_H, stroke=1, fill=0)

    # QR code on the left
    qr_img = render(vent.qr, box_size=8, border=2)
    qr_buf = io.BytesIO()
    qr_img.save(qr_buf, format="PNG")
    qr_buf.seek(0)
    pdf.drawImage(
        ImageReader(qr_buf),
        x + qr_padding,
        y + (LABEL_H - qr_size) / 2,
        width=qr_size,
        height=qr_size,
        preserveAspectRatio=True,
    )

    # Text on the right of the QR
    text_x = x + qr_size + qr_padding * 2
    text_top = y + LABEL_H - 0.18 * inch

    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(text_x, text_top, "smart-vent")

    pdf.setFont("Helvetica", 8)
    pdf.drawString(text_x, text_top - 0.15 * inch, f"id …{vent.eui_short}")

    label_hint = vent.label_hint or "room: ______________"
    pdf.drawString(text_x, text_top - 0.30 * inch, label_hint)

    pdf.setFont("Helvetica", 6)
    pdf.drawString(text_x, y + 0.06 * inch, kit_id)


def render_pdf_from_path(inventory_path: Path, output: Path) -> Path:
    return render_pdf(Inventory.load(inventory_path), output)
