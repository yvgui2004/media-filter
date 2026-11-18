"""The upload confirmation's My labels entry and its hybrid guard."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from mediafilter.config import Config
from mediafilter.core.models import FileRecord, MediaMetadata
from mediafilter.i18n import Translator
from mediafilter.ui.main_window import MainWindow
from mediafilter.ui.tokens import LIGHT
from mediafilter.ui.widgets import mode_switch as mode_switch_module
from mediafilter.ui.widgets.mode_switch import UploadConfirmDialog

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


class FakeTagsDialog:
    next_labels: list[str] = []
    opened: list[list[str]] = []
    accepted = True

    def __init__(self, labels, _tr, parent=None, tokens=None):
        type(self).opened.append(list(labels))

    def exec(self):
        return 1 if type(self).accepted else 0

    def labels(self):
        return list(type(self).next_labels)


@pytest.fixture
def fake_tags(monkeypatch):
    FakeTagsDialog.next_labels = []
    FakeTagsDialog.opened = []
    FakeTagsDialog.accepted = True
    monkeypatch.setattr(mode_switch_module, "MyTagsDialog", FakeTagsDialog)
    return FakeTagsDialog


def _dialog(tr, mode="cloud", custom=None, saved=None, frames=8,
            frame_counts=None):
    return UploadConfirmDialog(
        2, frames, mode, "https://dashscope.aliyuncs.com",
        "deepseek-v4.1-flash-1017", ["人物", "场景"], tr, tokens=LIGHT,
        custom_labels=custom or [], on_labels_saved=saved,
        frame_counts=frame_counts,
    )


def test_my_labels_leads_the_chips_and_gets_a_dashed_chip(qt_app, tr):
    assert qt_app is not None
    dlg = _dialog(tr, custom=["露营"])
    try:
        assert dlg._shown_labels[:1] == ["露营"]
        assert "人物" in dlg._shown_labels
        assert dlg._add_chip is not None
        assert not dlg._add_chip.isHidden()
        assert dlg._empty_add.isHidden()
        assert dlg._cloud_empty_note.isHidden()
        assert dlg._need_custom.isHidden()
        assert dlg._run.isEnabled()
    finally:
        dlg.close()


def test_manifest_copy_and_scope_follow_the_mode(qt_app, tr):
    assert qt_app is not None
    cloud = _dialog(tr, mode="cloud")
    hybrid = _dialog(tr, mode="hybrid", custom=["露营"])
    try:
        assert cloud.minimumWidth() == 520
        assert cloud._mode_chip.text() == "全云端"
        assert "预计" in cloud._lead.text()
        assert "8" in cloud._lead.text()
        assert cloud._scope.text() == "2 个视频 · 每个抽 4 帧"
        assert not cloud._cloud_empty_note.isHidden()
        assert cloud._need_custom.isHidden()
        assert cloud._run.isEnabled()

        assert hybrid._mode_chip.text() == "混合"
        assert "命中" in hybrid._lead.text()
        assert "命中" in hybrid._foot_note.text()
        assert hybrid._cloud_empty_note.isHidden()
        assert hybrid._run.isEnabled()
    finally:
        cloud.close()
        hybrid.close()


def test_variable_frame_counts_show_a_range(qt_app, tr):
    assert qt_app is not None
    dlg = _dialog(tr, frames=14, frame_counts=[6, 8])
    try:
        assert dlg._scope.text() == "2 个视频 · 每个抽 6–8 帧"
        assert "14" in dlg._lead.text()
    finally:
        dlg.close()


def test_no_custom_labels_shows_the_full_width_add_row(qt_app, tr):
    assert qt_app is not None
    dlg = _dialog(tr)
    try:
        assert dlg._add_chip is None
        assert not dlg._empty_add.isHidden()
        assert dlg._shown_labels == ["人物", "场景"]
        assert dlg._run.isEnabled()          # cloud may run without my labels
        assert dlg._need_custom.isHidden()
    finally:
        dlg.close()


def test_editing_from_the_card_saves_and_refreshes(qt_app, tr, fake_tags):
    assert qt_app is not None
    saved: list[list[str]] = []
    dlg = _dialog(tr, saved=saved.append)
    try:
        fake_tags.next_labels = ["露营"]
        dlg._empty_add.click()
        assert saved == [["露营"]]
        assert dlg._custom_labels == ["露营"]
        assert dlg._shown_labels[0] == "露营"
        assert dlg._add_chip is not None
        assert dlg._empty_add.isHidden()
    finally:
        dlg.close()


def test_hybrid_blocks_continue_when_my_labels_are_cleared(
    qt_app, tr, fake_tags
):
    assert qt_app is not None
    saved: list[list[str]] = []
    dlg = _dialog(tr, mode="hybrid", custom=["露营"], saved=saved.append)
    try:
        assert dlg._run.isEnabled()
        fake_tags.next_labels = []
        assert dlg._add_chip is not None
        dlg._add_chip.click()
        assert fake_tags.opened == [["露营"]]
        assert saved == [[]]
        assert dlg._custom_labels == []
        assert not dlg._run.isEnabled()
        assert not dlg._need_custom.isHidden()
        assert not dlg._empty_add.isHidden()
    finally:
        dlg.close()


def test_cancelling_the_editor_changes_nothing(qt_app, tr, fake_tags):
    assert qt_app is not None
    saved: list[list[str]] = []
    dlg = _dialog(tr, custom=["露营"], saved=saved.append)
    try:
        fake_tags.accepted = False
        fake_tags.next_labels = ["篮球"]
        assert dlg._add_chip is not None
        dlg._add_chip.click()
        assert saved == []
        assert dlg._custom_labels == ["露营"]
        assert dlg._shown_labels[0] == "露营"
    finally:
        dlg.close()


def test_wrapped_label_row_gets_the_height_it_needs(qt_app, tr):
    """The flow wraps; the dialog must grow instead of clipping the row."""
    assert qt_app is not None
    custom = [f"很长的标签第{i}个" for i in range(8)]
    dlg = _dialog(tr, custom=custom)
    dlg.show()
    QTest.qWait(10)
    try:
        width = dlg._chip_holder.width()
        needed = dlg._flow.heightForWidth(width)
        assert dlg._shown_labels == custom
        assert needed > 30                     # actually wrapped
        assert dlg._chip_holder.minimumHeight() >= needed
        assert dlg.height() >= dlg.minimumSizeHint().height()
    finally:
        dlg.close()


def test_main_window_separates_my_labels_and_persists_edits(
    qt_app, tr, tmp_path, monkeypatch
):
    assert qt_app is not None
    from mediafilter.ui import main_window as main_window_module

    config = Config.load(tmp_path / "cfg.json")
    config.first_run_done = True
    config.first_run_prompted = True
    config.guide_dismissed = True
    config.recognition_mode = "cloud"
    config.custom_labels = ["露营"]
    win = MainWindow(tr.__self__, config)
    captured: dict[str, object] = {}

    class FakeConfirm:
        def __init__(self, _videos, frames, _mode, _base, _model, labels,
                     _tr, parent=None, tokens=None, custom_labels=None,
                     on_labels_saved=None, frame_counts=None):
            captured.update(
                labels=list(labels), custom_labels=list(custom_labels or []),
                frames=frames, frame_counts=list(frame_counts or []),
                on_labels_saved=on_labels_saved,
            )

        def exec(self):
            return 0

    monkeypatch.setattr(main_window_module, "UploadConfirmDialog", FakeConfirm)
    try:
        win._ai_targets = lambda: [
            FileRecord(Path("C:/media/a.mp4"), "a.mp4", "mp4", 1024)
        ]
        win._ai.set_mode("cloud")
        win._request_ai()

        assert captured["custom_labels"] == ["露营"]
        assert captured["frames"] == 6
        assert captured["frame_counts"] == [6]   # auto on unknown duration
        seen_labels = captured["labels"]
        assert isinstance(seen_labels, list)
        assert "露营" not in seen_labels       # custom is passed separately
        saved = captured["on_labels_saved"]
        assert callable(saved)
        saved(["篮球"])
        assert config.custom_labels == ["篮球"]
        persisted = json.loads((tmp_path / "cfg.json").read_text(encoding="utf-8"))
        assert persisted["custom_labels"] == ["篮球"]
    finally:
        win.close()


def test_confirm_frames_follow_the_saved_frame_policy(
    qt_app, tr, tmp_path, monkeypatch
):
    """Changing 抽帧强度 must change both the run and the confirm copy."""
    assert qt_app is not None
    from mediafilter.ui import main_window as main_window_module

    config = Config.load(tmp_path / "cfg.json")
    config.first_run_done = True
    config.first_run_prompted = True
    config.guide_dismissed = True
    config.recognition_mode = "cloud"
    config.frame_policy = "auto"
    win = MainWindow(tr.__self__, config)
    captured: dict[str, object] = {}

    class FakeConfirm:
        def __init__(self, _videos, frames, *_args, frame_counts=None, **_kwargs):
            captured.update(frames=frames, frame_counts=list(frame_counts or []))

        def exec(self):
            return 0

    monkeypatch.setattr(main_window_module, "UploadConfirmDialog", FakeConfirm)
    try:
        win._ai_targets = lambda: [
            FileRecord(
                Path("C:/media/a.mp4"), "a.mp4", "mp4", 1024,
                metadata=MediaMetadata(duration=30.0),
            ),
            FileRecord(
                Path("C:/media/b.mp4"), "b.mp4", "mp4", 1024,
                metadata=MediaMetadata(duration=700.0),
            ),
        ]
        win._ai.set_mode("cloud")
        win._request_ai()
        assert captured["frame_counts"] == [6, 8]
        assert captured["frames"] == 14

        config.frame_policy = "fast"
        win._request_ai()
        assert captured["frame_counts"] == [4, 4]
        assert captured["frames"] == 8

        config.frame_policy = "fine"
        win._request_ai()
        assert captured["frame_counts"] == [12, 16]
        assert captured["frames"] == 28
    finally:
        win.close()