"""The batch runner must pass quoted paths through intact and count failures."""

from __future__ import annotations

import sys
from typing import cast

from PySide6.QtWidgets import QApplication

from mediafilter.ui.widgets.batch_dialog import CommandRunner, _for_batch_file


def _qt_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return cast(QApplication, app)


def _run(command: str) -> tuple[list[str], list[tuple[int, int]]]:
    _qt_app()
    runner = CommandRunner([command])
    lines: list[str] = []
    done: list[tuple[int, int]] = []
    runner.line.connect(lines.append)
    runner.finished.connect(lambda ok, failed: done.append((ok, failed)))
    runner.run()
    return lines, done


def test_quoted_path_with_spaces_reaches_the_child(tmp_path):
    target = tmp_path / "out with space.txt"
    script = "import sys; open(sys.argv[1], 'w').write('ok')"
    command = f'"{sys.executable}" -c "{script}" "{target}"'

    lines, done = _run(command)

    assert target.read_text(encoding="utf-8") == "ok"
    assert done == [(1, 0)]
    assert any(line.strip() == "[exit 0]" for line in lines)


def test_nonzero_exit_is_reported_as_failure():
    script = "import sys; print('boom', file=sys.stderr); sys.exit(3)"
    command = f'"{sys.executable}" -c "{script}"'

    lines, done = _run(command)

    assert done == [(0, 1)]
    assert any("[exit 3]" in line for line in lines)
    assert any("boom" in line for line in lines)


def test_batch_file_escapes_percent_signs():
    assert _for_batch_file('ffmpeg -i "C:\\a%20b\\clip.mp4"') == (
        'ffmpeg -i "C:\\a%%20b\\clip.mp4"'
    )