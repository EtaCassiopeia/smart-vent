"""Per-kit inventory model: the source of truth for what's in a kit.

A kit's inventory.json is produced by `flash`, consumed by `labels`,
`kit-card`, and `image`. JSON is intentionally hand-editable so the
operator can fix a typo or add a room hint after the fact.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable


@dataclass
class Vent:
    eui64: str
    qr: str
    manual_code: str
    label_hint: str = ""

    @property
    def eui_short(self) -> str:
        """Last 4 hex characters of the EUI-64, no separators.

        Used on the printed label to match sticker to physical board.
        """
        cleaned = self.eui64.replace(":", "").replace("-", "").lower()
        return cleaned[-4:]


@dataclass
class Inventory:
    kit_id: str
    firmware_version: str
    hub_image_version: str = ""
    vents: list[Vent] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "Inventory":
        data = json.loads(Path(path).read_text())
        return cls(
            kit_id=data["kit_id"],
            firmware_version=data["firmware_version"],
            hub_image_version=data.get("hub_image_version", ""),
            vents=[Vent(**v) for v in data.get("vents", [])],
        )

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2) + "\n")

    def add_vent(self, vent: Vent) -> None:
        if any(v.eui64 == vent.eui64 for v in self.vents):
            raise ValueError(f"vent with EUI-64 {vent.eui64} is already in the kit")
        self.vents.append(vent)

    def extend(self, vents: Iterable[Vent]) -> None:
        for v in vents:
            self.add_vent(v)
