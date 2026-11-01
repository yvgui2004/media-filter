import json

import pytest

from mediafilter.core.probe import MediaMetadata, parse_probe_json, ProbeError

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