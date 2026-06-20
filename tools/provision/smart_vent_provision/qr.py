"""Render a Matter QR-code payload string into a PIL Image.

The standalone `tools/qr-generator/generate_qr.py` writes a PNG file;
this module returns an in-memory image so the labels and kit-card
modules can embed it into PDFs without a temp file dance.
"""

from __future__ import annotations

import qrcode
from qrcode.constants import ERROR_CORRECT_M


def render(payload: str, *, box_size: int = 6, border: int = 2):
    """Return a PIL Image of the QR code for the given Matter payload.

    `box_size` is the pixel width of one QR module; `border` is in
    modules. ERROR_CORRECT_M (~15%) is a good balance for printed
    stickers — survives smudging but stays compact.
    """
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")
