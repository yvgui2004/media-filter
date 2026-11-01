"""Data models. Plain dataclasses — the single source of truth for the table."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class MediaMetadata:
    """Metadata extracted from a single file via ffprobe."""

    duration: float = 0.0          # seconds
    video_bitrate: int = 0         # bits per second
    audio_bitrate: int = 0         # bits per second


@dataclass
class FileRecord:
    """One scanned file plus its probed metadata and UI state."""

    path: Path
    name: str
    extension: str                # lowercased, no dot: "mp4", "mkv", "flac" ...
    size: int                     # bytes
    mtime: float = 0.0            # file modification time (POSIX timestamp)
    metadata: MediaMetadata | None = None
    error: str | None = None      # probe failure message, if any
    checked: bool = False         # user-selected for batch/export

    @property
    def duration(self) -> float:
        return self.metadata.duration if self.metadata else 0.0

    @property
    def video_bitrate(self) -> int:
        return self.metadata.video_bitrate if self.metadata else 0

    @property
    def audio_bitrate(self) -> int:
        return self.metadata.audio_bitrate if self.metadata else 0

    @property
    def bitrate(self) -> int:
        """Best-effort combined bitrate: video if present, else format/audio."""
        return self.video_bitrate or self.audio_bitrate