"""Regenerate the Windows app icon from the same mark as the titlebar.

Run from the repo root:
    .venv/Scripts/python.exe tools/build_icon.py
"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QBuffer, QByteArray, QIODevice  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from mediafilter.ui.icons import brand_image  # noqa: E402

ASSETS = ROOT / "src" / "mediafilter" / "assets"
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def png_bytes(size: int) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    brand_image(size).save(buffer, "PNG")  # pyright: ignore[reportCallIssue, reportArgumentType]
    buffer.close()
    return bytes(data.data())


def write_ico(path: Path, sizes: tuple[int, ...]) -> None:
    blobs = [png_bytes(size) for size in sizes]
    header = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries = []
    for size, blob in zip(sizes, blobs):
        dimension = 0 if size >= 256 else size
        entries.append(
            struct.pack(
                "<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(blob), offset
            )
        )
        offset += len(blob)
    path.write_bytes(header + b"".join(entries) + b"".join(blobs))


def main() -> None:
    QGuiApplication([])
    ASSETS.mkdir(parents=True, exist_ok=True)
    png = ASSETS / "app_icon.png"
    brand_image(256).save(str(png))
    ico = ASSETS / "app_icon.ico"
    write_ico(ico, SIZES)
    print(f"wrote {png} ({png.stat().st_size} bytes)")
    print(f"wrote {ico} ({ico.stat().st_size} bytes, {len(SIZES)} sizes)")


if __name__ == "__main__":
    main()