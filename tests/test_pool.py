import threading

from mediafilter.core.pool import scan_and_probe
from mediafilter.core.probe import ProbeError


def test_scan_and_probe_records_errors_when_ffprobe_missing(tmp_path):
    f = tmp_path / "a.mp4"
    f.write_text("not really a video")

    records, cancelled = scan_and_probe([f], ffprobe_path=None, max_workers=1)
    assert cancelled is False
    assert len(records) == 1
    assert records[0].metadata is None
    assert records[0].error  # ffprobe-not-found lands in the error field


def test_scan_and_probe_empty_input(tmp_path):
    records, cancelled = scan_and_probe([], ffprobe_path=None)
    assert records == []
    assert cancelled is False


def test_scan_and_probe_reports_progress(tmp_path):
    files = []
    for i in range(3):
        p = tmp_path / f"f{i}.mp4"
        p.write_text("x")
        files.append(p)

    ticks = []
    done = threading.Event()
    records, cancelled = scan_and_probe(
        files, ffprobe_path=None, max_workers=2,
        progress=lambda d, t: (ticks.append((d, t)), done.set() if d == t else None),
    )
    assert len(records) == 3
    assert not cancelled
    assert ticks
    assert ticks[-1] == (3, 3)