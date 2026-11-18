"""Toolbar layout: longer translations must grow the window, not clip."""

from __future__ import annotations

import re as regex
import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from mediafilter.config import Config
from mediafilter.i18n import Translator
from mediafilter.ui.main_window import MainWindow
from mediafilter.ui.tokens import DARK, LIGHT, parse_color
from mediafilter.ui.widgets.mode_switch import AiModeSwitch

LOCALES = Path(__file__).parents[1] / "src" / "mediafilter" / "i18n" / "locales"


def _luminance(hex_color: str) -> float:
    color = parse_color(hex_color)

    def channel(value: int) -> float:
        srgb = value / 255
        return srgb / 12.92 if srgb <= 0.04045 else ((srgb + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * channel(color.red())
        + 0.7152 * channel(color.green())
        + 0.0722 * channel(color.blue())
    )


def _contrast(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


@pytest.mark.parametrize("tokens", [LIGHT, DARK], ids=["light", "dark"])
def test_ai_mode_chip_uses_label_color_without_second_blue(qt_app, tokens):
    """The mode word must be the exact color of the "AI 识别" label.

    A translucent on-accent tint put the 10px word at 3.5:1 and read as
    pale; a tonal pill fixed that but introduced a second blue, and an
    outline read as a stray white box. The chip is plain text now: no
    fill, no border, the same on_accent color as the label.
    """
    assert qt_app is not None
    switch = AiModeSwitch(lambda key, **_: key, tokens)
    label = regex.search(r"color:\s*([^;]+);", switch.main.text_label.styleSheet())
    chip = regex.search(r"color:\s*([^;]+);", switch.main.chip.styleSheet())
    assert label is not None and chip is not None
    assert chip.group(1).strip() == label.group(1).strip()
    assert chip.group(1).strip().lower() == tokens["on_accent"].lower()
    assert "background: transparent" in switch.main.chip.styleSheet()
    assert "border" not in switch.main.chip.styleSheet()
    # Same contrast as the label itself, since both sit on the accent fill.
    assert _contrast(tokens["accent"], tokens["on_accent"]) >= 4.5


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _window(qt_app, tmp_path, language: str) -> MainWindow:
    assert qt_app is not None
    translator = Translator(LOCALES)
    translator.set_fallback("en")
    translator.set_language(language)
    config = Config.load(tmp_path / f"{language}.json")
    config.first_run_done = True
    config.first_run_prompted = True
    config.guide_dismissed = True
    win = MainWindow(translator, config)
    win.resize(980, 700)
    win.show()
    qt_app.processEvents()
    return win


def test_settings_and_pill_share_one_mode(qt_app, tmp_path):
    """Switching in Settings must move the main-window pill (and vice versa)."""
    win = _window(qt_app, tmp_path, "zh")
    try:
        win._on_mode_changed("hybrid")
        assert win._ai.mode() == "hybrid"
        saved = json.loads((tmp_path / "zh.json").read_text(encoding="utf-8"))
        assert saved["recognition_mode"] == "hybrid"

        win._config.recognition_mode = "cloud"
        win._apply_saved_mode()
        assert win._ai.mode() == "cloud"
        assert win._mode == "cloud"
    finally:
        win.close()


def test_english_toolbar_grows_window_instead_of_clipping(qt_app, tmp_path):
    zh = _window(qt_app, tmp_path, "zh")
    zh_width = zh.minimumWidth()
    zh.close()

    en = _window(qt_app, tmp_path, "en")
    try:
        assert en.minimumWidth() >= zh_width
        # The window minimum covers the whole toolbar row, so the fixed
        # Chinese widths can never squeeze the longer English labels.
        assert en.minimumWidth() >= en._filter_bar.minimumSizeHint().width()
        # The split AI button and the thread field must get their full hint.
        assert en._ai.width() >= en._ai.sizeHint().width()
        assert en._threads.width() >= en._threads.sizeHint().width()
    finally:
        en.close()