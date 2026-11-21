"""Tests for the batch model: catalogue, command building, planning, probe."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from mediafilter.core import batch


# -- catalogue -------------------------------------------------------------


def test_every_encoder_is_well_formed():
    assert set(batch.ENCODERS) == {
        "nvenc_hevc", "nvenc_h264", "nvenc_av1",
        "amf_hevc", "amf_h264", "amf_av1",
        "x265", "x264",
    }
    for key, spec in batch.ENCODERS.items():
        assert spec.key == key
        assert len(spec.tiers) == 3
        assert spec.tiers == tuple(sorted(spec.tiers))
        assert "mp4" in spec.containers
        assert spec.video_args


def test_encoder_groups_cover_the_catalogue():
    grouped = [key for _family, keys in batch.ENCODER_GROUPS for key in keys]
    assert sorted(grouped) == sorted(batch.ENCODERS)
    assert len(grouped) == len(set(grouped))


def test_quality_value_uses_tier_and_custom_override():
    assert batch.quality_value("x265", "high") == 20
    assert batch.quality_value("x265", "balanced") == 23
    assert batch.quality_value("x265", "small") == 26
    assert batch.quality_value("nvenc_h264", "balanced") == 23
    assert batch.quality_value("x265", "balanced", "19") == 19
    assert batch.quality_value("x265", "balanced", 18) == 18
    assert batch.quality_text("nvenc_hevc", "balanced") == "CQ 23"


def test_auto_prefers_hardware_hevc_then_cpu():
    assert batch.auto_encoder({"nvenc_hevc": True, "x265": True}) == "nvenc_hevc"
    assert batch.auto_encoder({"nvenc_hevc": False, "amf_hevc": True}) == "amf_hevc"
    assert batch.auto_encoder({"nvenc_h264": True, "amf_hevc": False}) == "nvenc_h264"
    assert batch.auto_encoder({"x265": True}) == "x265"
    # Unknown availability still resolves to something usable.
    assert batch.auto_encoder() in batch.ENCODERS


def test_resolve_encoder_falls_back_when_requested_is_missing():
    available = {"nvenc_hevc": True, "x265": True}
    assert batch.resolve_encoder("auto", available) == "nvenc_hevc"
    assert batch.resolve_encoder("x265", available) == "x265"
    assert batch.resolve_encoder("amf_av1", available) == "nvenc_hevc"
    with pytest.raises(ValueError):
        batch.resolve_encoder("nope", available)


def test_containers_follow_the_encoder():
    assert batch.containers_for("remux") == batch.ALL_CONTAINERS
    assert batch.containers_for("custom")[0] == batch.ORIGINAL
    assert "webm" in batch.containers_for("compress", "nvenc_av1")
    assert "webm" not in batch.containers_for("compress", "x265")
    assert batch.default_container("compress", "x265") == "mp4"
    assert batch.default_container("custom") == batch.ORIGINAL


# -- stream policies -------------------------------------------------------


def test_audio_policy():
    assert batch.audio_args("smart", "mp4") == ["-c:a", "copy"]
    assert batch.audio_args("aac", "mp4") == ["-c:a", "aac", "-b:a", "128k"]
    assert batch.audio_args("aac", "webm") == ["-c:a", "libopus", "-b:a", "128k"]
    assert batch.audio_args("remove", "mkv") == ["-an"]


def test_subtitle_policy_per_container():
    assert batch.subtitle_args("smart", "mp4") == ["-c:s", "mov_text"]
    assert batch.subtitle_args("smart", "mkv") == ["-c:s", "copy"]
    assert batch.subtitle_args("smart", "webm") == ["-c:s", "webvtt"]
    assert batch.subtitle_args("smart", "avi") == ["-sn"]
    assert batch.subtitle_args("remove", "mkv") == ["-sn"]
    assert batch.subtitle_effect("smart", "flv") == "dropped"
    assert batch.subtitle_effect("remove", "mp4") == "remove"


def test_container_helpers():
    assert batch.faststart_args("mp4") == ["-movflags", "+faststart"]
    assert batch.faststart_args("mkv") == []
    assert batch.attachment_args("mkv") == ["-map", "0:t?", "-c:t", "copy"]
    assert batch.attachment_args("mp4") == []


# -- command building ------------------------------------------------------


def test_compress_command_contains_encoder_and_policies():
    argv = batch.build_command(
        "ffmpeg", "D:/in/clip.mkv", "D:/out/clip_compressed.mp4",
        task="compress", encoder_key="nvenc_hevc", container="mp4",
        quality_tier="balanced", audio="aac", subtitles="smart", metadata=True,
    )
    assert isinstance(argv, list)
    assert argv[0] == "ffmpeg"
    assert "hevc_nvenc" in argv
    assert argv[argv.index("-cq") + 1] == "23"
    assert argv[argv.index("-preset") + 1] == "p7"
    assert ["-tag:v", "hvc1"] == argv[argv.index("-tag:v"):argv.index("-tag:v") + 2]
    assert ["-c:a", "aac"] == argv[argv.index("-c:a"):argv.index("-c:a") + 2]
    assert ["-c:s", "mov_text"] == argv[argv.index("-c:s"):argv.index("-c:s") + 2]
    assert ["-movflags", "+faststart"] == argv[argv.index("-movflags"):argv.index("-movflags") + 2]
    assert argv[-1] == "D:/out/clip_compressed.mp4"


def test_remux_copies_video_and_maps_streams():
    argv = batch.build_command(
        "ffmpeg", "in.mkv", "out.mp4",
        task="remux", container="mp4", audio="copy", subtitles="remove",
    )
    assert isinstance(argv, list)
    assert argv[argv.index("-c:v") + 1] == "copy"
    assert "-an" not in argv
    assert ["-map", "0:V:0"] == argv[argv.index("-map"):argv.index("-map") + 2]
    assert "-sn" in argv
    assert "libx265" not in argv


def test_remux_keeps_source_container_when_original():
    argv = batch.build_command(
        "ffmpeg", "in.webm", "out.webm", task="remux", container="original",
    )
    assert isinstance(argv, list)
    assert argv[-1] == "out.webm"
    assert "libopus" not in argv


def test_custom_command_is_a_string_with_substitutions():
    command = batch.build_command(
        "ffmpeg", "D:/in clip.mp4", "D:/out.mp4",
        task="custom",
        template='ffmpeg -i "{input}" -c:v libx264 -crf 24 "{output}"',
    )
    assert isinstance(command, str)
    assert command == (
        'ffmpeg -i "D:/in clip.mp4" -c:v libx264 -crf 24 "D:/out.mp4"'
    )
    with pytest.raises(ValueError):
        batch.build_command("ffmpeg", "a", "b", task="custom", template="   ")


def test_runtime_flags_are_added_for_builtin_commands():
    argv = batch.build_command(
        "ffmpeg", "in.mp4", "out.mp4", task="compress", encoder_key="x265",
        container="mp4", runtime=True,
    )
    assert isinstance(argv, list)
    assert "-progress" in argv
    assert argv[argv.index("-progress") + 1] == "pipe:1"
    assert "-nostats" in argv
    assert "-nostdin" in argv
    assert argv[-1] == "out.mp4"


def test_display_command_quotes_paths_with_spaces():
    argv = batch.build_command(
        "ffmpeg", "D:/my videos/in.mp4", "D:/my videos/out.mp4",
        task="compress", encoder_key="x264", container="mp4",
    )
    text = batch.display_command(argv)
    assert '"D:/my videos/in.mp4"' in text
    assert text.startswith("ffmpeg ")


def test_batch_file_text_escapes_percent_and_uses_crlf():
    text = batch.batch_file_text(["ffmpeg -i \"100%.mp4\" out.mp4"], pause=False)
    assert text.startswith("@echo off\r\n")
    assert "100%%.mp4" in text
    assert text.endswith("\r\n")


# -- output planning -------------------------------------------------------


def test_plan_outputs_defaults_to_sibling_with_suffix(tmp_path: Path):
    source = tmp_path / "clip.mkv"
    source.write_bytes(b"x")
    plans = batch.plan_outputs([source], suffix="_compressed", extension="mp4")
    assert plans[0].ok
    assert plans[0].target == tmp_path / "clip_compressed.mp4"


def test_plan_outputs_honours_output_folder(tmp_path: Path):
    source = tmp_path / "clip.mkv"
    source.write_bytes(b"x")
    folder = tmp_path / "exports"
    plans = batch.plan_outputs(
        [source], folder=folder, suffix="_out", extension="mkv",
    )
    assert plans[0].target == folder / "clip_out.mkv"


def test_plan_outputs_numbers_existing_files(tmp_path: Path):
    source = tmp_path / "clip.mkv"
    source.write_bytes(b"x")
    (tmp_path / "clip_out.mp4").write_bytes(b"old")
    plans = batch.plan_outputs(
        [source], suffix="_out", extension="mp4", conflict="number",
    )
    assert plans[0].target.name == "clip_out (2).mp4"


def test_plan_outputs_skip_policy_marks_existing(tmp_path: Path):
    source = tmp_path / "clip.mkv"
    source.write_bytes(b"x")
    (tmp_path / "clip_out.mp4").write_bytes(b"old")
    plans = batch.plan_outputs(
        [source], suffix="_out", extension="mp4", conflict="skip",
    )
    assert plans[0].skipped and plans[0].reason == "exists"


def test_plan_outputs_prevents_collisions_inside_the_batch(tmp_path: Path):
    first = tmp_path / "one" / "a.mkv"
    second = tmp_path / "two" / "a.mkv"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(b"x")
    second.write_bytes(b"x")
    out = tmp_path / "out"
    plans = batch.plan_outputs(
        [first, second], folder=out, suffix="", extension="mp4", conflict="number",
    )
    assert plans[0].target.name == "a.mp4"
    assert plans[1].target.name == "a (2).mp4"


def test_plan_outputs_never_overwrites_an_input_even_in_overwrite_mode(tmp_path: Path):
    first = tmp_path / "a.mkv"
    second = tmp_path / "a_out.mp4"
    first.write_bytes(b"x")
    second.write_bytes(b"x")
    plans = batch.plan_outputs(
        [first, second], suffix="_out", extension="mp4", conflict="overwrite",
    )
    assert plans[0].skipped and plans[0].reason == "input"
    assert plans[1].target == tmp_path / "a_out_out.mp4"


def test_plan_outputs_rejects_same_path(tmp_path: Path):
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"x")
    plans = batch.plan_outputs(
        [source], suffix="", extension="mp4", conflict="overwrite",
    )
    assert plans[0].skipped and plans[0].reason == "same"


def test_temp_output_keeps_extension_and_is_hidden(tmp_path: Path):
    temp = batch.temp_output_path(tmp_path / "clip.mp4")
    assert temp.parent == tmp_path
    assert temp.name.startswith(".clip.")
    assert temp.name.endswith(".part.mp4")
    assert temp != tmp_path / "clip.mp4"


def test_publish_temp_replaces_atomically(tmp_path: Path):
    target = tmp_path / "clip.mp4"
    target.write_bytes(b"old")
    temp = batch.temp_output_path(target)
    temp.write_bytes(b"new")
    batch.publish_temp(temp, target)
    assert target.read_bytes() == b"new"
    assert not temp.exists()
    batch.discard_temp(temp)  # missing file is a no-op


# -- progress --------------------------------------------------------------


def test_parse_progress_time_and_speed():
    sample = batch.parse_progress_line("out_time=00:00:04.033333")
    assert sample is not None and sample.out_time == pytest.approx(4.0333, abs=1e-3)
    sample = batch.parse_progress_line("speed=2.53x")
    assert sample is not None and sample.speed == pytest.approx(2.53)
    assert batch.parse_progress_line("speed=N/A") is None
    assert batch.parse_progress_line("frame=42") is None
    assert batch.parse_progress_line("") is None


def test_parse_progress_end():
    sample = batch.parse_progress_line("progress=end")
    assert sample is not None and sample.finished


def test_percent_done_clamps():
    assert batch.percent_done(5.0, 10.0) == 50.0
    assert batch.percent_done(15.0, 10.0) == 100.0
    assert batch.percent_done(-1.0, 10.0) == 0.0
    assert batch.percent_done(5.0, 0.0) is None
    assert batch.percent_done(None, 10.0) is None


# -- hardware probe --------------------------------------------------------


def _completed(code: int, stderr: bytes = b"") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(["ffmpeg"], code, stdout=b"", stderr=stderr)


@pytest.fixture(autouse=True)
def _fresh_probe_cache():
    batch.clear_probe_cache()
    yield
    batch.clear_probe_cache()


def test_probe_marks_missing_build_and_gpu(monkeypatch):
    monkeypatch.setattr(
        batch, "_available_encoders",
        lambda binary, timeout: {"hevc_nvenc", "h264_nvenc", "libx265"},
    )
    monkeypatch.setattr(batch, "_detected_vendors", lambda: {0x10DE})

    def fake_run(binary, args, timeout):
        assert "-encoders" not in args  # listing is mocked separately
        if "libx265" in args:
            return _completed(1, b"boom")
        return _completed(0)

    monkeypatch.setattr(batch, "_run_probe", fake_run)
    report = batch.probe_encoders("C:/ffmpeg/bin/ffmpeg.exe")

    assert report["nvenc_hevc"].available
    assert report["nvenc_h264"].available
    assert not report["nvenc_av1"].available
    assert report["nvenc_av1"].reason == batch.REASON_BUILD
    assert not report["x265"].available
    assert report["x265"].reason == batch.REASON_FAILED
    assert not report["amf_hevc"].available
    assert report["amf_hevc"].reason == batch.REASON_BUILD


def test_probe_reports_driver_failure_and_no_gpu(monkeypatch):
    monkeypatch.setattr(
        batch, "_available_encoders",
        lambda binary, timeout: {"hevc_nvenc", "h264_nvenc", "hevc_amf", "libx264"},
    )
    monkeypatch.setattr(batch, "_detected_vendors", lambda: {0x10DE})

    def fake_run(binary, args, timeout):
        if "hevc_nvenc" in args:
            return _completed(1, b"Cannot load nvcuda.dll")
        return _completed(0)

    monkeypatch.setattr(batch, "_run_probe", fake_run)
    report = batch.probe_encoders("ffmpeg")

    assert not report["nvenc_hevc"].available
    assert report["nvenc_hevc"].reason == batch.REASON_DRIVER
    assert report["nvenc_h264"].available
    # AMF is compiled in but no AMD adapter is present.
    assert not report["amf_hevc"].available
    assert report["amf_hevc"].reason == batch.REASON_NO_GPU


def test_probe_without_ffmpeg_reports_missing(monkeypatch):
    monkeypatch.setattr(batch, "find_ffmpeg", lambda: None)
    report = batch.probe_encoders(None)
    assert all(not item.available for item in report.values())
    assert {item.reason for item in report.values()} == {batch.REASON_FFMPEG}


def test_probe_results_are_cached(monkeypatch):
    calls = {"n": 0}

    def listed(binary, timeout):
        calls["n"] += 1
        return {"libx264"}

    monkeypatch.setattr(batch, "_available_encoders", listed)
    monkeypatch.setattr(batch, "_detected_vendors", lambda: set())
    monkeypatch.setattr(batch, "_run_probe", lambda *a, **k: _completed(0))

    batch.probe_encoders("ffmpeg")
    batch.probe_encoders("ffmpeg")
    assert calls["n"] == 1

    batch.probe_encoders("ffmpeg", refresh=True)
    assert calls["n"] == 2


def test_available_map_is_plain_booleans():
    report = {
        "x265": batch.Availability("x265", True),
        "x264": batch.Availability("x264", False, batch.REASON_BUILD),
    }
    assert batch.available_map(report) == {"x265": True, "x264": False}