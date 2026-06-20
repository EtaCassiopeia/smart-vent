from smart_vent_provision.qr import render


def test_renders_a_pil_rgb_image():
    img = render("MT:Y3.13OTB00KA0648G00")
    assert img.mode == "RGB"
    # QR codes should be square.
    assert img.size[0] == img.size[1]
    # And big enough to scan from a phone — sanity floor.
    assert img.size[0] >= 100


def test_box_size_scales_image():
    small = render("MT:X", box_size=2, border=1)
    big = render("MT:X", box_size=10, border=1)
    assert big.size[0] > small.size[0]
