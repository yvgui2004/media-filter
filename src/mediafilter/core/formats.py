"""Human-readable formatting helpers. Locale-independent; UI localizes labels."""

from __future__ import annotations

import re
from datetime import datetime

_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")


def format_duration(seconds: float) -> str:
    """Format seconds as h:mm:ss (or m:ss when under an hour)."""
    total = int(round(seconds))
    if total <= 0:
        return "0:00"
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_size(num_bytes: int) -> str:
    """Format a byte count as a human-readable size."""
    value = float(num_bytes)
    for unit in _UNITS:
        if value < 1024.0 or unit == _UNITS[-1]:
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.2f} {unit}"
        value /= 1024.0
    return f"{num_bytes} B"


def format_bitrate(bps: int) -> str:
    """Format a bitrate; returns the empty string for unknown/zero rates."""
    if bps <= 0:
        return ""
    if bps >= 1_000_000:
        return f"{bps / 1_000_000:.2f} Mbps"
    if bps >= 1_000:
        return f"{bps / 1_000:.0f} kbps"
    return f"{bps} bps"


def format_mtime(timestamp: float) -> str:
    """Format a POSIX timestamp as 'YYYY-MM-DD HH:MM'; empty when unknown."""
    if timestamp <= 0:
        return ""
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")


def parse_size_to_bytes(text: str) -> int | None:
    """Parse strings like '1.5GB', '240 MB', '500kb' into bytes. None on failure."""
    if not text:
        return None
    m = re.match(r"^\s*([\d.]+)\s*([kmgtp]?b)\s*$", text.strip(), re.IGNORECASE)
    if not m:
        return None
    value = float(m.group(1))
    unit = m.group(2)[0].lower()
    exponent = {"b": 0, "k": 1, "m": 2, "g": 3, "t": 4, "p": 5}[unit]
    return int(value * (1024 ** exponent))