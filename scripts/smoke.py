"""Smoke test: build the full UI offscreen and verify nothing raises on startup.
Run with: .venv/Scripts/python.exe scripts/smoke.py
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Make the package importable without an editable install.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from mediafilter.app import LOCALE_DIR
from mediafilter.config import Config
from mediafilter.i18n import Translator
from mediafilter.ui.theme import apply_theme
from mediafilter.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    config = Config.load()
    tr = Translator(LOCALE_DIR)
    tr.set_fallback("en")
    tr.set_language("zh")

    for mode in ("light", "dark", "system"):
        apply_theme(app, mode)
        win = MainWindow(tr, config)
        win.show()
        win.toggle_language()  # exercise retranslate, then restore
        win.toggle_language()

        # exercise a scan against a tiny temp folder (no ffprobe -> errors route)
        import tempfile
        from pathlib import Path
        tmp = Path(tempfile.mkdtemp())
        (tmp / "a.mp4").write_text("x")
        win.start_scan(str(tmp))

        QTimer.singleShot(0, win.close)
        app.processEvents()

    print("smoke OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())