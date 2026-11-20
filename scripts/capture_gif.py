"""Capture the README demo GIF from the real widgets.

Usage:
    .venv/Scripts/python.exe scripts/capture_gif.py <demo-folder> <out.gif>

Grabs a short, honest sequence: empty state -> scanning -> scanned -> AI
tagging -> tagged -> filtered by tag -> batch command dialog. The frames are
captured with QWidget.grab() from the real MainWindow (isolated config/cache),
then assembled into an optimised GIF with Pillow.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

os.environ["LOCALAPPDATA"] = tempfile.mkdtemp(prefix="mediafilter-gif-")

from PIL import Image
from PySide6.QtCore import QEventLoop
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from mediafilter.app import LOCALE_DIR
from mediafilter.config import Config
from mediafilter.i18n import Translator
from mediafilter.ui.dialog_base import set_dialog_tokens
from mediafilter.ui.main_window import MainWindow
from mediafilter.ui.theme import apply_theme
from mediafilter.ui.widgets.batch_dialog import BatchCommandDialog

FRAMES_DIR = Path(tempfile.mkdtemp(prefix="mediafilter-gif-frames-"))
DURATIONS_MS = [1800, 1600, 1900, 1900, 2600]
CANVAS = (1000, 625)


def wait_until(app: QApplication, predicate, timeout: float = 180.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents(QEventLoop.AllEvents, 50)
        if predicate():
            return
        time.sleep(0.02)
    raise TimeoutError("condition not reached in time")


def process_events(app: QApplication, seconds: float = 0.4) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents(QEventLoop.AllEvents, 50)
        time.sleep(0.02)


def grab(widget, index: int) -> Path:
    path = FRAMES_DIR / f"frame-{index:02d}.png"
    widget.grab().save(str(path), "PNG")
    print(f"  frame {index}: {path.name}")
    return path


def main() -> None:
    folder = Path(sys.argv[1])
    out = Path(sys.argv[2])
    model = ROOT / "models" / "yolov8n_fp32.onnx"

    app = QApplication([])
    app.setApplicationName("Media Filter")
    font = QFont()
    font.setFamilies(["Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei UI"])
    font.setPixelSize(13)
    app.setFont(font)

    tr = Translator(LOCALE_DIR)
    tr.set_fallback("en")
    tr.set_language("zh")
    tr_call = tr.tr

    palette = apply_theme(app, "light")
    set_dialog_tokens(palette)

    config = Config.load(Path(os.environ["LOCALAPPDATA"]) / "config.json")
    config.language = "zh"
    config.theme_mode = "light"
    config.recognition_mode = "local"
    config.frame_policy = "auto"
    config.ai_model_path = str(model)
    config.first_run_done = True
    config.first_run_prompted = True
    config.guide_dismissed = True
    config.last_folder = ""
    config.save()

    window = MainWindow(tr, config)
    window.resize(1440, 900)
    window.show()
    process_events(app, 0.6)
    frames = [grab(window, 0)]

    window.start_scan(str(folder))
    wait_until(app, lambda: window._worker is None)
    process_events(app, 0.3)
    frames.append(grab(window, 1))

    window.start_tagging()
    wait_until(app, lambda: window._tag_worker is None, timeout=300)
    process_events(app, 0.4)
    frames.append(grab(window, 2))

    # Filter by the most common tag so the table visibly narrows.
    counts: dict[str, int] = {}
    for rec in window._model.records():
        for tag in rec.tags:
            counts[tag] = counts.get(tag, 0) + 1
    tag = max(counts, key=lambda name: counts[name]) if counts else ""
    if tag:
        window._tag_combo.setCurrentText(tag)
        process_events(app, 0.5)
    frames.append(grab(window, 3))

    if tag:
        window._tag_combo.setCurrentIndex(0)
        process_events(app, 0.3)
    video_rows = [
        i for i, rec in enumerate(window._model.records()) if rec.has_video
    ][:3]
    window._model.set_checked(video_rows, True)
    window._refresh_stats()
    process_events(app, 0.3)

    records = window._model.checked_records() or window._model.records()[:3]
    batch = BatchCommandDialog(
        records, tr_call, window._load_presets(), window, window._palette
    )
    batch.resize(1100, 760)
    batch.show()
    process_events(app, 0.8)
    frames.append(grab(batch, 4))
    batch.close()

    window.close()
    app.processEvents()

    # Fit every grab on one canvas so the dialog frame does not change size.
    images = []
    for path in frames:
        im = Image.open(path).convert("RGB")
        scale = min(CANVAS[0] / im.width, CANVAS[1] / im.height)
        im = im.resize((round(im.width * scale), round(im.height * scale)),
                       Image.LANCZOS)
        canvas = Image.new("RGB", CANVAS, "#FFFFFF")
        canvas.paste(im, ((CANVAS[0] - im.width) // 2, (CANVAS[1] - im.height) // 2))
        images.append(canvas)

    out.parent.mkdir(parents=True, exist_ok=True)
    first, *rest = images
    quantized = [first.quantize(colors=256, method=Image.Quantize.MEDIANCUT,
                                dither=Image.Dither.FLOYDSTEINBERG)]
    for im in rest:
        quantized.append(im.quantize(palette=quantized[0], dither=Image.Dither.FLOYDSTEINBERG))

    quantized[0].save(
        out,
        save_all=True,
        append_images=quantized[1:],
        duration=DURATIONS_MS[:len(quantized)],
        loop=0,
        optimize=True,
        disposal=2,
    )
    size_mb = out.stat().st_size / 1024 / 1024
    print(f"\n{out}  ({size_mb:.2f} MB, {len(quantized)} frames)")


if __name__ == "__main__":
    main()