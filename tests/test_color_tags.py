"""Local colour sampling for cat / dog / car tags and its settings control."""

# pyright: reportMissingImports=false, reportArgumentType=false

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from mediafilter.config import Config
from mediafilter.core.color_tags import (
    aggregate_color_tags,
    classify_box,
    compose_color_label,
)
from mediafilter.core.tagger import Detection, tally_frame
from mediafilter.i18n import Translator
from mediafilter.ui.tokens import LIGHT
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


def _frame(rgb: tuple[int, int, int]) -> np.ndarray:
    frame = np.zeros((640, 640, 3), dtype=np.uint8)
    frame[:, :] = rgb
    return frame


def _box() -> tuple[float, float, float, float]:
    return (120.0, 120.0, 260.0, 260.0)


def test_classify_solid_colours():
    cases = {
        (255, 255, 255): "white",
        (0, 0, 0): "black",
        (128, 128, 128): "gray",
        (220, 30, 30): "red",
        (30, 30, 220): "blue",
        (240, 220, 30): "yellow",
        (30, 180, 60): "green",
    }
    for rgb, expected in cases.items():
        guess = classify_box(_frame(rgb), _box())
        assert guess is not None, rgb
        assert guess.key == expected, rgb


def test_classify_vehicle_ignores_windows_and_tyres():
    frame = np.zeros((640, 640, 3), dtype=np.uint8)
    frame[0:192, :] = (10, 10, 10)          # roof / windows
    frame[192:512, :] = (245, 245, 245)     # body band
    frame[512:, :] = (5, 5, 5)              # wheels / shadow
    guess = classify_box(frame, (40, 40, 560, 560), "vehicle")
    assert guess is not None
    assert guess.key == "white"


def test_classify_multicolour_body_is_not_forced():
    frame = np.zeros((640, 640, 3), dtype=np.uint8)
    frame[0:320, 0:320] = (220, 30, 30)
    frame[0:320, 320:] = (30, 180, 60)
    frame[320:, 0:320] = (30, 30, 220)
    frame[320:, 320:] = (240, 220, 30)
    assert classify_box(frame, (60, 60, 520, 520)) is None


def test_compose_color_label_uses_chinese_base_label():
    assert compose_color_label("猫", "black") == "黑猫"
    assert compose_color_label("车", "white") == "白车"


def test_aggregate_color_tags_requires_stable_votes():
    assert aggregate_color_tags({"车": {"white": 3}}, {"车": 3}, ["车"]) == ["白车"]
    assert aggregate_color_tags({"车": {"white": 1}}, {"车": 3}, ["车"]) == []
    assert aggregate_color_tags({"车": {"white": 2}}, {"车": 2}, ["车"]) == ["白车"]
    # A colour is never emitted for a base tag that did not survive.
    assert aggregate_color_tags({"车": {"white": 3}}, {"车": 3}, []) == []


def test_tag_media_appends_colour_and_respects_switch(monkeypatch):
    from mediafilter.core import tagger

    class DetectorStub:
        def detect(self, _frame):
            return [Detection(15, "cat", 0.9, (100, 100, 300, 300))]

    def run(enabled: bool):
        frames = [_frame((0, 0, 0)) for _ in range(3)]
        monkeypatch.setattr(tagger, "extract_frame", lambda *_a, **_k: frames.pop(0))
        return tagger.tag_media(
            cast(Any, DetectorStub()), "ffmpeg", "clip.mp4", 10.0,
            sample_count=3, color_tags_enabled=enabled,
        )

    assert run(True).tags == ["猫", "黑猫"]
    assert run(False).tags == ["猫"]


def test_tally_frame_votes_one_colour_per_class():
    detections = [
        Detection(15, "cat", 0.9, (100, 100, 300, 300)),
        Detection(15, "cat", 0.8, (400, 400, 80, 80)),
    ]
    tally = tally_frame(detections, _frame((0, 0, 0)))
    assert tally.votes == {"猫": 2}
    assert tally.class_frames == {"猫": 1}
    assert tally.color_votes == {"猫": {"black": 1}}


def test_tally_frame_respects_palette_and_switch():
    detections = [Detection(15, "cat", 0.9, (100, 100, 300, 300))]
    assert tally_frame(detections, _frame((0, 0, 0)), {"dog"}).votes == {}
    off = tally_frame(
        detections, _frame((0, 0, 0)), color_tags_enabled=False
    )
    assert off.votes == {"猫": 1}
    assert off.color_votes == {}
    no_frame = tally_frame(detections, None)
    assert no_frame.color_votes == {}


def test_config_local_color_tags_defaults_and_validates(tmp_path):
    assert Config().local_color_tags is True
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"local_color_tags": False}), encoding="utf-8")
    assert Config.load(path).local_color_tags is False
    path.write_text(json.dumps({"local_color_tags": "no"}), encoding="utf-8")
    assert Config.load(path).local_color_tags is True


def test_settings_color_checkbox_saves_and_resets(qt_app, tr, monkeypatch):
    assert qt_app is not None
    cfg = Config()
    dlg = SettingsDialog(cfg, tr, None, tokens=LIGHT, variant="settings")
    assert dlg._color_local.isChecked() is True
    dlg._color_local.setChecked(False)
    dlg._save()
    assert cfg.local_color_tags is False

    def fake(*args, **kwargs):
        del args, kwargs
        return 0x4000  # QMessageBox.Yes

    monkeypatch.setattr(
        "mediafilter.ui.widgets.settings_dialog.message_box", fake,
    )
    dlg = SettingsDialog(cfg, tr, None, tokens=LIGHT, variant="settings")
    assert dlg._color_local.isChecked() is False
    dlg._reset_page()
    assert dlg._color_local.isChecked() is True
    dlg.close()


def test_settings_color_is_disabled_in_cloud_mode(qt_app, tr):
    assert qt_app is not None
    cfg = Config()
    cfg.recognition_mode = "hybrid"
    dlg = SettingsDialog(cfg, tr, None, tokens=LIGHT, variant="settings")
    try:
        dlg.show()
        qt_app.processEvents()
        assert dlg._color_local.isEnabled()
        assert dlg._mode_cards is not None
        dlg._mode_cards.set_mode("cloud")
        dlg._refresh_mode_state()
        qt_app.processEvents()
        assert not dlg._color_local.isEnabled()
        assert "全云端" in dlg._color_hint.text()
        assert dlg._adv_fact_color.text() == tr("settings.adv_fact_color_na")
    finally:
        dlg.close()


def test_locales_have_color_keys():
    for language in ("zh", "en"):
        data = json.loads((LOCALES / f"{language}.json").read_text(encoding="utf-8"))
        for key in (
            "settings.color_local",
            "settings.color_local_hint",
            "settings.adv_fact_color",
            "settings.adv_fact_color_on",
            "settings.adv_fact_color_detail_na",
        ):
            assert key in data, (language, key)