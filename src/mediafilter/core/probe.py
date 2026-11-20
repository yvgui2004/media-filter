"""ffprobe wrapper: run the binary, parse its JSON, return a MediaMetadata."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from .models import MediaMetadata

_WIN_PROBE_CANDIDATES = (
    r"C:\ffmpeg\bin\ffprobe.exe",
    r"C:\Program Files\ffmpeg\bin\ffprobe.exe",
)


class ProbeError(Exception):
    """Raised when metadata cannot be read from a file."""


class ProbeCancelled(ProbeError):
    """The scan was cancelled while ffprobe was running."""


def _portable_dirs() -> list[Path]:
    """Folders that ship beside the app executable.

    The portable build puts ``ffmpeg/bin`` next to ``MediaFilter.exe`` so the
    package works without installing anything. In onefile mode ``sys.executable``
    is the real .exe path, not the temporary extraction directory.
    """
    if not getattr(sys, "frozen", False):
        return []
    root = Path(sys.executable).resolve().parent
    return [root, root / "ffmpeg" / "bin"]


def find_ffprobe() -> str | None:
    """Locate ffprobe: PATH, portable folders, then common Windows locations."""
    on_path = shutil.which("ffprobe")
    if on_path:
        return on_path
    for folder in _portable_dirs():
        candidate = folder / ("ffprobe.exe" if os.name == "nt" else "ffprobe")
        if candidate.is_file():
            return str(candidate)
    if os.name == "nt":
        for candidate in _WIN_PROBE_CANDIDATES:
            if os.path.isfile(candidate):
                return candidate
    return None


def find_ffmpeg(ffprobe_path: str | None = None) -> str | None:
    """Locate ffmpeg: PATH first, else next to a known ffprobe."""
    on_path = shutil.which("ffmpeg")
    if on_path:
        return on_path
    if ffprobe_path:
        sibling = Path(ffprobe_path).with_name("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        if sibling.is_file():
            return str(sibling)
    for folder in _portable_dirs():
        candidate = folder / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        if candidate.is_file():
            return str(candidate)
    return None


def probe_file(
    ffprobe_path: str | None,
    path: str | Path,
    cancel_event: threading.Event | None = None,
    timeout: float = 120.0,
) -> MediaMetadata:
    """Extract duration / video bitrate / audio bitrate from one media file.

    ``cancel_event`` is polled every 200 ms; when it is set the ffprobe process
    is killed and :class:`ProbeCancelled` is raised, so cancelling a scan does
    not wait for a slow network file to hit the timeout.
    """
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
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            startupinfo=startupinfo,
        )
    except OSError as exc:
        raise ProbeError(f"ffprobe launch failed: {exc}") from exc

    deadline = time.monotonic() + timeout
    while True:
        # Do not use communicate(timeout=...) for polling on Windows: it starts
        # reader threads that hold the pipe objects, and closing them after a
        # cancel would wait for every child process to exit anyway.
        if proc.poll() is not None:
            stdout, stderr = proc.communicate()
            break
        if cancel_event is not None and cancel_event.is_set():
            _kill(proc)
            raise ProbeCancelled("scan cancelled") from None
        if time.monotonic() >= deadline:
            _kill(proc)
            raise ProbeError("ffprobe timed out") from None
        time.sleep(0.05)

    if proc.returncode != 0:
        detail = stderr.decode("utf-8", errors="replace").strip()
        raise ProbeError(detail[:200] or f"exit code {proc.returncode}")

    return parse_probe_json(stdout.decode("utf-8", errors="replace"))


def _kill(proc: subprocess.Popen) -> None:
    """Kill ffprobe and stop waiting on its pipes immediately.

    Closing our read ends matters on Windows: killing a launcher (or a shell
    wrapper in tests) can leave a child holding the pipe open, and
    communicate() would then wait for that child to exit anyway.
    """
    try:
        proc.kill()
    except OSError:
        pass
    for stream in (proc.stdout, proc.stderr):
        if stream is not None:
            try:
                stream.close()
            except OSError:
                pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


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
    has_video = False
    for stream in data.get("streams", []):
        codec_type = stream.get("codec_type")
        rate = _to_int(stream.get("bit_rate"), 0)
        if codec_type == "video":
            has_video = True
            if rate > 0 and video_bitrate == 0:
                video_bitrate = rate
        elif codec_type == "audio" and rate > 0 and audio_bitrate == 0:
            audio_bitrate = rate

    # Some containers only carry a container-level bitrate; treat it as the
    # video rate minus any audio, best-effort.
    if has_video and video_bitrate == 0 and format_bitrate > 0:
        video_bitrate = max(0, format_bitrate - audio_bitrate) if audio_bitrate else format_bitrate

    return MediaMetadata(
        duration=duration,
        video_bitrate=video_bitrate,
        audio_bitrate=audio_bitrate,
        has_video=has_video,
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