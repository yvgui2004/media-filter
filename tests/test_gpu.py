"""Device discovery and the settings-page inference-device control."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from mediafilter.config import Config
from mediafilter.core import gpu
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


def _adapter(name="NVIDIA GeForce RTX 5070 Ti", vendor=0x10DE,
             dedicated=16384, shared=32768, software=False,
             index=0) -> gpu.AdapterInfo:
    return gpu.AdapterInfo(
        index=index, name=name, vendor_id=vendor,
        dedicated_video_mb=dedicated, shared_system_mb=shared, software=software,
    )


def test_normalize_device_rejects_unknown_values():
    assert gpu.normalize_device("gpu") == "gpu"
    assert gpu.normalize_device("CPU") == "auto"
    assert gpu.normalize_device(None) == "auto"
    assert gpu.normalize_device("") == "auto"


def test_short_adapter_name_strips_vendor_and_suffixes():
    assert gpu.short_adapter_name("NVIDIA GeForce RTX 5070 Ti") == "RTX 5070 Ti"
    assert gpu.short_adapter_name("AMD Radeon RX 7800 XT") == "RX 7800 XT"
    assert gpu.short_adapter_name("Intel(R) Arc(TM) A770 Graphics") == "Arc A770"
    assert gpu.short_adapter_name("  NVIDIA   GeForce RTX 4060 Laptop GPU ") == "RTX 4060"
    assert gpu.short_adapter_name("") == "GPU"


def test_integrated_gpu_detection():
    assert _adapter(vendor=0x8086, dedicated=0, shared=16384).is_integrated is True
    assert _adapter(vendor=0x8086, dedicated=128, shared=16384).is_integrated is True
    assert _adapter(dedicated=12288).is_integrated is False
    warp = _adapter(name="Microsoft Basic Render Driver", vendor=0x1414,
                    dedicated=0, shared=0, software=True)
    assert warp.is_integrated is False


def test_discrete_gpu_wins_over_integrated():
    report = gpu.DeviceReport((
        _adapter(index=0, name="Intel Arc Graphics", vendor=0x8086,
                 dedicated=128, shared=16384),
        _adapter(index=1),
    ))
    assert report.hardware is not None
    assert report.hardware.name == "NVIDIA GeForce RTX 5070 Ti"


def test_warp_only_report_is_software_only():
    warp = _adapter(name="Microsoft Basic Render Driver", vendor=0x1414,
                    dedicated=0, shared=0, software=True)
    report = gpu.DeviceReport((warp,))
    assert report.software_only is True
    assert report.hardware is None


def test_choose_prefers_hardware_but_never_warp():
    report = gpu.DeviceReport((_adapter(),))
    assert gpu.choose("auto", report, True).state == "gpu"
    assert gpu.choose("auto", report, True).use_dml is True
    assert gpu.choose("gpu", report, True).state == "gpu"
    assert gpu.choose("cpu", report, True).state == "cpu"
    assert gpu.choose("cpu", report, True).use_dml is False

    warp = gpu.DeviceReport((_adapter(
        name="Microsoft Basic Render Driver", vendor=0x1414,
        dedicated=0, shared=0, software=True,
    ),))
    assert gpu.choose("auto", warp, True).state == "warp"
    assert gpu.choose("auto", warp, True).use_dml is False
    assert gpu.choose("gpu", warp, True).state == "unavailable"


def test_choose_without_directml_falls_back():
    report = gpu.DeviceReport((_adapter(),))
    assert gpu.choose("auto", report, False).state == "cpu"
    assert gpu.choose("gpu", report, False).state == "unavailable"
    assert gpu.choose("cpu", report, False).state == "cpu"


def test_session_providers_cpu_never_requests_directml():
    assert gpu.session_providers("cpu") == ["CPUExecutionProvider"]


def test_dml_targets_the_adapter_shown_in_settings(monkeypatch):
    report = gpu.DeviceReport((_adapter(index=1),))
    monkeypatch.setattr(gpu, "inspect", lambda: report)
    monkeypatch.setattr(gpu, "dml_available", lambda: True)
    assert gpu.session_providers("auto") == [
        "DmlExecutionProvider", "CPUExecutionProvider",
    ]
    assert gpu.dml_device_id("auto") == 1
    assert gpu.dml_device_id("gpu") == 1
    assert gpu.dml_device_id("cpu") == 0


def test_config_validates_ai_device(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"ai_device": "gpu"}), encoding="utf-8")
    assert Config.load(path).ai_device == "gpu"

    path.write_text(json.dumps({"ai_device": "vulkan"}), encoding="utf-8")
    assert Config.load(path).ai_device == "auto"

    cfg = Config()
    cfg.save(path)
    assert Config.load(path).ai_device == "auto"


def test_settings_device_segment_saves_and_resets(qt_app, tr, monkeypatch):
    assert qt_app is not None
    cfg = Config()
    dlg = SettingsDialog(cfg, tr, None, tokens=LIGHT, variant="settings")
    assert dlg._device_seg.value() == "auto"

    dlg._device_seg.set_value("cpu")
    dlg._on_device_changed("cpu")
    dlg._save()
    assert cfg.ai_device == "cpu"

    def fake(*args, **kwargs):
        del args, kwargs
        return 0x4000  # QMessageBox.Yes

    monkeypatch.setattr(
        "mediafilter.ui.widgets.settings_dialog.message_box", fake,
    )
    dlg = SettingsDialog(cfg, tr, None, tokens=LIGHT, variant="settings")
    dlg._device_seg.set_value("gpu")
    dlg._device_setting = "gpu"
    dlg._reset_page()
    assert dlg._device_seg.value() == "auto"
    assert dlg._device_setting == "auto"


def test_settings_mode_cards_have_no_radio_dot(qt_app, tr):
    assert qt_app is not None
    cfg = Config()
    settings = SettingsDialog(cfg, tr, None, tokens=LIGHT, variant="settings")
    assert settings._mode_cards is not None
    assert all(card.dot is None for card in settings._mode_cards.cards.values())

    welcome = SettingsDialog(Config(), tr, None, tokens=LIGHT, variant="first_run")
    assert welcome._mode_cards is not None
    assert all(card.dot is not None for card in welcome._mode_cards.cards.values())