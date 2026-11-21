"""Batch processing dialog: fixed layout, task switching and advanced panel."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from mediafilter.config import Config
from mediafilter.core.models import FileRecord, MediaMetadata
from mediafilter.i18n import Translator
from mediafilter.ui.tokens import LIGHT
from mediafilter.ui.widgets.batch_process import BatchProcessDialog, BatchSettings

LOCALES = Path(__file__).parents[1] / "src" / "mediafilter" / "i18n" / "locales"


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def dialog(qt_app, tmp_path, monkeypatch):
    # The encoder probe runs ffmpeg; layout tests do not need it.
    monkeypatch.setattr(BatchProcessDialog, "_start_probe", lambda self: None)
    tr = Translator(LOCALES)
    tr.set_language("zh")
    tr.set_fallback("en")
    records = []
    for index, ext in enumerate(("mp4", "mkv")):
        path = tmp_path / f"clip_{index}.{ext}"
        path.write_bytes(b"x" * 2048)
        meta = MediaMetadata()
        meta.duration = 60.0
        records.append(FileRecord(path, path.name, ext, 2048, metadata=meta))
    window = BatchProcessDialog(records, tr.tr, [], tokens=LIGHT, config=Config())
    yield window
    window.close()


def test_dialog_keeps_the_prototype_size(qt_app, dialog):
    assert dialog.size().width() == 960
    assert dialog.size().height() == 760
    assert set(dialog._cards) == {"remux", "compress", "custom"}
    assert dialog._rail_values["mode"].text() == "压缩转码"


def test_task_switch_resets_the_form_to_the_top(qt_app, dialog):
    dialog.show()
    qt_app.processEvents()
    dialog._settings.advanced = True
    dialog._settings.output = "custom"
    dialog._settings.folder = str(Path(dialog._records[0].path).parent / "out")
    dialog._refresh_all(rebuild=True)
    qt_app.processEvents()
    dialog._scroll_to_bottom()
    for _ in range(3):
        qt_app.processEvents()
    bar = dialog._form_scroll.verticalScrollBar()
    assert bar.maximum() > 0

    dialog._on_task("remux")
    for _ in range(3):
        qt_app.processEvents()
    assert bar.value() == 0


def test_advanced_summary_hides_while_expanded(qt_app, dialog):
    dialog._settings.advanced = True
    dialog._refresh_all(rebuild=True)
    assert dialog._adv_summary.isHidden()

    dialog._toggle_advanced()
    assert dialog._settings.advanced is False
    assert not dialog._adv_summary.isHidden()


def test_advanced_row_opens_on_click(qt_app, dialog):
    # The disclosure used to be an empty row beside the real content, so it
    # had no size and never received a click.
    dialog.show()
    qt_app.processEvents()
    assert dialog._adv_toggle.isVisible()
    assert dialog._adv_toggle.height() > 0

    QTest.mouseClick(dialog._adv_summary, Qt.MouseButton.LeftButton)
    qt_app.processEvents()
    assert dialog._settings.advanced is True


def test_settings_round_trip():
    original = BatchSettings(
        task="remux", container="mkv", suffix="_x", advanced=True,
        failure="stop", fallback=False,
    )
    restored = BatchSettings.from_dict(original.to_dict())
    assert restored == original
    assert BatchSettings.from_dict({"unknown": 1}).task == "compress"