"""Disk cache for AI tags, keyed by file identity + model version.

Tagging costs ~0.3–1 s per video (ffmpeg seek + inference), so re-scanning a
folder must not redo the work. JSON is enough for a few thousand files.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

import platformdirs


def cache_key(path: str | Path, mtime: float, size: int, model_id: str) -> str:
    raw = f"{Path(path).resolve()}|{mtime:.3f}|{size}|{model_id}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


class TagCache:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else (
            Path(platformdirs.user_cache_dir("media-filter-v2", appauthor=False)) / "tags.json"
        )
        self._data: dict[str, list[str]] = {}
        self._dirty = False
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self._data = {k: list(v) for k, v in raw.items() if isinstance(v, list)}
        except (OSError, json.JSONDecodeError):
            self._data = {}

    def get(self, key: str) -> list[str] | None:
        return self._data.get(key)

    def put(self, key: str, tags: list[str]) -> None:
        self._data[key] = list(tags)
        self._dirty = True

    def save(self) -> None:
        if not self._dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, ensure_ascii=False)
            os.replace(tmp, self.path)
            self._dirty = False
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass