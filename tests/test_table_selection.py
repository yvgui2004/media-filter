"""Table interaction: ticks are the only selection, blue is drag preview only."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QSignalBlocker, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from mediafilter.config import Config
from mediafilter.core.models import FileRecord
from mediafilter.i18n import Translator
from mediafilter.ui.main_window import MainWindow

LOCALES = Path(__file__).parents[1] / "src" / "mediafilter" / "i18n" / "locales"


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def window(qt_app, tmp_path):
    assert qt_app is not None
    translator = Translator(LOCALES)
    translator.set_fallback("en")
    translator.set_language("zh")
    config = Config.load(tmp_path / "cfg.json")
    config.first_run_done = True
    config.first_run_prompted = True
    config.guide_dismissed = True
    win = MainWindow(translator, config)
    win.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    win.resize(1000, 700)
    win.show()
    qt_app.processEvents()

    records = [
        FileRecord(Path(f"C:/media/clip_{index}.mp4"), f"clip_{index}.mp4", "mp4", 1024)
        for index in range(6)
    ]
    win._model.set_records(records)
    win._populate_filter_formats(records)
    win._rebuild_tag_combo()
    win._sync_empty_state()
    qt_app.processEvents()
    yield win, records
    win.close()
    qt_app.processEvents()


def _point(view, row: int, column: int = 1) -> QPoint:
    return QPoint(
        view.columnViewportPosition(column) + 20,
        view.rowViewportPosition(row) + 20,
    )


def _drag(qt_app, view, first: int, last: int) -> None:
    viewport = view.viewport()
    QTest.mousePress(
        viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
        _point(view, first),
    )
    qt_app.processEvents()
    QTest.mouseMove(viewport, _point(view, last), 50)
    qt_app.processEvents()
    QTest.mouseRelease(
        viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
        _point(view, last),
    )
    qt_app.processEvents()


def test_click_ticks_without_leaving_a_blue_selection(qt_app, window):
    win, records = window
    view = win._view
    QTest.mouseClick(
        view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
        _point(view, 0),
    )
    qt_app.processEvents()
    assert records[0].checked is True
    assert not view.selectionModel().hasSelection()

    QTest.mouseClick(
        view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
        _point(view, 0),
    )
    qt_app.processEvents()
    assert records[0].checked is False
    assert not view.selectionModel().hasSelection()


def test_drag_ticks_the_range_then_clears_the_preview(qt_app, window):
    win, records = window
    view = win._view
    previews: list[tuple[bool, int]] = []
    view.dragPreviewChanged.connect(lambda tick, count: previews.append((tick, count)))

    _drag(qt_app, view, 0, 2)

    assert [record.checked for record in records] == [True, True, True, False, False, False]
    assert not view.selectionModel().hasSelection()
    assert previews[-1] == (True, 3)


def test_drag_from_a_ticked_row_unticks_the_range(qt_app, window):
    win, records = window
    view = win._view
    win._model.set_checked([0, 1, 2], True)
    previews: list[tuple[bool, int]] = []
    view.dragPreviewChanged.connect(lambda tick, count: previews.append((tick, count)))

    _drag(qt_app, view, 0, 2)

    assert [record.checked for record in records] == [False, False, False, False, False, False]
    assert not view.selectionModel().hasSelection()
    assert previews[-1] == (False, 3)


def test_actions_only_use_ticks_not_a_stray_selection(window):
    win, records = window
    view = win._view
    win._model.set_checked([1], True)
    # Simulate a view selection that did not come through the click handler.
    blocker = QSignalBlocker(view.selectionModel())
    view.selectRow(2)
    blocker.unblock()

    assert view.selectionModel().selectedRows()
    assert win._target_records() == [records[1]]


def test_shift_click_ticks_the_range(qt_app, window):
    win, records = window
    view = win._view
    viewport = view.viewport()
    QTest.mouseClick(
        viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
        _point(view, 1),
    )
    qt_app.processEvents()
    QTest.mouseClick(
        viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier,
        _point(view, 3),
    )
    qt_app.processEvents()
    assert [record.checked for record in records] == [
        False, True, True, True, False, False,
    ]
    assert not view.selectionModel().hasSelection()


def test_escape_cancels_a_drag_without_ticking(qt_app, window):
    win, records = window
    view = win._view
    viewport = view.viewport()
    QTest.mousePress(
        viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
        _point(view, 0),
    )
    qt_app.processEvents()
    QTest.mouseMove(viewport, _point(view, 3), 50)
    qt_app.processEvents()
    QTest.keyClick(view, Qt.Key.Key_Escape)
    qt_app.processEvents()
    QTest.mouseRelease(
        viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
        _point(view, 3),
    )
    qt_app.processEvents()
    assert not any(record.checked for record in records)
    assert not view.selectionModel().hasSelection()


def test_batch_button_follows_the_tick_count(qt_app, window):
    win, _ = window
    view = win._view
    assert win._batch_btn.isEnabled() is False
    assert win._export_btn.isEnabled() is False

    QTest.mouseClick(
        view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
        _point(view, 0),
    )
    qt_app.processEvents()
    assert win._batch_btn.isEnabled() is True
    assert win._batch_btn.text().endswith("1")
    assert win._export_btn.isEnabled() is True