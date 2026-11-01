"""Thread-pool orchestration for scanning many files.

One worker thread per file (ffprobe is the actual cost, and subprocess calls
release the GIL), results collected through concurrent.futures.as_completed.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .models import FileRecord
from .probe import ProbeError, probe_file

ProgressCallback = Callable[[int, int], None]


def scan_and_probe(
    files: Iterable[Path],
    ffprobe_path: str | None,
    max_workers: int = 8,
    progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> tuple[list[FileRecord], bool]:
    """Build FileRecords for *files* and fill in probed metadata in parallel.

    Returns ``(records, cancelled)``. On cancel the already-finished records are
    returned intact; unfinished ones simply keep ``metadata=None``.
    """
    records = [_make_record(path) for path in files]
    total = len(records)
    if total == 0:
        return records, False

    cancel_event = cancel_event or threading.Event()
    workers = max(1, min(max_workers, total, 32))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_to_record = {pool.submit(probe_file, ffprobe_path, rec.path): rec for rec in records}
        done = 0
        for future in as_completed(future_to_record):
            record = future_to_record[future]
            try:
                record.metadata = future.result()
            except ProbeError as exc:
                record.error = str(exc)
            except Exception as exc:  # defensive: never let one file kill the scan
                record.error = f"{type(exc).__name__}: {exc}"
            done += 1
            if progress is not None:
                progress(done, total)
            if cancel_event.is_set():
                for pending in future_to_record:
                    pending.cancel()
                return records, True

    return records, False


def _safe_stat(path: Path) -> tuple[int, float]:
    try:
        st = path.stat()
        return st.st_size, st.st_mtime
    except OSError:
        return 0, 0.0


def _make_record(path: Path) -> FileRecord:
    size, mtime = _safe_stat(path)
    return FileRecord(
        path=path,
        name=path.name,
        extension=path.suffix.lstrip(".").lower(),
        size=size,
        mtime=mtime,
    )