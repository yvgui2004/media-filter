"""Verify interaction behaviors: double-click toggles check; drag-toggling checks
or unchecks a block of rows depending on the anchor row the drag starts on.

Run: .venv/Scripts/python.exe scripts/verify_interaction.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from mediafilter.app import LOCALE_DIR
from mediafilter.config import Config
from mediafilter.core.models import FileRecord, MediaMetadata
from mediafilter.i18n import Translator
from mediafilter.ui.main_window import MainWindow
from mediafilter.ui.table_model import FileRecordModel
from mediafilter.ui.theme import apply_theme

failures: list[str] = []


def check(cond, label):
    print(f"[{'PASS' if cond else 'FAIL'}] {label}")
    if not cond:
        failures.append(label)


def _rec(name):
    return FileRecord(path=Path("D:/m") / name, name=name,
                      extension=name.rsplit(".", 1)[-1], size=100,
                      metadata=MediaMetadata(duration=10.0, video_bitrate=1_000_000,
                                             audio_bitrate=128_000))


def _drag(win, r_from, r_to):
    vp = win._view.viewport()
    c0 = win._view.visualRect(win._proxy.index(r_from, FileRecordModel.COL_NAME)).center()
    c1 = win._view.visualRect(win._proxy.index(r_to, FileRecordModel.COL_NAME)).center()
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, c0)
    QApplication.processEvents()
    for i in range(1, 6):
        y = c0.y() + (c1.y() - c0.y()) * i // 6
        QTest.mouseMove(vp, QPoint(c0.x(), y))
        QApplication.processEvents()
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, c1)
    QApplication.processEvents()


def main() -> int:
    app = QApplication(sys.argv)
    tr = Translator(LOCALE_DIR)
    tr.set_fallback("en")
    tr.set_language("zh")
    apply_theme(app, "light")

    win = MainWindow(tr, Config.load())
    win._model.set_records([_rec("a.mp4"), _rec("b.mp4"), _rec("c.mp4")])
    win.resize(600, 400)
    win.show()
    app.processEvents()

    # -- double-click toggles check (instead of opening the file) ---------
    idx = win._proxy.index(0, FileRecordModel.COL_NAME)
    win._on_double_clicked(idx)
    check(win._model.record(0).checked is True, "double-click toggles check False->True")
    win._on_double_clicked(idx)
    check(win._model.record(0).checked is False, "double-click toggles back True->False")

    # -- drag from an unchecked anchor checks the block --------------------
    win._model.set_checked(range(3), False)
    _drag(win, 0, 2)
    sel = sorted(r.row() for r in win._view.selectionModel().selectedRows())
    check(sel == [0, 1, 2], f"drag selects rows 0-2 ({sel})")
    checked = [win._model.record(k).checked for k in range(3)]
    check(checked == [True, True, True], f"unchecked anchor -> checks rows 0-2 ({checked})")

    # -- drag from a checked anchor unchecks the block ---------------------
    _drag(win, 0, 2)
    checked = [win._model.record(k).checked for k in range(3)]
    check(checked == [False, False, False], f"checked anchor -> unchecks rows 0-2 ({checked})")

    win.close()
    app.processEvents()
    print()
    print(f"RESULT: {len(failures)} failure(s)")
    for f in failures:
        print("  -", f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())