"""Diagnose two reported issues:
1. Does clicking the check column actually toggle the record's checked state?
2. Do the theme/language buttons overflow/hide after switching to English?

Run: .venv/Scripts/python.exe scripts/diagnose.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

from mediafilter.app import LOCALE_DIR
from mediafilter.config import Config
from mediafilter.core.models import FileRecord, MediaMetadata
from mediafilter.i18n import Translator
from mediafilter.ui.main_window import MainWindow
from mediafilter.ui.table_model import FileRecordModel
from mediafilter.ui.theme import apply_theme


def dump_toolbar(win, label):
    tb = win._toolbar
    print(f"\n[{label}] toolbar width={tb.width()}  (texts in this OS may print as mojibake)")
    for b in tb.findChildren(QPushButton):
        r = b.geometry()
        overflow = (r.x() + r.width()) > tb.width()
        print(f"  text={b.text()!r:24} x={r.x():4} w={r.width():4} right={r.x()+r.width():4} "
              f"visible={b.isVisible()} overflow={overflow}")
    print("  lang_btn .isVisible():", win._lang_btn.isVisible())
    print("  theme_btn .isVisible():", win._theme_btn.isVisible())


def main() -> int:
    app = QApplication(sys.argv)
    config = Config.load()
    tr = Translator(LOCALE_DIR)
    tr.set_fallback("en")
    tr.set_language("zh")
    apply_theme(app, "light")

    win = MainWindow(tr, config)
    rec = FileRecord(
        path=Path("D:/media") / "a.mp4", name="a.mp4", extension="mp4", size=100,
        metadata=MediaMetadata(duration=10.0, video_bitrate=1_000_000, audio_bitrate=128_000),
    )
    win._model.set_records([rec])
    win.resize(1080, 640)
    win.show()
    app.processEvents()

    # ---- Bug 1: does clicking toggle the checkbox? ----
    print("=== Bug 1: checkbox click ===")
    proxy_idx = win._proxy.index(0, FileRecordModel.COL_CHECK)
    rect = win._view.visualRect(proxy_idx)
    print(f"check cell visualRect: x={rect.x()} y={rect.y()} w={rect.width()} h={rect.height()}")

    viewport = win._view.viewport()
    print("checked before:", rec.checked)
    QTest.mouseClick(viewport, Qt.LeftButton, Qt.NoModifier, rect.center())
    app.processEvents()
    print("checked after center-click:", rec.checked)

    if not rec.checked:
        p = QPoint(rect.left() + rect.height() // 2, rect.center().y())
        QTest.mouseClick(viewport, Qt.LeftButton, Qt.NoModifier, p)
        app.processEvents()
        print("checked after indicator-click:", rec.checked)

    # also check stats label reflects a check
    print("stats file label:", win._stats._selected.text())

    # ---- Bug 2: toolbar buttons before/after language switch ----
    print("\n=== Bug 2: toolbar layout ===")
    dump_toolbar(win, "zh / light")
    win.toggle_language()
    app.processEvents()
    dump_toolbar(win, "en / light")

    win.close()
    app.processEvents()
    return 0


if __name__ == "__main__":
    sys.exit(main())