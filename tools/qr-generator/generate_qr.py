#!/usr/bin/env python3
"""Generate a printable QR code from a Matter QR payload string.

Usage:
    python generate_qr.py "MT:Y3.13OTB00KA0648G00"
    python generate_qr.py "MT:Y3.13OTB00KA0648G00" --output vent-qr.png
"""

import argparse
import sys

try:
    import qrcode
except ImportError:
    print("Install qrcode: pip install qrcode[pil]", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Generate a Matter QR code for device commissioning"
    )
    parser.add_argument("payload", help="Matter QR payload string (e.g. MT:...)")
    parser.add_argument(
        "--output", "-o", default="matter-qr.png", help="Output PNG file path"
    )
    parser.add_argument(
        "--size", type=int, default=10, help="Box size in pixels (default: 10)"
    )
    args = parser.parse_args()

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=args.size,
        border=4,
    )
    qr.add_data(args.payload)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    img.save(args.output)
    print(f"QR code saved to {args.output}")


if __name__ == "__main__":
    main()
