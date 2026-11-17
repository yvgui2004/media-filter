"""Interaction tests for the searchable model field and save policy."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from mediafilter.config import Config
from mediafilter.core.cloud_models import IMAGE, TEXT, UNKNOWN, ModelInfo
from mediafilter.i18n import Translator
from mediafilter.ui.tokens import LIGHT
from mediafilter.ui.widgets.model_picker import ModelPicker
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
    translator.set_language("zh")
    return translator.tr


MODELS = [
    ModelInfo("lab/vision-a", "Vision A", "lab", "1M", IMAGE, True),
    ModelInfo("lab/vision-b", "Vision B", "lab", "256K", IMAGE),
    ModelInfo("lab/unknown", "Unknown", "lab", "", UNKNOWN),
    ModelInfo("lab/text", "Text", "lab", "128K", TEXT),
]


def test_picker_search_grouping_and_selection(qt_app, tr):
    picker = ModelPicker(tr, LIGHT)
    picker.set_models(MODELS)
    picker.open_popup()
    popup = picker._popup
    assert popup is not None
    popup._search.setText("vision")
    current = popup._list.current_model()
    assert current is not None
    assert current.id.startswith("lab/vision")
    popup._pick(MODELS[1])
    picked = picker.model()
    assert picked is not None
    assert picked.id == "lab/vision-b"
    assert picker._popup is None


def test_picker_manual_id_becomes_custom_model(qt_app, tr):
    picker = ModelPicker(tr, LIGHT)
    picker.set_models(MODELS)
    picker.open_popup()
    popup = picker._popup
    assert popup is not None
    popup._manual_link.click()
    popup._manual_input.setText("my-lab/vision-x")
    popup._use_manual()
    model = picker.model()
    assert model is not None
    assert model.id == "my-lab/vision-x"
    assert model.is_custom
    assert model.capability == UNKNOWN


def test_text_model_blocks_save_unknown_does_not(qt_app, tr):
    dialog = SettingsDialog(Config(), tr, tokens=LIGHT)
    assert dialog._api_status.text.text() == tr("settings.api_untested")
    assert dialog._model_status.text.text() == tr("settings.model_none_status")
    dialog._picker.set_model(MODELS[3])
    dialog._on_model_selected(MODELS[3])
    assert dialog._model_state == "text"
    assert not dialog._save_btn.isEnabled()

    dialog._picker.set_model(MODELS[2])
    dialog._on_model_selected(MODELS[2])
    assert dialog._model_state == "unknown"
    assert dialog._save_btn.isEnabled()
    dialog.close()