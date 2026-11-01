"""Filesystem traversal. Pure stdlib; no ffprobe involvement here."""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

VIDEO_EXTENSIONS = {
    "mp4", "mkv", "avi", "mov", "wmv", "flv", "webm", "m4v", "mpg", "mpeg",
    "ts", "m2ts", "3gp", "rmvb", "rm", "vob", "ogv",
}

AUDIO_EXTENSIONS = {
    "mp3", "flac", "wav", "aac", "ogg", "opus", "m4a", "wma", "ape", "aiff",
}

DEFAULT_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS


def scan_files(folder: str | Path, extensions: Iterable[str] | None = None) -> list[Path]:
    """Recursively collect media files under *folder*.

    Returns a list of absolute paths sorted by name (case-insensitive).
    Hidden directories (dot-prefixed) are skipped.
    """
    root = Path(folder)
    if not root.is_dir():
        return []

    wanted = {e.lower().lstrip(".") for e in (extensions or DEFAULT_EXTENSIONS)}
    results: list[Path] = []

    for current, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in files:
            ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
            if ext in wanted:
                results.append(Path(current) / name)

    results.sort(key=lambda p: p.name.lower())
    return results


def extension_of(path: str | Path) -> str:
    """Lowercased extension without the dot ('' when there is none)."""
    return Path(path).suffix.lstrip(".").lower()