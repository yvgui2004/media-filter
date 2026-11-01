"""Open the real (onscreen) window briefly, then auto-close.

Useful to verify the Windows platform plugin loads. Run:
.venv/Scripts/python.exe scripts/preview.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from mediafilter.app import LOCALE_DIR
from mediafilter.config import Config
from mediafilter.i18n import Translator
from mediafilter.ui.main_window import MainWindow
from mediafilter.ui.theme import apply_theme


def main() -> int:
    app = QApplication(sys.argv)
    config = Config.load()
    tr = Translator(LOCALE_DIR)
    tr.set_fallback("en")
    tr.set_language(config.language if config.language in ("zh", "en") else "zh")
    apply_theme(app, config.theme_mode)

    win = MainWindow(tr, config)
    win.show()
    QTimer.singleShot(1500, app.quit)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())