"""Hub configuration management."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class HubConfig:
    """Hub service configuration."""

    otbr_url: str = "http://localhost:8081"
    db_path: str = "devices.db"
    poll_interval_s: int = 30
    discovery_interval_s: int = 300
    log_level: str = "INFO"
    scheduler_rules: list[dict] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path = "config.yaml") -> HubConfig:
        """Load configuration from a YAML file."""
        p = Path(path)
        if not p.exists():
            return cls()

        with open(p) as f:
            data = yaml.safe_load(f) or {}

        return cls(
            otbr_url=data.get("otbr_url", cls.otbr_url),
            db_path=data.get("db_path", cls.db_path),
            poll_interval_s=data.get("poll_interval_s", cls.poll_interval_s),
            discovery_interval_s=data.get("discovery_interval_s", cls.discovery_interval_s),
            log_level=data.get("log_level", cls.log_level),
            scheduler_rules=data.get("scheduler_rules", []),
        )

    def save(self, path: str | Path = "config.yaml") -> None:
        """Save configuration to a YAML file."""
        data = {
            "otbr_url": self.otbr_url,
            "db_path": self.db_path,
            "poll_interval_s": self.poll_interval_s,
            "discovery_interval_s": self.discovery_interval_s,
            "log_level": self.log_level,
            "scheduler_rules": self.scheduler_rules,
        }
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False)
