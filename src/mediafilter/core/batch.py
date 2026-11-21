"""Batch processing model.

This module is deliberately UI-free: it owns the encoder catalogue, the ffmpeg
argument construction, output planning (suffix / folder / conflict policy /
temporary files) and the "can this GPU actually encode?" probe.  The dialog
only renders these decisions, and the tests exercise them without Qt.

One rule runs through everything here: a batch never writes in place.  Outputs
are rendered to a unique ``.part`` file next to the target and published with
:func:`os.replace` once ffmpeg exits cleanly, so a cancelled or failed job
cannot leave a half-written video behind.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from . import gpu
from .probe import find_ffmpeg

# --------------------------------------------------------------------------
# tasks & containers
# --------------------------------------------------------------------------

TASKS: tuple[str, ...] = ("remux", "compress", "custom")

ORIGINAL = "original"           # keep the source container
ALL_CONTAINERS: tuple[str, ...] = (
    "mp4", "mkv", "mov", "webm", "avi", "flv", "ts", "m4v",
)
REMUX_CONTAINERS: tuple[str, ...] = ALL_CONTAINERS

DEFAULT_SUFFIX: dict[str, str] = {
    "remux": "_converted",
    "compress": "_compressed",
    "custom": "_out",
}
DEFAULT_CONTAINER: dict[str, str] = {
    "remux": "mp4",
    "compress": "mp4",
    "custom": ORIGINAL,
}

# --------------------------------------------------------------------------
# encoders
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class EncoderSpec:
    """One ffmpeg video encoder and the quality knobs it understands.

    ``tiers`` is ordered high / balanced / small.  ``video_args`` is a
    whitespace-separated template with ``{q}`` (quality number) and ``{p}``
    (encoder preset) placeholders; the AMF encoders do not use ``{p}`` in the
    argument list and that is fine — unused placeholders are simply ignored by
    :meth:`args`.
    """

    key: str
    label: str                  # English fallback label
    short: str                  # chip label, e.g. "NVENC HEVC"
    codec: str                  # h264 | hevc | av1
    family: str                 # nvenc | amf | cpu
    ffmpeg: str                 # encoder name handed to -c:v
    qkind: str                  # CQ | QP | CRF
    tiers: tuple[int, int, int]
    containers: tuple[str, ...]
    preset: str = ""
    presets: tuple[str, ...] = ()
    video_args: str = ""

    @property
    def hardware(self) -> bool:
        return self.family in ("nvenc", "amf")

    def args(self, quality: int, preset: str | None = None) -> list[str]:
        template = self.video_args.format(q=int(quality), p=preset or self.preset)
        return template.split()


ENCODERS: dict[str, EncoderSpec] = {
    "nvenc_hevc": EncoderSpec(
        key="nvenc_hevc",
        label="NVIDIA NVENC · H.265",
        short="NVENC HEVC",
        codec="hevc",
        family="nvenc",
        ffmpeg="hevc_nvenc",
        qkind="CQ",
        tiers=(20, 23, 26),
        containers=("mp4", "mkv", "mov", "ts"),
        preset="p7",
        presets=("p7", "p6", "p5"),
        video_args="-preset {p} -tune hq -rc vbr -cq {q} -b:v 0",
    ),
    "nvenc_h264": EncoderSpec(
        key="nvenc_h264",
        label="NVIDIA NVENC · H.264",
        short="NVENC H.264",
        codec="h264",
        family="nvenc",
        ffmpeg="h264_nvenc",
        qkind="CQ",
        tiers=(19, 23, 26),
        containers=("mp4", "mkv", "mov", "avi", "flv", "ts"),
        preset="p7",
        presets=("p7", "p6", "p5"),
        video_args="-preset {p} -tune hq -rc vbr -cq {q} -b:v 0 -pix_fmt yuv420p",
    ),
    "nvenc_av1": EncoderSpec(
        key="nvenc_av1",
        label="NVIDIA NVENC · AV1",
        short="NVENC AV1",
        codec="av1",
        family="nvenc",
        ffmpeg="av1_nvenc",
        qkind="QP",
        tiers=(26, 30, 34),
        containers=("mp4", "mkv", "webm"),
        preset="p7",
        presets=("p7", "p6", "p5"),
        video_args="-preset {p} -tune hq -rc constqp -qp {q}",
    ),
    "amf_hevc": EncoderSpec(
        key="amf_hevc",
        label="AMD AMF · H.265",
        short="AMF HEVC",
        codec="hevc",
        family="amf",
        ffmpeg="hevc_amf",
        qkind="QP",
        tiers=(22, 26, 30),
        containers=("mp4", "mkv", "mov", "ts"),
        preset="quality",
        presets=("quality", "balanced", "speed"),
        video_args="-quality {p} -rc cqp -qp_i {q} -qp_p {q}",
    ),
    "amf_h264": EncoderSpec(
        key="amf_h264",
        label="AMD AMF · H.264",
        short="AMF H.264",
        codec="h264",
        family="amf",
        ffmpeg="h264_amf",
        qkind="QP",
        tiers=(20, 24, 28),
        containers=("mp4", "mkv", "mov", "avi", "flv", "ts"),
        preset="quality",
        presets=("quality", "balanced", "speed"),
        video_args="-quality {p} -rc cqp -qp_i {q} -qp_p {q} -pix_fmt yuv420p",
    ),
    "amf_av1": EncoderSpec(
        key="amf_av1",
        label="AMD AMF · AV1",
        short="AMF AV1",
        codec="av1",
        family="amf",
        ffmpeg="av1_amf",
        qkind="QP",
        tiers=(26, 30, 34),
        containers=("mp4", "mkv", "webm"),
        preset="quality",
        presets=("quality", "balanced", "speed"),
        video_args="-quality {p} -rc cqp -qp_i {q} -qp_p {q}",
    ),
    "x265": EncoderSpec(
        key="x265",
        label="CPU · H.265 (x265)",
        short="x265",
        codec="hevc",
        family="cpu",
        ffmpeg="libx265",
        qkind="CRF",
        tiers=(20, 23, 26),
        containers=("mp4", "mkv", "mov", "ts"),
        preset="medium",
        presets=("medium", "slow", "faster"),
        video_args="-crf {q} -preset {p}",
    ),
    "x264": EncoderSpec(
        key="x264",
        label="CPU · H.264 (x264)",
        short="x264",
        codec="h264",
        family="cpu",
        ffmpeg="libx264",
        qkind="CRF",
        tiers=(18, 21, 24),
        containers=("mp4", "mkv", "mov", "avi", "flv", "ts"),
        preset="medium",
        presets=("medium", "slow", "faster"),
        video_args="-crf {q} -preset {p} -pix_fmt yuv420p",
    ),
}

ENCODER_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("nvenc", ("nvenc_hevc", "nvenc_h264", "nvenc_av1")),
    ("amf", ("amf_hevc", "amf_h264", "amf_av1")),
    ("cpu", ("x265", "x264")),
)

#: Preference order for "auto": hardware HEVC first (best quality per bit on
#: every vendor), then hardware H.264 (broad compatibility), then AV1 (newer
#: cards only), then the CPU encoders.
AUTO_ORDER: tuple[str, ...] = (
    "nvenc_hevc", "amf_hevc",
    "nvenc_h264", "amf_h264",
    "nvenc_av1", "amf_av1",
    "x265", "x264",
)
CPU_FALLBACK = "x265"
CPU_FALLBACK_SAFE = "x264"

QUALITY_TIERS: tuple[str, ...] = ("high", "balanced", "small")
SUBTITLE_MODES: tuple[str, ...] = ("smart", "remove")
AUDIO_MODES: tuple[str, ...] = ("smart", "copy", "aac", "remove")
CONFLICT_MODES: tuple[str, ...] = ("number", "skip", "overwrite")
FAILURE_MODES: tuple[str, ...] = ("continue", "stop")


def encoder(key: str) -> EncoderSpec:
    try:
        return ENCODERS[key]
    except KeyError as exc:
        raise ValueError(f"unknown encoder: {key}") from exc


def auto_encoder(available: dict[str, bool] | None = None) -> str:
    """Best available encoder.  Unknown availability is treated as available."""
    if available:
        for key in AUTO_ORDER:
            if available.get(key):
                return key
    for key in AUTO_ORDER:
        if ENCODERS[key].hardware:
            continue
        return key
    return CPU_FALLBACK


def resolve_encoder(key: str, available: dict[str, bool] | None = None) -> str:
    """Turn ``auto`` (or an unavailable pick) into a concrete encoder."""
    if key == "auto":
        return auto_encoder(available)
    if key not in ENCODERS:
        raise ValueError(f"unknown encoder: {key}")
    if available and not available.get(key):
        return auto_encoder(available)
    return key


def quality_value(
    key: str, tier: str = "balanced", custom: str | int | None = None
) -> int:
    """Resolve a quality tier (or a typed override) to the encoder's number."""
    spec = encoder(key)
    if custom is not None and str(custom).strip() != "":
        return int(str(custom).strip())
    index = QUALITY_TIERS.index(tier) if tier in QUALITY_TIERS else 1
    return spec.tiers[index]


def quality_text(key: str, tier: str = "balanced", custom: str | int | None = None) -> str:
    spec = encoder(key)
    return f"{spec.qkind} {quality_value(key, tier, custom)}"


def containers_for(task: str, encoder_key: str = "auto") -> tuple[str, ...]:
    if task == "remux":
        return REMUX_CONTAINERS
    if task == "custom":
        return (ORIGINAL,) + ALL_CONTAINERS
    key = resolve_encoder(encoder_key)
    return ENCODERS[key].containers


def default_container(task: str, encoder_key: str = "auto") -> str:
    if task in ("remux", "custom"):
        return DEFAULT_CONTAINER[task]
    allowed = containers_for(task, encoder_key)
    return "mp4" if "mp4" in allowed else allowed[0]


# --------------------------------------------------------------------------
# stream policies
# --------------------------------------------------------------------------


def audio_args(mode: str = "smart", extension: str = "mp4") -> list[str]:
    ext = extension.lower().lstrip(".")
    if mode == "remove":
        return ["-an"]
    if mode == "aac":
        if ext == "webm":
            return ["-c:a", "libopus", "-b:a", "128k"]
        return ["-c:a", "aac", "-b:a", "128k"]
    return ["-c:a", "copy"]


def subtitle_args(mode: str = "smart", extension: str = "mp4") -> list[str]:
    ext = extension.lower().lstrip(".")
    if mode == "remove":
        return ["-sn"]
    if ext in ("mp4", "mov", "m4v"):
        return ["-c:s", "mov_text"]
    if ext == "mkv":
        return ["-c:s", "copy"]
    if ext == "webm":
        return ["-c:s", "webvtt"]
    if ext in ("avi", "flv"):
        return ["-sn"]
    return ["-c:s", "copy"]


def subtitle_effect(mode: str, extension: str) -> str:
    """Short description of what will happen to subtitle streams."""
    ext = extension.lower().lstrip(".")
    if mode == "remove":
        return "remove"
    if ext in ("mp4", "mov", "m4v"):
        return "mov_text"
    if ext == "mkv":
        return "copy"
    if ext == "webm":
        return "webvtt"
    if ext in ("avi", "flv"):
        return "dropped"
    return "copy"


def faststart_args(extension: str) -> list[str]:
    return ["-movflags", "+faststart"] if extension.lower().lstrip(".") in (
        "mp4", "mov", "m4v",
    ) else []


def attachment_args(extension: str) -> list[str]:
    # MKV can carry fonts; copying them keeps ASS subtitle styling intact.
    return ["-map", "0:t?", "-c:t", "copy"] if extension.lower().lstrip(".") == "mkv" else []


def stream_map_args() -> list[str]:
    return ["-map", "0:V:0", "-map", "0:a?", "-map", "0:s?"]


# --------------------------------------------------------------------------
# command construction
# --------------------------------------------------------------------------

Command = list[str] | str


def fill_template(template: str, source: str | Path, target: str | Path) -> str:
    return template.replace("{input}", str(source)).replace("{output}", str(target))


def resolved_extension(container: str, source: str | Path) -> str:
    if container == ORIGINAL:
        return Path(source).suffix.lower().lstrip(".")
    return container.lower().lstrip(".")


