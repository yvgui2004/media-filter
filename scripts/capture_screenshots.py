"""Capture README screenshots from the real widgets.

Usage:
    .venv/Scripts/python.exe scripts/capture_screenshots.py <demo-folder> <out-dir>

The app is started with an isolated config/cache directory, scans the demo
folder with the real ffprobe, runs the bundled local model, then grabs the
main window (light + dark), the batch dialog and the settings page.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# Keep the demo tags out of the real user cache before platformdirs is used.
os.environ["LOCALAPPDATA"] = tempfile.mkdtemp(prefix="mediafilter-shots-")

from PySide6.QtCore import QEventLoop
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import QApplication

from mediafilter.app import LOCALE_DIR
from mediafilter.config import Config
from mediafilter.i18n import Translator
from mediafilter.ui.dialog_base import set_dialog_tokens
from mediafilter.ui.main_window import MainWindow
from mediafilter.ui.theme import apply_theme
from mediafilter.ui.widgets.batch_dialog import BatchCommandDialog
from mediafilter.ui.widgets.settings_dialog import SettingsDialog


def wait_until(app: QApplication, predicate, timeout: float = 180.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents(QEventLoop.AllEvents, 50)
        if predicate():
            return
        time.sleep(0.02)
    raise TimeoutError("condition not reached in time")


def process_events(app: QApplication, seconds: float = 0.6) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents(QEventLoop.AllEvents, 50)
        time.sleep(0.02)


def save(widget, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    widget.grab().save(str(path), "PNG")
    print(f"  {path}")


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
    config.last_folder = str(folder)
    config.save()

    window = MainWindow(tr, config)
    window.resize(1440, 900)
    window.show()
    process_events(app)

    window.start_scan(str(folder))
    wait_until(app, lambda: window._worker is None and window._model.rowCount() > 0)
    print(f"scanned {window._model.rowCount()} files")

    window.start_tagging()
    wait_until(app, lambda: window._tag_worker is None, timeout=300)
    print("tagging finished")

    video_rows = [
        i for i, rec in enumerate(window._model.records()) if rec.has_video
    ][:3]
    window._model.set_checked(video_rows, True)
    window._refresh_stats()
    process_events(app)
    status = window._status_label.text()
    save(window, out / "main-light.png")

    config.theme_mode = "dark"
    window._palette = apply_theme(app, "dark")
    window._apply_palette()
    window.retranslate()
    window._set_status(status)
    process_events(app)
    save(window, out / "main-dark.png")

    config.theme_mode = "light"
    window._palette = apply_theme(app, "light")
    window._apply_palette()
    window.retranslate()
    window._set_status(status)
    process_events(app)

    records = window._model.checked_records() or window._model.records()[:3]
    batch = BatchCommandDialog(records, tr_call, window._load_presets(), window, window._palette)
    batch.resize(820, 720)
    batch.show()
    process_events(app)
    save(batch, out / "batch.png")
    batch.close()

    settings = SettingsDialog(config, tr_call, window, tokens=window._palette)
    settings.show()
    settings._show_tab("tags")
    process_events(app, 1.0)
    save(settings, out / "settings.png")
    settings.close()

    window.close()
    app.processEvents()


if __name__ == "__main__":
    main()