import json
import os
import threading
import time

import pytest

from mediafilter.core.probe import ProbeCancelled, ProbeError, parse_probe_json, probe_file

VIDEO_JSON = {
    "streams": [
        {"codec_type": "video", "bit_rate": "2500000"},
        {"codec_type": "audio", "bit_rate": "128000"},
    ],
    "format": {"duration": "3721.5", "bit_rate": "2632000"},
}


def test_parses_video_and_audio_bitrates():
    meta = parse_probe_json(json.dumps(VIDEO_JSON))
    assert meta.duration == pytest.approx(3721.5)
    assert meta.video_bitrate == 2_500_000
    assert meta.audio_bitrate == 128_000
    assert meta.has_video is True


def test_audio_only_is_not_mistaken_for_a_video():
    data = {
        "streams": [{"codec_type": "audio", "bit_rate": "128000"}],
        "format": {"duration": "10.0", "bit_rate": "128500"},
    }
    meta = parse_probe_json(json.dumps(data))
    assert meta.has_video is False
    # The container-rate fallback must not invent a video stream for audio.
    assert meta.video_bitrate == 0
    assert meta.audio_bitrate == 128_000


def test_container_bitrate_used_when_stream_has_none():
    data = {
        "streams": [
            {"codec_type": "video", "bit_rate": "0"},
            {"codec_type": "audio", "bit_rate": "96000"},
        ],
        "format": {"duration": "10.0", "bit_rate": "1500000"},
    }
    meta = parse_probe_json(json.dumps(data))
    assert meta.video_bitrate == 1_500_000 - 96_000


def test_zero_defaults_on_missing_fields():
    meta = parse_probe_json(json.dumps({"format": {}}))
    assert meta.duration == 0.0
    assert meta.video_bitrate == 0
    assert meta.audio_bitrate == 0


def test_invalid_json_raises():
    with pytest.raises(ProbeError):
        parse_probe_json("not json")


def test_portable_dirs_only_when_frozen(monkeypatch, tmp_path):
    import mediafilter.core.probe as probe

    monkeypatch.delattr(probe.sys, "frozen", raising=False)
    assert probe._portable_dirs() == []

    monkeypatch.setattr(probe.sys, "frozen", True, raising=False)
    monkeypatch.setattr(probe.sys, "executable", str(tmp_path / "MediaFilter.exe"))
    dirs = probe._portable_dirs()
    assert tmp_path in dirs
    assert tmp_path / "ffmpeg" / "bin" in dirs


@pytest.mark.skipif(os.name != "nt", reason="uses a .cmd wrapper")
def test_cancel_kills_a_slow_ffprobe_quickly(tmp_path):
    fake = tmp_path / "slow.cmd"
    fake.write_text("@echo off\r\nping -n 6 127.0.0.1 >nul\r\n", encoding="ascii")
    cancel = threading.Event()
    threading.Timer(0.3, cancel.set).start()

    started = time.monotonic()
    with pytest.raises(ProbeCancelled):
        probe_file(str(fake), "x.mp4", cancel_event=cancel)

    assert time.monotonic() - started < 2.0