def build_command(
    ffmpeg_bin: str,
    source: str | Path,
    target: str | Path,
    *,
    task: str = "compress",
    encoder_key: str = "x265",
    container: str = "mp4",
    quality_tier: str = "balanced",
    quality: str | int | None = None,
    preset: str = "",
    audio: str = "smart",
    subtitles: str = "smart",
    metadata: bool = True,
    template: str = "",
    runtime: bool = False,
) -> Command:
    """Build one per-file command.

    Built-in tasks return an argv list; the custom task returns the raw command
    string the user typed (with ``{input}`` / ``{output}`` substituted), because
    we must not re-tokenise a shell command the user chose.  ``runtime=True``
    appends machine-readable progress flags that the preview hides.
    """
    if task == "custom":
        text = template.strip()
        if not text:
            raise ValueError("custom command template is empty")
        return fill_template(text, source, target)

    ext = resolved_extension(container, source)
    args: list[str] = [ffmpeg_bin, "-hide_banner", "-hwaccel", "auto", "-i", str(source)]
    args += stream_map_args()

    if task == "remux":
        args += ["-c:v", "copy"]
    elif task == "compress":
        spec = encoder(encoder_key)
        value = quality_value(spec.key, quality_tier, quality)
        args += ["-c:v", spec.ffmpeg]
        args += spec.args(value, preset or spec.preset)
        if spec.codec == "hevc" and ext in ("mp4", "mov", "m4v"):
            args += ["-tag:v", "hvc1"]
    else:
        raise ValueError(f"unknown task: {task}")

    args += audio_args(audio, ext)
    args += subtitle_args(subtitles, ext)
    args += attachment_args(ext)
    if metadata:
        args += ["-map_metadata", "0", "-map_chapters", "0"]
    args += faststart_args(ext)

    if runtime:
        args[1:1] = ["-nostdin", "-loglevel", "error", "-progress", "pipe:1", "-nostats"]
    args.append(str(target))
    return args


def display_command(command: Command) -> str:
    """A copy-pasteable Windows command line for the preview pane."""
    if isinstance(command, str):
        return command
    return subprocess.list2cmdline(command)


def batch_file_text(commands: Sequence[Command], *, pause: bool = True) -> str:
    """Body of a double-clickable .bat file (CRLF line endings).

    Paths are quoted by :func:`display_command`; ``%`` is the only character
    cmd.exe still expands inside quotes, so it is doubled here.
    """
    lines = [display_command(c).replace("%", "%%") for c in commands]
    body = "@echo off\r\n" + "\r\n".join(lines) + "\r\n"
    return body + ("pause\r\n" if pause else "")


def subprocess_kwargs() -> dict:
    """Keep ffmpeg from flashing a console window on Windows."""
    kwargs: dict = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    return kwargs


# --------------------------------------------------------------------------
# progress parsing
# --------------------------------------------------------------------------

_TIME_RE = re.compile(r"^out_time=(-?)(\d+):(\d{2}):(\d{2}(?:\.\d+)?)")
_SPEED_RE = re.compile(r"^speed=\s*([\d.]+|-?nan|N/A)\s*x?", re.IGNORECASE)


@dataclass(frozen=True)
class ProgressSample:
    out_time: float | None = None
    speed: float | None = None
    finished: bool = False
    cycle: bool = False


def parse_progress_line(line: str) -> ProgressSample | None:
    """Parse one key=value line of ``ffmpeg -progress pipe:1`` output."""
    text = line.strip()
    if not text:
        return None
    if text == "progress=end":
        return ProgressSample(finished=True)
    if text == "progress=continue":
        return ProgressSample(cycle=True)
    match = _TIME_RE.match(text)
    if match:
        sign, hours, minutes, seconds = match.groups()
        value = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        return ProgressSample(out_time=-value if sign else value)
    match = _SPEED_RE.match(text)
    if match and match.group(1) not in ("N/A", "-nan", "nan"):
        try:
            return ProgressSample(speed=float(match.group(1)))
        except ValueError:
            return None
    return None


