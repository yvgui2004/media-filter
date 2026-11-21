"""Background AI tagging worker: cache lookup, frame sampling, inference."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ..core.color_tags import COLOR_PALETTE_VERSION
from ..core.sampling import normalize_policy, sample_count
from ..core.tag_cache import TagCache, cache_key
from ..core.tagger import Detector, TagResult, tag_media


class TagWorker(QThread):
    tagged = Signal(str, list, str)          # path, tags, error ("" on success)
    progress = Signal(int, int)
    finished_ok = Signal(int, int, int)      # total, tagged_ok, failed
    failed = Signal(str)

    def __init__(self, records, model_path: str | Path, ffmpeg_path: str,
                 sample_frames: int = 3, threads: int = 2, conf: float = 0.25,
                 frame_policy: str | None = None,
                 device: str = "auto",
                 enabled_tags: list[str] | None = None,
                 color_tags: bool = True,
                 cache_path: str | Path | None = None, parent=None):
        super().__init__(parent)
        self._records = list(records)
        self._model_path = Path(model_path)
        self._ffmpeg = ffmpeg_path
        self._sample = max(1, sample_frames)
        self._policy = normalize_policy(frame_policy)
        self._threads = max(1, threads)
        self._device = device
        self._conf = conf
        self._enabled = set(enabled_tags) if enabled_tags is not None else None
        self._color_tags = bool(color_tags)
        self._cache = TagCache(cache_path)
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        total = len(self._records)
        done = tagged_ok = failed = 0
        try:
            if not self._model_path.is_file():
                raise FileNotFoundError(f"model not found: {self._model_path}")
            model_id = f"{self._model_path.name}:{self._model_path.stat().st_size}"
            if self._policy is not None:
                model_id += f"|frames:{self._policy}"
            if self._enabled is not None:
                model_id += "|tags:" + ",".join(sorted(self._enabled))
            model_id += (
                f"|color:{int(self._color_tags)}"
                f"|palette:{COLOR_PALETTE_VERSION}"
            )
            pending = []
            for rec in self._records:
                if self._cancel.is_set():
                    break
                key = cache_key(rec.path, rec.mtime, rec.size, model_id)
                cached = self._cache.get(key)
                if cached is not None:
                    done += 1
                    tagged_ok += 1
                    self.tagged.emit(str(rec.path), cached, "")
                    self.progress.emit(done, total)
                else:
                    pending.append((rec, key))

            if pending and not self._cancel.is_set():
                detector = Detector(
                    self._model_path, threads=self._threads,
                    conf=self._conf, device=self._device,
                )
                with ThreadPoolExecutor(max_workers=self._threads) as pool:
                    futures = {
                        pool.submit(self._tag_one, detector, rec): (rec, key)
                        for rec, key in pending
                    }
                    for future in as_completed(futures):
                        rec, key = futures[future]
                        if self._cancel.is_set():
                            continue
                        try:
                            result: TagResult = future.result()
                        except Exception as exc:      # one bad file must not kill the batch
                            result = TagResult(error=f"{type(exc).__name__}: {exc}")
                        done += 1
                        if result.error:
                            failed += 1
                            self.tagged.emit(str(rec.path), [], result.error)
                        else:
                            tagged_ok += 1
                            self._cache.put(key, result.tags)
                            self.tagged.emit(str(rec.path), result.tags, "")
                        self.progress.emit(done, total)
                    for f in futures:
                        f.cancel()
            self._cache.save()
            self.finished_ok.emit(total, tagged_ok, failed)
        except Exception as exc:                      # model missing / ORT not installed
            self.failed.emit(f"{type(exc).__name__}: {exc}")

    def _tag_one(self, detector: Detector, rec) -> TagResult:
        if rec.duration <= 0:
            return TagResult(error="duration unknown")
        count = (
            sample_count(self._policy, rec.duration)
            if self._policy is not None
            else self._sample
        )
        return tag_media(
            detector, self._ffmpeg, rec.path, rec.duration,
            sample_count=count, cancel_event=self._cancel,
            enabled_tags=self._enabled,
            color_tags_enabled=self._color_tags,
        )