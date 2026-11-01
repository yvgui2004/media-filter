from pathlib import Path

from mediafilter.core.scanner import extension_of, scan_files


def test_scan_files_collects_only_media(tmp_path: Path):
    (tmp_path / "a.mp4").write_text("x")
    (tmp_path / "b.MKV").write_text("x")
    (tmp_path / "notes.txt").write_text("x")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.flac").write_text("x")
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "d.mp3").write_text("x")

    found = scan_files(tmp_path)
    names = {p.name for p in found}

    assert "a.mp4" in names
    assert "b.MKV" in names          # extension matching is case-insensitive
    assert "c.flac" in names
    assert "notes.txt" not in names
    assert "d.mp3" not in names      # hidden dir skipped
    assert len(found) == 3


def test_scan_files_respects_extension_override(tmp_path: Path):
    (tmp_path / "a.mp4").write_text("x")
    (tmp_path / "b.mp3").write_text("x")

    assert [p.name for p in scan_files(tmp_path, {"mp3"})] == ["b.mp3"]


def test_scan_files_missing_folder_returns_empty(tmp_path: Path):
    assert scan_files(tmp_path / "nope") == []


def test_extension_of():
    assert extension_of("C:/a/B.MKV") == "mkv"
    assert extension_of("noext") == ""