"""App configuration: a small dataclass persisted as JSON under the user's
config directory (via platformdirs). Stdlib-only on purpose — this is simple
enough that pydantic would be ceremony, not safety."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import platformdirs


@dataclass
class Config:
    language: str = "zh"                 # "zh" | "en"
    theme_mode: str = "system"           # "light" | "dark" | "system"
    scan_threads: int = 8
    window_geometry: str = ""            # "WxH+X+Y"
    last_folder: str = ""
    presets: list[dict] = field(default_factory=list)    # user-customized presets
    cmd_history: list[str] = field(default_factory=list)  # recent custom commands

    @classmethod
    def default_path(cls) -> Path:
        return (
            Path(platformdirs.user_config_dir("media-filter-v2", appauthor=False))
            / "config.json"
        )

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Config":
        cfg = cls()
        target = Path(path) if path else cls.default_path()
        if not target.is_file():
            return cfg
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if isinstance(data, dict):
            for key, value in data.items():
                if hasattr(cfg, key) and not key.startswith("_"):
                    setattr(cfg, key, value)
        return cfg

    def save(self, path: str | Path | None = None) -> None:
        target = Path(path) if path else self.default_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )