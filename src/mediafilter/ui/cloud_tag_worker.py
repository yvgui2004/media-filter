"""Background cloud tagging worker.

Cloud mode sends sampled frames to the configured vision model. Hybrid mode
first runs the local ONNX tagger, keeps those labels, and only uploads when
the local pass found something (or when the user turned that filter off) —
the cloud then adds the user's custom labels. Same signals as ``TagWorker``
so the window can reuse its progress / cancel / error handling.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ..core.cloud_tagger import (
    CloudTagConfig, cloud_model_id, cloud_tag_video, safe_error,
)
from ..core.color_tags import COLOR_PALETTE_VERSION
from ..core.sampling import normalize_policy, sample_count
from ..core.tag_cache import TagCache, cache_key
from ..core.tagger import Detector, TagResult, tag_media


class CloudTagWorker(QThread):
    tagged = Signal(str, list, str)          # path, tags, error ("" on success)
    progress = Signal(int, int)
    finished_ok = Signal(int, int, int)      # total, tagged_ok, failed
    failed = Signal(str)

    def __init__(
        self,
        records,
        ffmpeg_path: str,
        config: CloudTagConfig,
        mode: str = "cloud",
        custom_labels: list[str] | None = None,
        sample_frames: int = 3,
        threads: int = 2,
        local_model_path: str | Path | None = None,
        upload_target_only: bool = True,
        frame_policy: str | None = None,
        device: str = "auto",
        enabled_tags: list[str] | None = None,
        color_tags: bool = True,
        cache_path: str | Path | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._records = list(records)
        self._ffmpeg = ffmpeg_path
        self._config = config
        self._mode = mode
        self._custom = list(custom_labels or [])
        self._sample = max(1, sample_frames)
        self._policy = normalize_policy(frame_policy)
        self._threads = max(1, threads)
        self._device = device
        self._enabled = set(enabled_tags) if enabled_tags is not None else None
        self._local_model = Path(local_model_path) if local_model_path else None
        self._upload_target_only = upload_target_only
        self._color_tags = bool(color_tags)
        self._cache = TagCache(cache_path)
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        total = len(self._records)
        done = tagged_ok = failed = 0
        try:
            model_id = cloud_model_id(
                self._mode, self._config.base_url,
                self._config.model, self._config.labels,
            )
            if self._local_model is not None:
                model_id += f"|{self._local_model.name}:{self._local_model.stat().st_size}"
            if self._policy is not None:
                model_id += f"|frames:{self._policy}"
            if self._enabled is not None:
                model_id += "|tags:" + ",".join(sorted(self._enabled))
            model_id += (
                f"|color:{int(self._color_tags)}"
                f"|palette:{COLOR_PALETTE_VERSION}"
            )
            detector = None
            if self._mode == "hybrid":
                if self._local_model is None or not self._local_model.is_file():
                    raise RuntimeError("混合模式需要本地 ONNX 模型")
                detector = Detector(
                    self._local_model, threads=self._threads,
                    device=self._device,
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
                workers = max(1, min(self._threads, 6))
                with ThreadPoolExecutor(max_workers=workers) as pool:
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
                            result = TagResult(error=safe_error(exc, self._config.api_key))
                        done += 1
                        if result.error:
                            failed += 1
                            self.tagged.emit(str(rec.path), result.tags, result.error)
                        else:
                            tagged_ok += 1
                            self._cache.put(key, result.tags)
                            self.tagged.emit(str(rec.path), result.tags, "")
                        self.progress.emit(done, total)
                    for f in futures:
                        f.cancel()
            self._cache.save()
            self.finished_ok.emit(total, tagged_ok, failed)
        except Exception as exc:                      # missing model / bad key / no network
            self.failed.emit(safe_error(exc, self._config.api_key))

    def _tag_one(self, detector: Detector | None, rec) -> TagResult:
        if rec.duration <= 0:
            return TagResult(error="duration unknown")
        count = (
            sample_count(self._policy, rec.duration)
            if self._policy is not None
            else self._sample
        )

        local = TagResult()
        if self._mode == "hybrid":
            if detector is None:
                return TagResult(error="混合模式需要本地 ONNX 模型")
            local = tag_media(
                detector, self._ffmpeg, rec.path, rec.duration,
                sample_count=count, cancel_event=self._cancel,
                enabled_tags=self._enabled,
                color_tags_enabled=self._color_tags,
            )
            if local.error:
                return local
            if self._upload_target_only and not local.tags:
                return local

        labels = self._custom if self._mode == "hybrid" else self._config.labels
        if not labels:
            return local
        cloud = cloud_tag_video(
            self._ffmpeg, rec.path, rec.duration,
            CloudTagConfig(
                self._config.base_url, self._config.api_key,
                self._config.model, labels, self._config.timeout,
            ),
            sample_count=count,
            context_tags=local.tags,
            cancel_event=self._cancel,
        )
        if self._mode == "hybrid":
            merged = list(local.tags)
            for label in cloud.tags:
                if label not in merged:
                    merged.append(label)
            return TagResult(
                tags=merged,
                frames=local.frames + cloud.frames,
                detections=local.detections + cloud.detections,
                error=cloud.error,
            )
        return cloud