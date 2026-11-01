"""TXT report export. Pure text building; receives a translator so it can emit
localized headers without importing Qt."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Protocol

from .core.formats import format_bitrate, format_duration, format_size
from .core.models import FileRecord


class Translate(Protocol):
    def __call__(self, key: str, **kwargs) -> str: ...


def export_txt(records: list[FileRecord], dst: str | Path, tr: Translate) -> int:
    """Write a report for *records* to *dst*; returns the number of files written."""
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append(f"  Media Filter — {datetime.now():%Y-%m-%d %H:%M:%S}")
    lines.append("=" * 72)
    lines.append("")

    total_size = sum(r.size for r in records)
    total_duration = sum(r.duration for r in records)
    lines.append(
        f"  {tr('stat.files', n=len(records))} | "
        f"{tr('stat.duration', d=format_duration(total_duration))} | "
        f"{tr('stat.size', s=format_size(total_size))}"
    )
    lines.append("")

    header = (
        f"{tr('col.name'):<40} {tr('col.size'):>10} {tr('col.duration'):>10} "
        f"{tr('col.bitrate'):>12}  {tr('col.format'):>6}"
    )
    lines.append(header)
    lines.append("-" * len(header))

    for rec in records:
        size = format_size(rec.size)
        duration = format_duration(rec.duration)
        bitrate = format_bitrate(rec.bitrate) or tr("unknown")
        name = rec.name if len(rec.name) <= 40 else rec.name[:37] + "..."
        lines.append(f"{name:<40} {size:>10} {duration:>10} {bitrate:>12}  {rec.extension:>6}")

    lines.append("")
    lines.append("-" * 72)
    text = "\n".join(lines) + "\n"

    dst_path = Path(dst)
    dst_path.write_text(text, encoding="utf-8")
    return len(records)