"""Settings / first-run / my-tags behaviour that is easy to regress."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from mediafilter.config import Config
from mediafilter.core.vocabulary import ALL_TAG_IDS
from mediafilter.i18n import Translator
from mediafilter.ui.theme import apply_theme
from mediafilter.ui.tokens import LIGHT
from mediafilter.ui.widgets.my_tags_dialog import MyTagsDialog
from mediafilter.ui.widgets.settings_dialog import SettingsDialog

LOCALES = Path(__file__).parents[1] / "src" / "mediafilter" / "i18n" / "locales"


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(scope="module")
def tr():
    translator = Translator(LOCALES)
    translator.set_fallback("en")
    translator.set_language("zh")
    return translator.tr


def _dialog(qt_app, tr, cfg, variant="settings", parent=None):
    assert qt_app is not None
    return SettingsDialog(cfg, tr, parent, tokens=LIGHT, variant=variant)


def test_first_run_local_save_completes_setup(qt_app, tr):
    cfg = Config()
    dlg = _dialog(qt_app, tr, cfg, variant="first_run")
    assert dlg._selected_mode() == "local"
    assert not dlg._api_body.isEnabled()
    dlg._save()
    assert cfg.first_run_done is True
    assert cfg.first_run_prompted is True
    assert cfg.recognition_mode == "local"
    assert list(cfg.tag_palette) == list(ALL_TAG_IDS)


def test_settings_mode_switch_enables_api_and_requires_key(qt_app, tr):
    cfg = Config()
    cfg.recognition_mode = "hybrid"
    dlg = _dialog(qt_app, tr, cfg)
    assert dlg._api_effect is not None
    assert dlg._api_body.isEnabled()
    assert dlg._api_effect.isEnabled() is False
    dlg._key.clear()
    dlg._save()
    assert cfg.first_run_done is False

    assert dlg._mode_cards is not None
    dlg._mode_cards.set_mode("local")
    dlg._refresh_mode_state()
    assert not dlg._api_body.isEnabled()
    assert dlg._api_effect.isEnabled() is True


def test_first_run_hybrid_with_key_selected_by_default(qt_app, tr):
    cfg = Config()
    cfg.cloud_api_key_dpapi = "ciphertext"
    dlg = _dialog(qt_app, tr, cfg, variant="first_run")
    assert dlg._selected_mode() == "hybrid"


def test_tag_panel_toggle_and_defaults(qt_app, tr):
    cfg = Config()
    dlg = _dialog(qt_app, tr, cfg)
    panel = dlg._tags_panel
    assert panel.count_enabled() == 26
    panel.set_all(False)
    assert panel.enabled_ids() == []
    first = ALL_TAG_IDS[0]
    panel._buttons[first].setChecked(True)
    assert panel.enabled_ids() == [first]


def test_tag_panel_minimum_height_is_not_inflated(qt_app, tr):
    """FlowLayout rows used to report a many-line height as their minimum,
    which made the scroll area reserve a large blank area under the page."""
    dlg = _dialog(qt_app, tr, Config())
    panel = dlg._tags_panel
    assert panel.minimumSizeHint().height() <= panel.sizeHint().height() + 8
    assert panel.minimumSizeHint().height() < 400


def test_tag_chip_border_box_matches_fixed_height(qt_app, tr):
    """The chip's style box must not exceed its 26px slot.

    The QSS ``height`` is the content box, so ``height: 26px`` plus the 1px
    borders made the layout item 28px tall while ``setFixedHeight(26)``
    clipped the widget to 26 — the bottom border was cut off.
    """
    assert qt_app is not None
    apply_theme(qt_app, "light")
    dlg = _dialog(qt_app, tr, Config())
    chip = dlg._tags_panel._buttons[ALL_TAG_IDS[0]]
    assert chip.sizeHint().height() <= 26
    assert chip.minimumSizeHint().height() <= 26
    assert chip.height() <= 26


def test_frame_policy_note_and_save_follow_selection(qt_app, tr):
    cfg = Config()
    dlg = _dialog(qt_app, tr, cfg)
    try:
        assert cfg.frame_policy == "auto"
        assert "6" in dlg._frame_note.text()
        dlg._segment.buttons["fast"].click()
        assert "4" in dlg._frame_note.text()
        dlg._segment.buttons["fine"].click()
        assert "12" in dlg._frame_note.text()
        dlg._save()
        assert cfg.frame_policy == "fine"
    finally:
        dlg.close()


def test_start_tagging_passes_the_saved_policy_to_the_worker(
    qt_app, tr, tmp_path, monkeypatch
):
    """The setting must reach the run, not just the settings page copy."""
    assert qt_app is not None
    from mediafilter.core.models import FileRecord
    from mediafilter.ui import main_window as main_window_module

    cfg = Config()
    cfg.first_run_done = True
    cfg.first_run_prompted = True
    cfg.guide_dismissed = True
    cfg.frame_policy = "fine"
    win = main_window_module.MainWindow(tr.__self__, cfg)
    captured: dict[str, object] = {}

    class FakeWorker:
        def __init__(self, *_args, **kwargs):
            captured.update(kwargs)

        def isRunning(self):  # noqa: N802 - mirrors QThread
            return False

        def cancel(self):
            pass

        def wait(self, *_args):
            return True

    monkeypatch.setattr(main_window_module, "TagWorker", FakeWorker)
    monkeypatch.setattr(main_window_module, "find_model", lambda *_a: Path("m.onnx"))
    monkeypatch.setattr(win, "_start_tag_worker", lambda _worker: None)
    try:
        win._ffmpeg_path = "ffmpeg"
        win.start_tagging([
            FileRecord(Path("C:/media/a.mp4"), "a.mp4", "mp4", 1024)
        ])
        assert captured["frame_policy"] == "fine"
    finally:
        win.close()


def test_settings_my_tags_edit_opens_editor(qt_app, tr, monkeypatch):
    assert qt_app is not None
    from mediafilter.ui.widgets import settings_dialog as settings_module

    opened: list[list[str]] = []

    class FakeTagsDialog:
        class DialogCode:
            Accepted = 1

        def __init__(self, labels, _tr, parent=None, tokens=None):
            opened.append(list(labels))

        def exec(self):
            return 0

        def labels(self):
            return []

    monkeypatch.setattr(settings_module, "MyTagsDialog", FakeTagsDialog)
    dlg = _dialog(qt_app, tr, Config())
    try:
        assert dlg._custom_edit.isEnabled()
        assert dlg._custom_count.text()
        dlg._custom_edit.click()
        assert opened == [[]]
    finally:
        dlg.close()


def test_my_tags_enter_confirms_the_tag_not_import(qt_app, tr):
    assert qt_app is not None
    dlg = MyTagsDialog([], tr, None, tokens=LIGHT)
    dlg.show()
    try:
        imported: list[int] = []
        dlg._import_btn.clicked.disconnect()
        dlg._import_btn.clicked.connect(lambda: imported.append(1))
        assert not dlg._import_btn.autoDefault()
        assert dlg._save_btn.isDefault()

        dlg._input.setFocus()
        dlg._input.setText("踢足球")
        QTest.keyClick(dlg._input, Qt.Key.Key_Return)

        assert dlg.labels() == ["踢足球"]
        assert imported == []
        assert dlg.isVisible()  # Enter did not press 保存 and close the dialog
    finally:
        dlg.close()


def test_my_tags_adds_and_caps(qt_app, tr):
    assert qt_app is not None
    dlg = MyTagsDialog([], tr, None, tokens=LIGHT)
    dlg._input.setText("踢足球、篮球，王者荣耀")
    dlg._add()
    assert dlg.labels() == ["踢足球", "篮球", "王者荣耀"]

    dlg._grid.set_labels([f"标签{i}" for i in range(10)])
    dlg._refresh_state()
    assert not dlg._input.isEnabled()

    dlg._grid.set_labels(["王者荣耀"])
    dlg._refresh_state()
    dlg._input.setText("王者荣耀")
    dlg._add()
    assert dlg.labels() == ["王者荣耀"]

def test_settings_uses_tabs_and_live_summary(qt_app, tr):
    """B4: tabs drive one pane, while the rail mirrors the draft state."""
    cfg = Config()
    cfg.recognition_mode = "hybrid"
    cfg.custom_labels = ["露营"]
    cfg.frame_policy = "auto"
    cfg.tag_palette = list(ALL_TAG_IDS)
    dlg = _dialog(qt_app, tr, cfg)
    try:
        assert dlg._stack is not None
        assert set(dlg._pages) == {"mode", "api", "tags", "advanced"}
        assert dlg._tabs["mode"].isChecked()
        assert "混合" in dlg._chip_mode.text()
        assert "26" in dlg._chip_tags.text()
        assert "6–8" in dlg._chip_frame.text()
        assert dlg._rail_custom.value.text() == "1 / 10"
        assert dlg._rail_builtin.value.text() == "26 / 26"

        dlg._segment.buttons["fast"].click()
        assert "4" in dlg._chip_frame.text()
        assert "4" in dlg._rail_scope_frames.value.text()

        dlg._show_tab("tags")
        assert dlg._stack.currentWidget() is dlg._pages["tags"]
        assert dlg._tabs["tags"].isChecked()
        assert dlg._tabs["mode"].isChecked() is False

        assert dlg._mode_cards is not None
        dlg._mode_cards.set_mode("local")
        dlg._refresh_mode_state()
        assert not dlg._api_body.isEnabled()
        assert dlg._api_effect is not None and dlg._api_effect.isEnabled()
        assert dlg._rail_connection.value.text() == tr("settings.connection_local")
    finally:
        dlg.close()


def test_save_switches_to_api_when_key_is_missing(qt_app, tr):
    cfg = Config()
    cfg.recognition_mode = "hybrid"
    dlg = _dialog(qt_app, tr, cfg)
    try:
        dlg._show_tab("tags")
        dlg._key.clear()
        dlg._save()
        assert dlg._stack is not None
        assert dlg._stack.currentWidget() is dlg._pages["api"]
        assert dlg._key_required.isVisible() is False  # not shown yet
        assert dlg._key_required.isHidden() is False
    finally:
        dlg.close()


def test_custom_labels_preview_tracks_editor_result(qt_app, tr, monkeypatch):
    assert qt_app is not None
    from mediafilter.ui.widgets import settings_dialog as settings_module

    class FakeTagsDialog:
        class DialogCode:
            Accepted = 1

        def __init__(self, labels, _tr, parent=None, tokens=None):
            pass

        def exec(self):
            return 1

        def labels(self):
            return ["露营", "踢足球"]

    monkeypatch.setattr(settings_module, "MyTagsDialog", FakeTagsDialog)
    dlg = _dialog(qt_app, tr, Config())
    try:
        assert dlg._custom_count.text() == "0 / 10"
        dlg._custom_edit.click()
        assert dlg._custom_count.text() == "2 / 10"
        chips = [
            widget.text()
            for widget in dlg._custom_chips.findChildren(QLabel)
            if widget.objectName() == "PreviewChip"
        ]
        assert chips == ["露营", "踢足球"]
    finally:
        dlg.close()


def test_b4_compact_density_is_scoped_to_regular_settings(qt_app, tr):
    """The tabbed page is the 900x570 prototype enlarged 1.15x; first-run is not."""
    assert qt_app is not None
    apply_theme(qt_app, "light")
    cfg = Config()
    cfg.first_run_done = True
    cfg.recognition_mode = "hybrid"
    dlg = _dialog(qt_app, tr, cfg)
    dlg.ensurePolished()
    try:
        chip = dlg._tags_panel._buttons[ALL_TAG_IDS[0]]
        assert chip.height() == 25
        assert dlg._save_btn.height() == 37
        assert dlg._test_btn.height() == 37
        assert dlg._mode_cards is not None
        assert dlg._mode_cards.cards["local"].minimumHeight() == 120
        assert dlg._segment.buttons["auto"].height() == 28
        assert dlg._segment.buttons["auto"].font().pixelSize() == 12
    finally:
        dlg.close()

    first = _dialog(qt_app, tr, Config(), variant="first_run")
    first.ensurePolished()
    try:
        chip = first._tags_panel._buttons[ALL_TAG_IDS[0]]
        assert chip.height() == 26
        assert first._mode_cards is not None
        assert first._mode_cards.cards["local"].minimumHeight() == 112
    finally:
        first.close()
