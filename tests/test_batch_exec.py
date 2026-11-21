"""Batch execution tests: process loop, safety, fallback and cancellation."""

from __future__ import annotations

import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

from mediafilter.core import batch
from mediafilter.core.batch_exec import (
    BatchExecutor,
    BuildSpec,
    ExecutorHooks,
    Job,
)


def _quote(value: str | Path) -> str:
    return f'"{value}"'


def _custom_spec(script: Path) -> BuildSpec:
    """A custom command that runs a Python helper instead of ffmpeg."""
    template = (
        f"{_quote(sys.executable)} {_quote(script)} "
        "{input} {output}"
    )
    return BuildSpec(ffmpeg="ffmpeg", task="custom", template=template)


def _write_script(tmp_path: Path, body: str) -> Path:
    script = tmp_path / "fake_ffmpeg.py"
    script.write_text(textwrap.dedent(body), encoding="utf-8")
    return script


def _job(source: Path, target: Path, duration: float = 0.0) -> Job:
    source.write_bytes(b"input-bytes")
    return Job(source, target, duration=duration)


def test_jobs_publish_atomically_and_report_sizes(tmp_path: Path):
    script = _write_script(tmp_path, """
        import sys, pathlib
        source, target = sys.argv[1], sys.argv[2]
        print("out_time=00:00:01.000000", flush=True)
        print("speed=1.5x", flush=True)
        print("progress=continue", flush=True)
        pathlib.Path(target).write_bytes(b"converted!")
    """)
    source = tmp_path / "clip.mp4"
    job = _job(source, tmp_path / "clip_out.mp4", duration=2.0)
    spec = _custom_spec(script)

    progress: list[tuple[int, float, float, float | None]] = []
    executor = BatchExecutor([job], spec)
    summary = executor.run(ExecutorHooks(
        on_progress=lambda i, o, p, s: progress.append((i, o, p, s)),
    ))

    assert summary.succeeded == 1 and not summary.cancelled
    assert job.target.read_bytes() == b"converted!"
    assert summary.results[0].output_bytes == len(b"converted!")
    assert summary.results[0].input_bytes == len(b"input-bytes")
    assert progress and progress[0][2] == 50.0
    assert any(sample[3] == 1.5 for sample in progress)
    # No temp sibling left behind.
    assert not any(p.name.endswith(".part.mp4") for p in tmp_path.iterdir())


def test_failure_keeps_existing_target_untouched(tmp_path: Path):
    script = _write_script(tmp_path, """
        import sys
        print("boom: encoder exploded", file=sys.stderr, flush=True)
        sys.exit(3)
    """)
    source = tmp_path / "clip.mp4"
    target = tmp_path / "clip_out.mp4"
    target.write_bytes(b"original")
    job = _job(source, target)
    executor = BatchExecutor([job], _custom_spec(script))
    summary = executor.run()

    assert summary.failed == 1
    assert target.read_bytes() == b"original"
    result = summary.results[0]
    assert "boom" in result.message
    assert not any(p.name.endswith(".part.mp4") for p in tmp_path.iterdir())


def test_stop_policy_halts_after_the_first_failure(tmp_path: Path):
    script = _write_script(tmp_path, "import sys; sys.exit(2)")
    jobs = [
        Job(tmp_path / "a.mp4", tmp_path / "a_out.mp4"),
        Job(tmp_path / "b.mp4", tmp_path / "b_out.mp4"),
    ]
    for job in jobs:
        job.source.write_bytes(b"x")
    summary = BatchExecutor(jobs, _custom_spec(script), failure="stop").run()
    assert summary.failed == 1
    assert len(summary.results) == 1


def test_continue_policy_runs_every_job(tmp_path: Path):
    script = _write_script(tmp_path, "import sys; sys.exit(2)")
    jobs = [
        Job(tmp_path / "a.mp4", tmp_path / "a_out.mp4"),
        Job(tmp_path / "b.mp4", tmp_path / "b_out.mp4"),
    ]
    for job in jobs:
        job.source.write_bytes(b"x")
    summary = BatchExecutor(jobs, _custom_spec(script), failure="continue").run()
    assert summary.failed == 2
    assert len(summary.results) == 2


def test_skipped_jobs_are_recorded_without_running(tmp_path: Path):
    script = _write_script(tmp_path, "raise SystemExit('must not run')")
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"x")
    job = Job(source, tmp_path / "clip_out.mp4", skipped=True, skip_reason="exists")
    summary = BatchExecutor([job], _custom_spec(script)).run()
    assert summary.skipped == 1
    assert summary.results[0].message == "exists"
    assert not job.target.exists()


def test_cancel_terminates_the_running_process(tmp_path: Path):
    script = _write_script(tmp_path, """
        import sys, time
        print("out_time=00:00:00.500000", flush=True)
        time.sleep(30)
        open(sys.argv[2], "wb").write(b"late")
    """)
    source = tmp_path / "clip.mp4"
    job = _job(source, tmp_path / "clip_out.mp4", duration=10.0)
    executor = BatchExecutor([job], _custom_spec(script))
    started = threading.Event()
    summary_box: list = []

    def run():
        summary_box.append(executor.run(ExecutorHooks(
            on_start=lambda index, item: started.set(),
        )))

    thread = threading.Thread(target=run)
    thread.start()
    assert started.wait(5)
    time.sleep(0.2)
    begin = time.monotonic()
    executor.cancel()
    thread.join(10)
    elapsed = time.monotonic() - begin

    assert not thread.is_alive()
    summary = summary_box[0]
    assert summary.cancelled
    assert summary.results[0].status == "cancelled"
    assert elapsed < 5
    assert not job.target.exists()


def test_hardware_failure_retries_on_cpu(tmp_path: Path, monkeypatch):
    spec = BuildSpec(
        ffmpeg="ffmpeg", task="compress", encoder="nvenc_hevc",
        container="mp4", fallback=True,
    )
    jobs = [
        Job(tmp_path / "a.mp4", tmp_path / "a_out.mp4"),
        Job(tmp_path / "b.mp4", tmp_path / "b_out.mp4"),
    ]
    for job in jobs:
        job.source.write_bytes(b"x")

    calls: list[list[str]] = []

    def fake_run(self, command, index, hooks, finished, total, weight, duration):
        calls.append(list(command))
        if "hevc_nvenc" in command:
            return 1, False, "Cannot load nvcuda.dll", None
        Path(command[-1]).write_bytes(b"cpu-result")
        return 0, False, "", None

    monkeypatch.setattr(BatchExecutor, "_run_process", fake_run)
    summary = BatchExecutor(jobs, spec).run()

    assert summary.succeeded == 2
    assert all(result.fallback for result in summary.results)
    assert len(calls) == 4
    assert all("libx265" in call for call in calls[1::2])
    assert jobs[0].target.read_bytes() == b"cpu-result"


def test_no_fallback_for_webm_or_remux(tmp_path: Path):
    webm = BuildSpec(ffmpeg="ffmpeg", encoder="nvenc_hevc", container="webm")
    assert webm.fallback_encoder() is None
    avi = BuildSpec(ffmpeg="ffmpeg", encoder="nvenc_h264", container="avi")
    assert avi.fallback_encoder() == "x264"
    remux = BuildSpec(ffmpeg="ffmpeg", task="remux", encoder="nvenc_hevc")
    assert remux.fallback_encoder() is None
    cpu = BuildSpec(ffmpeg="ffmpeg", encoder="x265")
    assert cpu.fallback_encoder() is None


def test_preview_has_no_runtime_progress_flags(tmp_path: Path):
    spec = BuildSpec(ffmpeg="ffmpeg", task="compress", encoder="x265")
    text = spec.preview("in.mp4", "out.mp4")
    assert "-progress" not in text
    assert "libx265" in text
    assert text.rstrip().endswith('"out.mp4"') or text.rstrip().endswith("out.mp4")