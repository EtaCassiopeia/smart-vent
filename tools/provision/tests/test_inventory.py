import json
from pathlib import Path

import pytest

from smart_vent_provision.inventory import Inventory, Vent


def test_vent_eui_short():
    v = Vent(eui64="58:e6:c5:01:0a:dc", qr="MT:X", manual_code="123")
    assert v.eui_short == "0adc"


def test_vent_eui_short_handles_dash_separator():
    v = Vent(eui64="58-e6-c5-01-0a-dc", qr="MT:X", manual_code="123")
    assert v.eui_short == "0adc"


def test_inventory_roundtrip(tmp_path: Path):
    inv = Inventory(kit_id="kit-abc", firmware_version="firmware-v0.1.0")
    inv.add_vent(Vent(eui64="58:e6:c5:01:0a:dc", qr="MT:A", manual_code="111"))
    inv.add_vent(Vent(eui64="58:e6:c5:02:0a:dd", qr="MT:B", manual_code="222", label_hint="study"))

    out = tmp_path / "kits" / "kit-abc" / "inventory.json"
    inv.save(out)

    raw = json.loads(out.read_text())
    assert raw["kit_id"] == "kit-abc"
    assert len(raw["vents"]) == 2

    loaded = Inventory.load(out)
    assert loaded.kit_id == "kit-abc"
    assert loaded.vents[1].label_hint == "study"


def test_inventory_rejects_duplicate_eui():
    inv = Inventory(kit_id="k", firmware_version="v")
    inv.add_vent(Vent(eui64="58:e6:c5:01:0a:dc", qr="MT:A", manual_code="111"))
    with pytest.raises(ValueError):
        inv.add_vent(Vent(eui64="58:e6:c5:01:0a:dc", qr="MT:B", manual_code="222"))
