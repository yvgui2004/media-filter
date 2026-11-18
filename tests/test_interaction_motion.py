"""P1 interaction polish: filtered empty state, guide reveal, caret, toast."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from mediafilter.config import Config
from mediafilter.core.models import FileRecord
from mediafilter.i18n import Translator
from mediafilter.ui.main_window import MainWindow
from mediafilter.ui.select_field import SelectField
from mediafilter.ui.tokens import LIGHT
from mediafilter.ui.widgets.mode_switch import AiModeSwitch
from mediafilter.ui.widgets.settings_dialog import SettingsDialog

LOCALES = Path(__file__).parents[1] / "src" / "mediafilter" / "i18n" / "locales"


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _records() -> list[FileRecord]:
    return [
        FileRecord(Path("C:/media/a.mp4"), "a.mp4", "mp4", 1024),
        FileRecord(Path("C:/media/b.mkv"), "b.mkv", "mkv", 2048),
    ]


def _window(qt_app, tmp_path) -> MainWindow:
    assert qt_app is not None
    translator = Translator(LOCALES)
    translator.set_fallback("en")
    translator.set_language("zh")
    config = Config.load(tmp_path / "cfg.json")
    config.first_run_done = True
    config.first_run_prompted = True
    config.guide_dismissed = True
    win = MainWindow(translator, config)
    win.resize(1000, 700)
    win.show()
    qt_app.processEvents()
    return win


def test_empty_search_swaps_to_filtered_page_and_clear_filters_restores_it(
    qt_app, tmp_path
):
    win = _window(qt_app, tmp_path)
    try:
        records = _records()
        win._model.set_records(records)
        win._populate_filter_formats(records)
        win._rebuild_tag_combo()
        win._sync_empty_state()
        assert win._stack.currentWidget() is win._view

        win._search.setText("zzzz-no-match")
        assert win._proxy.rowCount() == 0
        assert win._stack.currentWidget() is win._empty_filter
        assert win._empty_filter._title.text() == win._tr("empty.filtered_title")
        assert win._empty_filter._primary_icon == "refresh"

        win._clear_filters()
        assert win._search.text() == ""
        assert win._filter_combo.currentIndex() == 0
        assert win._tag_combo.currentIndex() == 0
        assert win._proxy.rowCount() == len(records)
        assert win._stack.currentWidget() is win._view
        assert win._toast.isVisible()
        assert win._toast._label.text() == win._tr("toast.filters_cleared")
    finally:
        win.close()


def test_guide_bar_reveals_and_collapses_without_motion(qt_app, tmp_path, monkeypatch):
    monkeypatch.setattr("mediafilter.ui.motion.animations_enabled", lambda: False)
    win = _window(qt_app, tmp_path)
    try:
        win._config.first_run_done = False
        win._config.first_run_prompted = True
        win._config.guide_dismissed = False
        win._update_guide_bar()
        assert win._guide.isVisible()
        assert win._guide.height() == 40

        win._dismiss_guide()
        assert not win._guide.isVisible()
        assert win._config.guide_dismissed is True
        # Restored so the next reveal can start from the full height again.
        assert win._guide.minimumHeight() == 40
    finally:
        win.close()


def test_popover_flips_caret_while_open(qt_app, tmp_path):
    win = _window(qt_app, tmp_path)
    try:
        assert win._ai.caret._open is False
        win._ai.caret.click()
        qt_app.processEvents()
        assert win._ai._popover is not None
        assert win._ai.caret._open is True

        win._ai._popover.close()
        qt_app.processEvents()
        assert win._ai.caret._open is False
    finally:
        win.close()


def test_busy_button_pulses_and_stops(qt_app, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "mediafilter.ui.widgets.mode_switch.animations_enabled", lambda: True
    )
    win = _window(qt_app, tmp_path)
    try:
        win._ai.set_busy(True)
        assert win._ai._pulse is not None
        assert win._ai.main.text_label.text() == win._tr("toolbar.ai_stop")

        win._ai.set_busy(False)
        assert win._ai._pulse is None
        effect = win._ai.main.icon_label.graphicsEffect()
        assert effect is None or effect.opacity() == 1.0
    finally:
        win.close()


def test_switching_mode_shows_a_toast(qt_app, tmp_path):
    win = _window(qt_app, tmp_path)
    try:
        win._on_mode_changed("cloud")
        assert win._toast.isVisible()
        expected = win._tr(
            "toast.mode_switched", mode=win._tr("mode.cloud.name")
        )
        assert win._toast._label.text() == expected
    finally:
        win.close()


def _press(widget) -> None:
    pos = QPointF(5, 5)
    event = QMouseEvent(
        QEvent.Type.MouseButtonPress, pos, pos,
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    widget.mousePressEvent(event)


def test_second_click_on_select_field_arrow_retracts(qt_app):
    assert qt_app is not None
    field = SelectField("格式")
    field.addItems(["全部", "MP4"])
    field._popup_closed()          # what Qt does when the popup closes
    assert field._suppress_open
    _press(field)                  # replayed press from the closing click
    assert field._popup is None
    assert field._suppress_open is False


def test_second_click_on_mode_caret_retracts(qt_app):
    assert qt_app is not None
    switch = AiModeSwitch(lambda key, **_: key, LIGHT)
    switch._on_popover_closed()    # popup closed by the first caret click
    switch._toggle_popover()       # replayed click must not reopen
    assert switch._popover is None


def test_settings_dialog_matches_welcome_card_proportion(qt_app):
    assert qt_app is not None

    def tr(key, **_kwargs):
        return key

    settings = SettingsDialog(Config(), tr, None, tokens=LIGHT)
    welcome = SettingsDialog(Config(), tr, None, tokens=LIGHT, variant="first_run")
    try:
        assert settings.width() == 700
        assert 620 <= settings.height() <= 751
        assert welcome.width() == 760
        # Same 760:815 proportion, scaled down and capped by the screen.
        expected = welcome.width() * 815 / 760
        if welcome.height() >= expected:
            assert abs(settings.width() * 815 / 760 - settings.height()) <= 1
    finally:
        settings.close()
        welcome.close()