"""Application bootstrap: Qt app, config, translator, theme, main window."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from .config import Config
from .i18n import Translator
from .ui.dialog_base import DialogChromeFilter, set_dialog_tokens
from .ui.icons import brand_icon
from .ui.main_window import MainWindow
from .ui.theme import apply_theme
from .ui.widgets.settings_dialog import wait_for_active_workers

LOCALE_DIR = Path(__file__).parent / "i18n" / "locales"


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Media Filter")
    app.setOrganizationName("mediafilter")
    app.setWindowIcon(brand_icon())

    font = QFont()
    font.setFamilies(["Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei UI"])
    font.setPixelSize(13)
    font.setHintingPreference(QFont.PreferFullHinting)
    app.setFont(font)

    config = Config.load()
    translator = Translator(LOCALE_DIR)
    translator.set_fallback("en")
    languages = translator.available_languages()
    translator.set_language(config.language if config.language in languages else "zh")

    palette = apply_theme(app, config.theme_mode)
    set_dialog_tokens(palette)
    chrome = DialogChromeFilter(app)
    app.installEventFilter(chrome)

    window = MainWindow(translator, config)
    window.show()
    app.aboutToQuit.connect(wait_for_active_workers)
    return app.exec()


__all__ = ["run"]