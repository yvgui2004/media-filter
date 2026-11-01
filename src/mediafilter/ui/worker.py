"""Background scan worker: walks the folder and probes in a worker thread."""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ..core.pool import scan_and_probe
from ..core.scanner import scan_files


class ScanWorker(QThread):
    progress = Signal(int, int)
    done = Signal(list)      # list[FileRecord]
    aborted = Signal(list)   # partial list[FileRecord]
    failed = Signal(str)

    def __init__(self, folder: str, ffprobe_path: str | None, max_workers: int,
                 extensions=None, parent=None):
        super().__init__(parent)
        self._folder = folder
        self._ffprobe = ffprobe_path
        self._workers = max_workers
        self._extensions = extensions
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        try:
            files = scan_files(self._folder, self._extensions)
            records, cancelled = scan_and_probe(
                files,
                self._ffprobe,
                self._workers,
                progress=lambda d, t: self.progress.emit(d, t),
                cancel_event=self._cancel,
            )
            if cancelled:
                self.aborted.emit(records)
            else:
                self.done.emit(records)
        except Exception as exc:  # defensive: surface any unexpected failure
            self.failed.emit(f"{type(exc).__name__}: {exc}")