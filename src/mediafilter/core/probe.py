"""ffprobe wrapper: run the binary, parse its JSON, return a MediaMetadata."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from .models import MediaMetadata

_WIN_PROBE_CANDIDATES = (
    r"C:\ffmpeg\bin\ffprobe.exe",
    r"C:\Program Files\ffmpeg\bin\ffprobe.exe",
)


class ProbeError(Exception):
    """Raised when metadata cannot be read from a file."""


def find_ffprobe() -> str | None:
    """Locate the ffprobe executable on PATH or common Windows locations."""
    on_path = shutil.which("ffprobe")
    if on_path:
        return on_path
    if os.name == "nt":
        for candidate in _WIN_PROBE_CANDIDATES:
            if os.path.isfile(candidate):
                return candidate
    return None


def probe_file(ffprobe_path: str | None, path: str | Path) -> MediaMetadata:
    """Extract duration / video bitrate / audio bitrate from one media file."""
    if not ffprobe_path:
        raise ProbeError("ffprobe not found on PATH")

    cmd = [
        ffprobe_path,
        "-v", "error",
        "-show_entries", "format=duration,bit_rate:stream=codec_type,bit_rate",
        "-of", "json",
        str(path),
    ]

    startupinfo = None
    if os.name == "nt":
        # Prevent a console window from flashing on each probe.
        startupinfo = subprocess.STARTUPINFO()  # type: ignore[attr-defined]
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore[attr-defined]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            startupinfo=startupinfo,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProbeError(f"ffprobe launch failed: {exc}") from exc

    if result.returncode != 0:
        detail = (result.stderr or "").strip()
        raise ProbeError(detail[:200] or f"exit code {result.returncode}")

    return parse_probe_json(result.stdout)


def parse_probe_json(stdout: str) -> MediaMetadata:
    """Parse ffprobe ``-of json`` output into a MediaMetadata.

    Kept separate from ``probe_file`` so it is unit-testable against fixture
    strings without spawning a process.
    """
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ProbeError("invalid ffprobe JSON output") from exc

    fmt = data.get("format", {})
    duration = _to_float(fmt.get("duration"), 0.0)
    format_bitrate = _to_int(fmt.get("bit_rate"), 0)

    video_bitrate = 0
    audio_bitrate = 0
    for stream in data.get("streams", []):
        codec_type = stream.get("codec_type")
        rate = _to_int(stream.get("bit_rate"), 0)
        if codec_type == "video" and rate > 0 and video_bitrate == 0:
            video_bitrate = rate
        elif codec_type == "audio" and rate > 0 and audio_bitrate == 0:
            audio_bitrate = rate

    # Some containers only carry a container-level bitrate; treat it as the
    # video rate minus any audio, best-effort.
    if video_bitrate == 0 and format_bitrate > 0:
        video_bitrate = max(0, format_bitrate - audio_bitrate) if audio_bitrate else format_bitrate

    return MediaMetadata(
        duration=duration,
        video_bitrate=video_bitrate,
        audio_bitrate=audio_bitrate,
    )


def _to_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default