"""Application bootstrap: Qt app, config, translator, theme, main window."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .config import Config
from .i18n import Translator
from .ui.main_window import MainWindow
from .ui.theme import apply_theme

LOCALE_DIR = Path(__file__).parent / "i18n" / "locales"
ASSET_DIR = Path(__file__).parent / "assets"


def _app_icon() -> QIcon:
    for name in ("app_icon.ico", "app_icon.png"):
        path = ASSET_DIR / name
        if path.exists():
            return QIcon(str(path))
    return QIcon()


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Media Filter")
    app.setOrganizationName("mediafilter")
    app.setWindowIcon(_app_icon())

    config = Config.load()
    translator = Translator(LOCALE_DIR)
    translator.set_fallback("en")
    languages = translator.available_languages()
    translator.set_language(config.language if config.language in languages else "zh")

    apply_theme(app, config.theme_mode)

    window = MainWindow(translator, config)
    window.show()
    return app.exec()


__all__ = ["run"]