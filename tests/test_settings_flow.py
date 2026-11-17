"""Settings / first-run / my-tags behaviour that is easy to regress."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

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

    assert dlg._mode_list is not None
    dlg._mode_list.set_mode("local")
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