"""A tiny JSON-backed translator.

Qt ships QTranslator, but that requires compiling .ts -> .qm (lrelease) and a
second translation path for core/export string formatting. A plain JSON dict
kept this self-contained and unit-testable; widgets re-apply texts via
``retranslate()`` after ``set_language``.
"""

from __future__ import annotations

import json
from pathlib import Path


class Translator:
    def __init__(self, locale_dir: str | Path):
        self._locale_dir = Path(locale_dir)
        self._tables: dict[str, dict[str, str]] = {}
        self._fallback: dict[str, str] = {}
        self._current = "en"

    # -- loading ---------------------------------------------------------

    def _load(self, lang: str) -> dict[str, str]:
        if lang in self._tables:
            return self._tables[lang]
        path = self._locale_dir / f"{lang}.json"
        table: dict[str, str] = {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                table = {k: v for k, v in data.items() if isinstance(v, str)}
        except (OSError, json.JSONDecodeError):
            table = {}
        self._tables[lang] = table
        return table

    @property
    def fallback(self) -> dict[str, str]:
        return self._fallback

    def set_fallback(self, lang: str) -> None:
        self._fallback = self._load(lang)

    # -- api -------------------------------------------------------------

    def available_languages(self) -> list[str]:
        if not self._locale_dir.is_dir():
            return ["en"]
        return sorted(p.stem for p in self._locale_dir.glob("*.json"))

    def set_language(self, lang: str) -> None:
        self._load(lang)
        self._current = lang

    @property
    def language(self) -> str:
        return self._current

    def tr(self, key: str, **kwargs) -> str:
        text = (self._tables.get(self._current, {}) or {}).get(key)
        if text is None:
            text = self._fallback.get(key, key)
        if kwargs:
            try:
                text = text.format(**kwargs)
            except (KeyError, IndexError, ValueError):
                pass
        return text