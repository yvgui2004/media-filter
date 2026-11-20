"""The local worker honours the saved frame-intensity policy."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from PySide6.QtWidgets import QApplication

from mediafilter.core.tagger import TagResult
from mediafilter.ui import tag_worker as worker_module
from mediafilter.ui.tag_worker import TagWorker


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_local_worker_samples_each_video_by_policy(qt_app, tmp_path, monkeypatch):
    counts: list[int] = []

    def fake_tag(*_args, **kwargs):
        counts.append(kwargs["sample_count"])
        return TagResult(tags=["人物"], frames=kwargs["sample_count"])

    monkeypatch.setattr(worker_module, "tag_media", fake_tag)
    assert qt_app is not None
    worker = TagWorker(
        [], tmp_path / "model.onnx", "ffmpeg",
        frame_policy="fine", cache_path=tmp_path / "tags.json",
    )
    short = SimpleNamespace(path="a.mp4", duration=30.0, mtime=1.0, size=10)
    long = SimpleNamespace(path="b.mp4", duration=700.0, mtime=1.0, size=10)

    worker._tag_one(cast(Any, object()), short)
    worker._tag_one(cast(Any, object()), long)

    assert counts == [12, 16]


def test_local_worker_passes_the_enabled_palette(qt_app, tmp_path, monkeypatch):
    seen: list[set[str] | None] = []

    def fake_tag(*_args, **kwargs):
        seen.append(kwargs["enabled_tags"])
        return TagResult()

    monkeypatch.setattr(worker_module, "tag_media", fake_tag)
    worker = TagWorker(
        [], tmp_path / "model.onnx", "ffmpeg",
        enabled_tags=["person", "dog"], cache_path=tmp_path / "tags.json",
    )
    short = SimpleNamespace(path="a.mp4", duration=30.0, mtime=1.0, size=10)
    worker._tag_one(cast(Any, object()), short)

    assert seen == [{"person", "dog"}]


def test_missing_model_reports_failure_instead_of_raising(qt_app, tmp_path):
    worker = TagWorker(
        [], tmp_path / "missing.onnx", "ffmpeg",
        cache_path=tmp_path / "tags.json",
    )
    errors: list[str] = []
    worker.failed.connect(errors.append)

    worker.run()

    assert errors and "model not found" in errors[0]