def percent_done(out_time: float | None, duration: float) -> float | None:
    """0..100, or None when either side is unknown."""
    if not out_time or duration <= 0:
        return None
    return max(0.0, min(100.0, out_time / duration * 100.0))


# --------------------------------------------------------------------------
# output planning
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class OutputTarget:
    source: Path
    target: Path
    skipped: bool = False
    reason: str = ""            # exists | same | input

    @property
    def ok(self) -> bool:
        return not self.skipped


def _key(path: str | Path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def plan_outputs(
    sources: Iterable[str | Path],
    *,
    folder: str | Path | None = None,
    suffix: str = "_out",
    extension: str | None = None,
    conflict: str = "number",
) -> list[OutputTarget]:
    """Decide every output path up front, honouring the conflict policy.

    ``sources`` are also reserved, so even ``overwrite`` can never clobber an
    input file.  With ``number`` the first clash becomes ``name (2).ext``;
    ``skip`` marks the row instead of running it.
    """
    if conflict not in CONFLICT_MODES:
        conflict = "number"
    paths = [Path(item) for item in sources]
    inputs = {_key(item) for item in paths}
    reserved = set(inputs)
    base_folder = Path(folder) if folder else None
    plans: list[OutputTarget] = []

    for source in paths:
        ext = (extension or source.suffix.lstrip(".")).lower().lstrip(".")
        target_folder = base_folder or source.parent
        stem = f"{source.stem}{suffix}"
        candidate = target_folder / f"{stem}.{ext}"
        same_as_input = _key(candidate) == _key(source)

        if same_as_input:
            plans.append(OutputTarget(source, candidate, True, "same"))
            continue

        if conflict == "overwrite":
            if _key(candidate) in inputs:
                plans.append(OutputTarget(source, candidate, True, "input"))
            else:
                plans.append(OutputTarget(source, candidate))
                reserved.add(_key(candidate))
            continue

        if conflict == "skip":
            if candidate.exists() or _key(candidate) in reserved:
                plans.append(OutputTarget(source, candidate, True, "exists"))
            else:
                plans.append(OutputTarget(source, candidate))
                reserved.add(_key(candidate))
            continue

        chosen = candidate
        counter = 1
        while chosen.exists() or _key(chosen) in reserved:
            counter += 1
            chosen = target_folder / f"{stem} ({counter}).{ext}"
        plans.append(OutputTarget(source, chosen))
        reserved.add(_key(chosen))

    return plans


def temp_output_path(target: str | Path) -> Path:
    """Hidden sibling file ffmpeg writes before the atomic rename.

    The real extension stays last so ffmpeg picks the right muxer.
    """
    path = Path(target)
    stamp = f"{os.getpid()}-{time.time_ns()}"
    return path.with_name(f".{path.stem}.{stamp}.part{path.suffix}")


def publish_temp(temp: str | Path, target: str | Path) -> None:
    """Atomically move a finished temp file over its final name."""
    os.replace(str(temp), str(target))


def discard_temp(temp: str | Path) -> None:
    try:
        Path(temp).unlink()
    except OSError:
        pass


# --------------------------------------------------------------------------
# hardware availability
# --------------------------------------------------------------------------

#: Reasons a hardware encoder is unavailable; the UI localises these.
REASON_FFMPEG = "ffmpeg_missing"
REASON_BUILD = "not_in_ffmpeg"
REASON_NO_GPU = "no_gpu"
REASON_DRIVER = "driver"
REASON_FAILED = "failed"

_VENDOR_BY_FAMILY = {"nvenc": 0x10DE, "amf": 0x1002}


@dataclass(frozen=True)
class Availability:
    key: str
    available: bool
    reason: str = ""

    @property
    def disabled_note(self) -> str:
        return "" if self.available else self.reason


_PROBE_TTL = 600.0
_probe_cache: dict[str, tuple[float, dict[str, Availability]]] = {}

_SMOKE_SOURCE = "color=c=black:s=256x144:r=30:d=1"


def clear_probe_cache() -> None:
    _probe_cache.clear()


def _detected_vendors() -> set[int]:
    try:
        report = gpu.inspect()
    except Exception:
        return set()
    return {adapter.vendor_id for adapter in report.adapters if not adapter.software}


def detected_vendors() -> set[int]:
    """PCI vendor ids of the real display adapters (for UI hints)."""
    return _detected_vendors()


def _run_probe(binary: str, args: Sequence[str], timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(
        [binary, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        **subprocess_kwargs(),
    )


def _available_encoders(binary: str, timeout: float) -> set[str] | None:
    try:
        result = _run_probe(binary, ["-hide_banner", "-encoders"], timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    text = (result.stdout or b"").decode("utf-8", errors="replace")
    names: set[str] = set()
    for line in text.splitlines():
        match = re.match(r"^\s*[VAS][A-Z.]{5}\s+(\S+)", line)
        if match:
            names.add(match.group(1))
    return names


def _smoke_args(spec: EncoderSpec) -> list[str]:
    preset = spec.presets[-1] if spec.presets else ""
    return [
        "-hide_banner", "-nostdin", "-loglevel", "error",
        "-f", "lavfi", "-i", _SMOKE_SOURCE,
        "-frames:v", "1", "-an", "-sn",
        "-c:v", spec.ffmpeg, *spec.args(spec.tiers[-1], preset),
        "-f", "null", "-",
    ]


def _classify_failure(stderr: str) -> str:
    text = stderr.lower()
    driver_hints = (
        "cannot load", "failed to open", "no capable devices",
        "device creation failed", "not supported", "no nvenc capable",
        "amf", "initializ", "d3d11",
    )
    return REASON_DRIVER if any(hint in text for hint in driver_hints) else REASON_FAILED


def probe_encoders(
    ffmpeg_bin: str | None = None,
    *,
    refresh: bool = False,
    timeout: float = 12.0,
) -> dict[str, Availability]:
    """Check which encoders this machine can really use.

    FFmpeg may list an encoder that the installed driver cannot run (an old
    AMD card without AV1 support is the common case), so every hardware entry
    is proven with a one-frame lavfi encode.  Results are cached for ten
    minutes; opening the dialog again costs nothing.
    """
    binary = ffmpeg_bin or find_ffmpeg()
    if not binary:
        return {key: Availability(key, False, REASON_FFMPEG) for key in ENCODERS}

    cache_key = os.path.normcase(os.path.abspath(binary))
    now = time.monotonic()
    cached = _probe_cache.get(cache_key)
    if cached and not refresh and now - cached[0] < _PROBE_TTL:
        return dict(cached[1])

    listed = _available_encoders(binary, timeout)
    vendors = _detected_vendors()
    results: dict[str, Availability] = {}

    for key, spec in ENCODERS.items():
        if listed is None:
            results[key] = Availability(key, False, REASON_FFMPEG)
            continue
        if spec.ffmpeg not in listed:
            results[key] = Availability(key, False, REASON_BUILD)
            continue
        if spec.hardware and _VENDOR_BY_FAMILY.get(spec.family) not in vendors:
            results[key] = Availability(key, False, REASON_NO_GPU)
            continue
        try:
            result = _run_probe(binary, _smoke_args(spec), timeout)
        except subprocess.TimeoutExpired:
            results[key] = Availability(key, False, REASON_DRIVER)
            continue
        except (OSError, subprocess.SubprocessError):
            results[key] = Availability(key, False, REASON_FAILED)
            continue
        if result.returncode == 0:
            results[key] = Availability(key, True)
        else:
            stderr = (result.stderr or b"").decode("utf-8", errors="replace")
            results[key] = Availability(key, False, _classify_failure(stderr))

    _probe_cache[cache_key] = (now, results)
    return dict(results)


def available_map(report: dict[str, Availability]) -> dict[str, bool]:
    return {key: item.available for key, item in report.items()}