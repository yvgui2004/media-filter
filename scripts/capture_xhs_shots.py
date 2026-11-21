"""Capture high-resolution screenshots used by the Xiaohongshu post.

Usage:
    .venv/Scripts/python.exe scripts/capture_xhs_shots.py <demo-folder>

Writes filtered.png, batch-hi.png and settings-hi.png next to the README
screenshots. The app runs with an isolated config/cache, scans with the real
ffprobe and tags with the bundled YOLOv8n model.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

os.environ["LOCALAPPDATA"] = tempfile.mkdtemp(prefix="mediafilter-xhs-")

from PySide6.QtCore import QEventLoop, QPoint
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QPushButton

from mediafilter.app import LOCALE_DIR
from mediafilter.config import Config
from mediafilter.i18n import Translator
from mediafilter.ui.dialog_base import set_dialog_tokens
from mediafilter.ui.main_window import MainWindow
from mediafilter.ui.theme import apply_theme
from mediafilter.ui.widgets.batch_process import BatchProcessDialog
from mediafilter.ui.widgets.settings_dialog import SettingsDialog

OUT = ROOT / "docs" / "screenshots"


def wait_until(app: QApplication, predicate, timeout: float = 300.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents(QEventLoop.AllEvents, 50)
        if predicate():
            return
        time.sleep(0.02)
    raise TimeoutError("condition not reached")


def process_events(app: QApplication, seconds: float = 0.5) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents(QEventLoop.AllEvents, 50)
        time.sleep(0.02)


def save(widget, name: str) -> None:
    path = OUT / name
    widget.grab().save(str(path), "PNG")
    print(f"  {path}  {widget.width()}x{widget.height()}")


def dump_geometry(root, widgets: dict, name: str) -> None:
    """Widget rects in grabbed-image pixels, used to place callout arrows."""
    data = {}
    for key, widget in widgets.items():
        point = widget.mapTo(root, QPoint(0, 0))
        data[key] = [point.x(), point.y(), widget.width(), widget.height()]
    path = OUT / name
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"  {path}")


def main() -> None:
    folder = Path(sys.argv[1])
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
    config.last_folder = str(folder)
    config.save()

    window = MainWindow(tr, config)
    window.resize(1440, 900)
    window.show()
    process_events(app, 0.6)

    window.start_scan(str(folder))
    wait_until(app, lambda: window._worker is None)
    window.start_tagging()
    wait_until(app, lambda: window._tag_worker is None)
    process_events(app, 0.5)

    window._tag_combo.setCurrentText("人")
    process_events(app, 0.6)
    visible = window._visible_source_rows()
    window._model.set_checked(visible, True)
    window._refresh_stats()
    process_events(app, 0.3)
    save(window, "filtered.png")
    dump_geometry(
        window,
        {
            "tag_filter": window._tag_combo,
            "select_all": window._select_all_btn,
            "status": window._status_label,
        },
        "xhs-geometry-main.json",
    )

    records = window._model.checked_records()[:3]
    batch = BatchProcessDialog(
        records, tr_call, window._load_presets(), window,
        tokens=window._palette, config=window._config,
    )
    batch.show()
    process_events(app, 1.0)
    save(batch, "batch-hi.png")

    footer_buttons = {
        button.text(): button for button in batch.findChildren(QPushButton)
        if button.isVisible()
    }
    dump_geometry(
        batch,
        {
            "copy": footer_buttons[tr_call("batch.copy")],
            "run": footer_buttons[tr_call("batch.start")],
            "preview": batch._preview_body,
        },
        "xhs-geometry-batch.json",
    )
    batch.close()

    settings = SettingsDialog(config, tr_call, window, tokens=window._palette)
    settings.resize(1360, 700)
    settings.show()
    settings._show_tab("tags")
    process_events(app, 0.8)
    save(settings, "settings-hi.png")
    settings.close()

    window.close()
    app.processEvents()


if __name__ == "__main__":
    main()