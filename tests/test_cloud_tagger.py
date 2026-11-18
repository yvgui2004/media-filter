"""Cloud tagger: closed-set parsing, voting, hybrid merge and cache identity."""

from __future__ import annotations

import threading
from types import SimpleNamespace
from typing import Any, cast

import pytest
from PySide6.QtWidgets import QApplication

from mediafilter.core import cloud_tagger
from mediafilter.core.cloud_tagger import (
    CloudTagConfig, build_messages, cloud_model_id, cloud_tag_video, parse_labels,
)
from mediafilter.core.tagger import TagResult
from mediafilter.ui import cloud_tag_worker as worker_module
from mediafilter.ui.cloud_tag_worker import CloudTagWorker

ALLOWED = ["人物", "屏幕", "游戏"]
CONFIG = CloudTagConfig(
    base_url="https://example.test/v1",
    api_key="sk-test-secret",
    model="vision-test",
    labels=ALLOWED,
)


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def fake_frames(monkeypatch):
    monkeypatch.setattr(cloud_tagger, "extract_jpeg", lambda *_a, **_k: b"\xff\xd8jpeg")
    answers: list[str] = []

    def fake_chat(*_args, **_kwargs) -> str:
        return answers.pop(0)

    monkeypatch.setattr(cloud_tagger, "chat_completion", fake_chat)
    return answers


def test_parse_labels_keeps_only_allowed_and_handles_shapes():
    assert parse_labels('{"labels": ["人物", "编的标签"]}', ALLOWED) == ["人物"]
    assert parse_labels('```json\n{"tags": ["屏幕"]}\n```', ALLOWED) == ["屏幕"]
    assert parse_labels('["游戏", "人物"]', ALLOWED) == ["人物", "游戏"]
    assert parse_labels("我觉得有个人", ALLOWED) == []
    assert parse_labels('{"labels": ["屏幕", "屏幕"]}', ALLOWED) == ["屏幕"]


def test_build_messages_lists_every_allowed_label_and_the_image():
    messages = build_messages(ALLOWED, "data:image/jpeg;base64,AAAA")
    text = messages[1]["content"][0]["text"]
    for label in ALLOWED:
        assert f"- {label}" in text
    assert messages[1]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_cloud_tag_video_votes_across_frames(fake_frames):
    fake_frames.extend([
        '{"labels": ["人物"]}',
        '{"labels": ["人物", "屏幕"]}',
        '{"labels": ["屏幕"]}',
    ])
    result = cloud_tag_video("ffmpeg", "a.mp4", 30.0, CONFIG, sample_count=3)
    assert result.error is None
    assert result.frames == 3
    assert result.tags == ["人物", "屏幕"]     # seen in 2 of 3 frames
    assert "游戏" not in result.tags


def test_cloud_tag_video_reports_first_error_when_every_frame_fails(monkeypatch):
    from mediafilter.core.cloud_models import CloudModelError

    monkeypatch.setattr(cloud_tagger, "extract_jpeg", lambda *_a, **_k: b"\xff\xd8jpeg")

    def boom(*_args, **_kwargs):
        raise CloudModelError("HTTP 401：invalid key")

    monkeypatch.setattr(cloud_tagger, "chat_completion", boom)
    result = cloud_tag_video("ffmpeg", "a.mp4", 30.0, CONFIG, sample_count=2)
    assert result.error == "HTTP 401：invalid key"
    assert result.tags == []


def test_cloud_tag_video_stops_on_cancel():
    event = threading.Event()
    event.set()
    result = cloud_tag_video(
        "ffmpeg", "a.mp4", 30.0, CONFIG, sample_count=3, cancel_event=event,
    )
    assert result.tags == []
    assert result.error is None


def test_cloud_model_id_changes_with_mode_endpoint_and_labels():
    base = cloud_model_id("cloud", CONFIG.base_url, CONFIG.model, ALLOWED)
    assert base != cloud_model_id("hybrid", CONFIG.base_url, CONFIG.model, ALLOWED)
    assert base != cloud_model_id("cloud", "https://other.test/v1", CONFIG.model, ALLOWED)
    assert base != cloud_model_id("cloud", CONFIG.base_url, CONFIG.model, ["人物"])


def _record():
    return SimpleNamespace(path="a.mp4", duration=30.0, mtime=1.0, size=100)


def _worker(qt_app, monkeypatch, *, local_tags, cloud, upload_only=True):
    calls: list[str] = []
    monkeypatch.setattr(
        worker_module, "tag_media",
        lambda *_a, **_k: TagResult(tags=local_tags, frames=3, detections=len(local_tags)),
    )

    def fake_cloud(*_a, **_k):
        calls.append("cloud")
        return cloud

    monkeypatch.setattr(worker_module, "cloud_tag_video", fake_cloud)
    assert qt_app is not None
    worker = CloudTagWorker(
        [_record()], "ffmpeg", CONFIG, mode="hybrid",
        custom_labels=["游戏"], sample_frames=3, threads=1,
        local_model_path="model.onnx", upload_target_only=upload_only,
    )
    return worker, calls


def test_hybrid_merges_local_tags_with_cloud_custom_labels(qt_app, monkeypatch):
    worker, calls = _worker(
        qt_app, monkeypatch, local_tags=["人物"], cloud=TagResult(tags=["游戏"], frames=3),
    )
    result = worker._tag_one(cast(Any, object()), _record())     # detector only passed through
    assert calls == ["cloud"]
    assert result.tags == ["人物", "游戏"]
    assert result.error is None


def test_hybrid_skips_upload_when_local_found_nothing(qt_app, monkeypatch):
    worker, calls = _worker(
        qt_app, monkeypatch, local_tags=[], cloud=TagResult(tags=["游戏"]),
    )
    result = worker._tag_one(cast(Any, object()), _record())
    assert calls == []
    assert result.tags == []


def test_hybrid_keeps_local_tags_when_cloud_fails(qt_app, monkeypatch):
    worker, calls = _worker(
        qt_app, monkeypatch, local_tags=["人物"],
        cloud=TagResult(tags=[], error="HTTP 401：invalid key"),
    )
    result = worker._tag_one(cast(Any, object()), _record())
    assert calls == ["cloud"]
    assert result.tags == ["人物"]
    assert result.error == "HTTP 401：invalid key"


def test_worker_applies_the_frame_policy_to_both_passes(qt_app, monkeypatch):
    counts: list[int] = []

    def fake_local(*_args, **kwargs):
        counts.append(kwargs["sample_count"])
        return TagResult(tags=["人物"], frames=kwargs["sample_count"])

    def fake_cloud(*_args, **kwargs):
        counts.append(kwargs["sample_count"])
        return TagResult(tags=["游戏"], frames=kwargs["sample_count"])

    monkeypatch.setattr(worker_module, "tag_media", fake_local)
    monkeypatch.setattr(worker_module, "cloud_tag_video", fake_cloud)
    assert qt_app is not None
    worker = CloudTagWorker(
        [_record()], "ffmpeg", CONFIG, mode="hybrid",
        custom_labels=["游戏"], frame_policy="fast", threads=1,
        local_model_path="model.onnx",
    )
    result = worker._tag_one(cast(Any, object()), _record())
    assert counts == [4, 4]
    assert result.tags == ["人物", "游戏"]