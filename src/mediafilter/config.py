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
    window_geometry: str = ""            # "X,Y,W,H"
    window_maximized: bool = False
    last_folder: str = ""
    presets: list[dict] = field(default_factory=list)    # user-customized presets
    cmd_history: list[str] = field(default_factory=list)  # recent custom commands
    ai_model_path: str = ""              # empty -> auto-discover <project>/models/*.onnx
    ai_sample_frames: int = 3            # frames sampled per video
    ai_threads: int = 2                  # parallel inference workers
    ai_conf: float = 0.25                # detection confidence threshold

    # Cloud recognition (settings page; no upload happens until a scan uses it)
    cloud_api_key_dpapi: str = ""        # DPAPI ciphertext, Base64
    cloud_api_key_hint: str = ""         # last four chars, display only
    cloud_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    cloud_model: str = ""
    cloud_model_name: str = ""
    cloud_model_context: str = ""
    cloud_model_capability: str = "unknown"  # image | verified_image | text | unknown
    cloud_model_probe_at: str = ""       # ISO timestamp of the last 96x96 probe
    cloud_model_cache: dict[str, str] = field(default_factory=dict)

    # Recognition behaviour (main-window mode button + settings page)
    recognition_mode: str = "local"      # active mode and next-launch default: local | hybrid | cloud
    custom_labels: list[str] = field(default_factory=list)  # user closed set, <= 10
    tag_palette: list[str] = field(default_factory=list)    # enabled built-in tag ids
    frame_policy: str = "auto"           # auto | fast | fine
    upload_target_only: bool = True      # hybrid: only upload frames that may hit custom labels
    local_color_tags: bool = True        # derive black/white/orange colours locally
    first_run_done: bool = False         # setup finished (saved at least once)
    first_run_prompted: bool = False     # the welcome dialog was shown once
    guide_dismissed: bool = False        # the non-blocking "finish setup" bar was closed

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
        cfg._source_path = target
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
        if path:
            target = Path(path)
        else:
            source = getattr(self, "_source_path", None)
            target = Path(source) if source else self.default_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )