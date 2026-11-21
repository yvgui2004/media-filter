"""Batch execution: run planned jobs sequentially with progress and safety.

The dialog wraps :class:`BatchExecutor` in a ``QThread``; keeping the loop
itself free of Qt means it can be tested directly.  Each job renders into a
temporary sibling file and is only published with :func:`os.replace` after a
clean exit, so cancelling or a failed GPU encode never damages an existing
file.
"""

from __future__ import annotations

import queue
import shlex
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

from . import batch
from .batch import Command

EventHook = Callable[..., None]


@dataclass(frozen=True)
class Job:
    """One source file and the final path it should land on."""

    source: Path
    target: Path
    duration: float = 0.0
    skipped: bool = False
    skip_reason: str = ""


@dataclass(frozen=True)
class BuildSpec:
    """Everything needed to turn (source, output) into an ffmpeg command."""

    ffmpeg: str
    task: str = "compress"
    encoder: str = "x265"
    container: str = "mp4"
    quality_tier: str = "balanced"
    quality: str | int | None = None
    preset: str = ""
    audio: str = "smart"
    subtitles: str = "smart"
    metadata: bool = True
    template: str = ""
    fallback: bool = True

    def command(
        self,
        source: str | Path,
        output: str | Path,
        *,
        encoder: str | None = None,
        runtime: bool = True,
    ) -> Command:
        return batch.build_command(
            self.ffmpeg,
            source,
            output,
            task=self.task,
            encoder_key=encoder or self.encoder,
            container=self.container,
            quality_tier=self.quality_tier,
            quality=self.quality,
            preset=self.preset,
            audio=self.audio,
            subtitles=self.subtitles,
            metadata=self.metadata,
            template=self.template,
            runtime=runtime,
        )

    def preview(self, source: str | Path, target: str | Path) -> str:
        return batch.display_command(self.command(source, target, runtime=False))

    def fallback_encoder(self) -> str | None:
        """CPU encoder to retry with, or None when a retry makes no sense.

        H.265 is the usual fallback; AVI/FLV cannot mux it, and WebM has no
        software encoder in our catalogue, so those containers stay as they are.
        """
        if not self.fallback or self.task != "compress":
            return None
        if not batch.encoder(self.encoder).hardware:
            return None
        ext = self.container.lower().lstrip(".")
        if ext == "webm":
            return None
        if ext in ("avi", "flv"):
            return "x264"
        return "x265"

    def fallback_command(self, source: str | Path, output: str | Path) -> Command | None:
        fallback = self.fallback_encoder()
        if not fallback:
            return None
        return self.command(source, output, encoder=fallback, runtime=True)


@dataclass
class JobResult:
    source: Path
    target: Path
    status: str                     # ok | failed | skipped | cancelled
    message: str = ""
    seconds: float = 0.0
    input_bytes: int = 0
    output_bytes: int = 0
    fallback: bool = False
    log_tail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"


@dataclass
class BatchSummary:
    results: list[JobResult] = field(default_factory=list)
    cancelled: bool = False
    elapsed: float = 0.0

    @property
    def succeeded(self) -> int:
        return sum(1 for item in self.results if item.status == "ok")

    @property
    def failed(self) -> int:
        return sum(1 for item in self.results if item.status == "failed")

    @property
    def skipped(self) -> int:
        return sum(1 for item in self.results if item.status == "skipped")

    @property
    def input_bytes(self) -> int:
        return sum(item.input_bytes for item in self.results)

    @property
    def output_bytes(self) -> int:
        return sum(item.output_bytes for item in self.results if item.status == "ok")

    @property
    def saved_ratio(self) -> float:
        if not self.input_bytes:
            return 0.0
        return max(0.0, 1.0 - self.output_bytes / self.input_bytes)


@dataclass
class ExecutorHooks:
    on_start: Callable[[int, Job], None] | None = None
    on_progress: Callable[[int, float, float, float | None], None] | None = None
    on_result: Callable[[int, JobResult], None] | None = None
    on_log: Callable[[str], None] | None = None


class BatchExecutor:
    """Sequential, cancellable execution of a list of :class:`Job`."""

    def __init__(
        self,
        jobs: Sequence[Job],
        spec: BuildSpec,
        *,
        failure: str = "continue",
    ):
        self._jobs = list(jobs)
        self._spec = spec
        self._failure = failure if failure in batch.FAILURE_MODES else "continue"
        self._cancel = threading.Event()
        self._proc: subprocess.Popen | None = None
        self._summary = BatchSummary()

    # -- public ---------------------------------------------------------

    def cancel(self) -> None:
        self._cancel.set()
        self._terminate()

    @property
    def summary(self) -> BatchSummary:
        return self._summary

    def run(self, hooks: ExecutorHooks | None = None) -> BatchSummary:
        hooks = hooks or ExecutorHooks()
        started = time.monotonic()
        weights = [max(job.duration, 1.0) for job in self._jobs]
        total_weight = sum(weights) or 1.0
        finished_weight = 0.0

        for index, job in enumerate(self._jobs):
            if self._cancel.is_set():
                self._summary.cancelled = True
                break

            input_size = _file_size(job.source)
            if job.skipped:
                result = JobResult(
                    job.source, job.target, "skipped",
                    message=job.skip_reason, input_bytes=input_size,
                )
                self._record(index, result, hooks)
                finished_weight += weights[index]
                continue

            if hooks.on_start:
                hooks.on_start(index, job)
            job_started = time.monotonic()
            result = self._run_job(
                index, job, hooks, finished_weight, total_weight, weights[index],
            )
            result.seconds = time.monotonic() - job_started
            result.input_bytes = input_size
            self._record(index, result, hooks)
            finished_weight += weights[index]

            if result.status == "cancelled":
                self._summary.cancelled = True
                break
            if result.status == "failed" and self._failure == "stop":
                break

        self._summary.elapsed = time.monotonic() - started
        return self._summary

    # -- one job --------------------------------------------------------

    def _run_job(
        self,
        index: int,
        job: Job,
        hooks: ExecutorHooks,
        finished_weight: float,
        total_weight: float,
        weight: float,
    ) -> JobResult:
        try:
            job.target.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return JobResult(job.source, job.target, "failed", str(exc))

        temp = batch.temp_output_path(job.target)
        command = self._spec.command(job.source, temp)
        code, cancelled, tail, _speed = self._run_process(
            command, index, hooks, finished_weight, total_weight,
            weight, job.duration,
        )

        if cancelled:
            batch.discard_temp(temp)
            return JobResult(job.source, job.target, "cancelled", log_tail=tail)

        used_fallback = False
        if code != 0:
            fallback = self._spec.fallback_command(job.source, temp)
            if not fallback:
                batch.discard_temp(temp)
                return JobResult(
                    job.source, job.target, "failed",
                    message=_first_error(tail) or f"ffmpeg exit {code}",
                    log_tail=tail,
                )
            if hooks.on_log:
                hooks.on_log(_fallback_message(job.target.name))
            batch.discard_temp(temp)
            code, cancelled, tail, _speed = self._run_process(
                fallback, index, hooks, finished_weight, total_weight,
                weight, job.duration,
            )
            used_fallback = True
            if cancelled:
                batch.discard_temp(temp)
                return JobResult(job.source, job.target, "cancelled", log_tail=tail)
            if code != 0:
                batch.discard_temp(temp)
                return JobResult(
                    job.source, job.target, "failed",
                    message=_first_error(tail) or f"ffmpeg exit {code}",
                    log_tail=tail, fallback=True,
                )

        if not temp.exists() or temp.stat().st_size == 0:
            batch.discard_temp(temp)
            return JobResult(
                job.source, job.target, "failed",
                message="no output written", log_tail=tail, fallback=used_fallback,
            )

        try:
            batch.publish_temp(temp, job.target)
        except OSError as exc:
            batch.discard_temp(temp)
            return JobResult(
                job.source, job.target, "failed", str(exc),
                log_tail=tail, fallback=used_fallback,
            )

        return JobResult(
            job.source, job.target, "ok",
            output_bytes=_file_size(job.target),
            fallback=used_fallback, log_tail=tail,
        )

    # -- process loop ---------------------------------------------------

    def _run_process(
        self,
        command: Command,
        index: int,
        hooks: ExecutorHooks,
        finished_weight: float,
        total_weight: float,
        weight: float,
        duration: float,
    ) -> tuple[int, bool, str, float | None]:
        argv = _command_argv(command)
        stderr_tail: deque[str] = deque(maxlen=40)
        stdout_queue: queue.Queue[str | None] = queue.Queue()

        try:
            proc = subprocess.Popen(
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                **batch.subprocess_kwargs(),
            )
        except OSError as exc:
            return -1, False, str(exc), None

        self._proc = proc
        readers = [
            _start_reader(proc.stdout, stdout_queue.put),
            _start_reader(proc.stderr, stderr_tail.append),
        ]
        speed: float | None = None
        last_time: float | None = None
        cancelled = False

        try:
            while True:
                line = _next_line(stdout_queue)
                if line is not None:
                    sample = batch.parse_progress_line(line)
                    if sample is None:
                        if line.strip():
                            stderr_tail.append(line.strip())
                    else:
                        if sample.out_time is not None:
                            last_time = sample.out_time
                        if sample.speed is not None:
                            speed = sample.speed
                        if (sample.cycle or sample.finished) and hooks.on_progress:
                            job_fraction = batch.percent_done(last_time, duration)
                            percent = job_fraction or 0.0
                            overall = (
                                finished_weight + weight * percent / 100.0
                            ) / total_weight
                            hooks.on_progress(index, overall * 100.0, percent, speed)
                if self._cancel.is_set():
                    cancelled = True
                    self._terminate()
                    break
                if line is None and proc.poll() is not None:
                    break
        finally:
            for reader in readers:
                reader.join(timeout=1.0)
            self._proc = None

        try:
            code = proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            code = proc.wait(timeout=5)
        return code, cancelled, "\n".join(stderr_tail), speed

    def _terminate(self) -> None:
        proc = self._proc
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            try:
                proc.kill()
            except OSError:
                pass

    # -- bookkeeping ----------------------------------------------------

    def _record(self, index: int, result: JobResult, hooks: ExecutorHooks) -> None:
        self._summary.results.append(result)
        if hooks.on_result:
            hooks.on_result(index, result)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _command_argv(command: Command) -> list[str] | str:
    if isinstance(command, str):
        if sys.platform == "win32":
            # CreateProcess parses the string itself; re-tokenising it would
            # break the quotes around paths the user typed.
            return command
        return shlex.split(command, posix=True)
    return command


def _start_reader(stream, sink: Callable[[str], None]) -> threading.Thread:
    def pump():
        if stream is None:
            return
        try:
            for line in stream:
                sink(line.rstrip("\r\n"))
        except (OSError, ValueError):
            pass
        finally:
            try:
                stream.close()
            except OSError:
                pass

    thread = threading.Thread(target=pump, daemon=True)
    thread.start()
    return thread


def _next_line(lines: queue.Queue) -> str | None:
    try:
        return lines.get(timeout=0.1)
    except queue.Empty:
        return None


def _file_size(path: str | Path) -> int:
    try:
        return Path(path).stat().st_size
    except OSError:
        return 0


def _first_error(tail: str) -> str:
    for line in reversed(tail.splitlines()):
        text = " ".join(line.split())
        if text:
            return text[:300]
    return ""


def _fallback_message(name: str) -> str:
    return f"{name}: hardware encoder failed, retrying on CPU"