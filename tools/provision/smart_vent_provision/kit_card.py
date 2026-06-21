"""One-page client quick-start PDF.

Bare-bones v1: kit ID, the AP-mode SSID/password placeholders, app
store links, support line. Provider can customize text via CLI flags.
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from .inventory import Inventory

PAGE_W, PAGE_H = LETTER


def render_pdf(
    inventory: Inventory,
    output: Path,
    *,
    ap_password: str = "",
    support_contact: str = "support@example.com",
) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(output), pagesize=LETTER)

    ap_ssid = f"smart-vent-setup-{inventory.kit_id[-4:]}"
    n_vents = len(inventory.vents)

    pdf.setFont("Helvetica-Bold", 28)
    pdf.drawString(0.75 * inch, PAGE_H - 1.2 * inch, "Welcome to smart-vent")

    pdf.setFont("Helvetica", 12)
    cursor = PAGE_H - 1.7 * inch
    line = lambda text, gap=0.25: (pdf.drawString(0.75 * inch, cursor, text), gap)

    cursor -= 0.05 * inch
    pdf.drawString(0.75 * inch, cursor, f"Your kit:  {inventory.kit_id}")
    cursor -= 0.25 * inch
    pdf.drawString(0.75 * inch, cursor, f"Includes:  {n_vents} vent{'s' if n_vents != 1 else ''}, 1 hub")
    cursor -= 0.5 * inch

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(0.75 * inch, cursor, "1.  Plug in the hub")
    cursor -= 0.30 * inch
    pdf.setFont("Helvetica", 11)
    pdf.drawString(0.95 * inch, cursor, "Power the hub from any USB-C charger. Wait ~30s for the LED.")
    cursor -= 0.50 * inch

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(0.75 * inch, cursor, "2.  Connect it to your WiFi")
    cursor -= 0.30 * inch
    pdf.setFont("Helvetica", 11)
    pdf.drawString(0.95 * inch, cursor, f"From your phone WiFi list, join:  {ap_ssid}")
    cursor -= 0.20 * inch
    if ap_password:
        pdf.drawString(0.95 * inch, cursor, f"Password:  {ap_password}")
        cursor -= 0.20 * inch
    pdf.drawString(0.95 * inch, cursor, "Enter your home WiFi name and password when prompted, then wait for reboot.")
    cursor -= 0.50 * inch

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(0.75 * inch, cursor, "3.  Install Home Assistant")
    cursor -= 0.30 * inch
    pdf.setFont("Helvetica", 11)
    pdf.drawString(0.95 * inch, cursor, "Search 'Home Assistant' on the App Store or Google Play.")
    cursor -= 0.20 * inch
    pdf.drawString(0.95 * inch, cursor, "Sign in to your hub when prompted (it auto-discovers on your network).")
    cursor -= 0.50 * inch

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(0.75 * inch, cursor, "4.  Add each vent")
    cursor -= 0.30 * inch
    pdf.setFont("Helvetica", 11)
    pdf.drawString(0.95 * inch, cursor, "Settings → Devices & services → Add Integration → Matter.")
    cursor -= 0.20 * inch
    pdf.drawString(0.95 * inch, cursor, "Scan the QR sticker on the vent, pick its room. Repeat for each vent.")
    cursor -= 0.80 * inch

    pdf.setFont("Helvetica-Oblique", 10)
    pdf.drawString(0.75 * inch, cursor, f"Need help?  {support_contact}")

    pdf.showPage()
    pdf.save()
    return output


def render_pdf_from_path(
    inventory_path: Path,
    output: Path,
    *,
    ap_password: str = "",
    support_contact: str = "support@example.com",
) -> Path:
    return render_pdf(
        Inventory.load(inventory_path),
        output,
        ap_password=ap_password,
        support_contact=support_contact,
    )
