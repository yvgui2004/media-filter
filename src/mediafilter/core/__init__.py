"""Pure logic layer. No Qt imports allowed in this package.
Everything here is unit-testable without a display."""

from .models import FileRecord, MediaMetadata
from .scanner import scan_files, DEFAULT_EXTENSIONS, VIDEO_EXTENSIONS, AUDIO_EXTENSIONS
from .probe import find_ffprobe, probe_file, ProbeError
from .pool import scan_and_probe
from .ffmpeg import Preset, default_presets, build_command, build_output_path
from .formats import format_duration, format_size, format_bitrate, parse_size_to_bytes

__all__ = [
    "FileRecord",
    "MediaMetadata",
    "scan_files",
    "DEFAULT_EXTENSIONS",
    "VIDEO_EXTENSIONS",
    "AUDIO_EXTENSIONS",
    "find_ffprobe",
    "probe_file",
    "ProbeError",
    "scan_and_probe",
    "Preset",
    "default_presets",
    "build_command",
    "build_output_path",
    "format_duration",
    "format_size",
    "format_bitrate",
    "parse_size_to_bytes",
]