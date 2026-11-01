"""Verify the two fixes:
1. Clicking the check column toggles exactly once (no delegate double-toggle).
2. Theme/language buttons stay visible in BOTH zh and en.

Run: .venv/Scripts/python.exe scripts/verify_fixes.py
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

failures: list[str] = []


def check(cond, label):
    print(f"[{'PASS' if cond else 'FAIL'}] {label}")
    if not cond:
        failures.append(label)


def toolbar_buttons(win):
    return list(win._toolbar.findChildren(QPushButton))


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

    # ---- Bug 1 ----
    print("=== Bug 1: checkbox click toggles exactly once ===")
    spy_calls = []
    orig_setdata = win._model.setData

    def spy(index, value, role):
        if role == Qt.CheckStateRole:
            spy_calls.append(value)
        return orig_setdata(index, value, role)

    win._model.setData = spy

    proxy_idx = win._proxy.index(0, FileRecordModel.COL_CHECK)
    rect = win._view.visualRect(proxy_idx)

    # rendering check: the checkbox indicator must still be drawn without the flag
    from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

    class _Delegate(QStyledItemDelegate):
        def expose(self, index):
            opt = QStyleOptionViewItem()
            self.initStyleOption(opt, index)
            return opt

    opt = _Delegate(win).expose(proxy_idx)
    try:
        flag = QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator
        has_indicator = bool(opt.features.value & flag.value)
    except AttributeError:
        has_indicator = None
    check(has_indicator is True, f"check indicator still rendered (HasCheckIndicator={has_indicator})")

    QTest.mouseClick(win._view.viewport(), Qt.LeftButton, Qt.NoModifier, rect.center())
    app.processEvents()

    check(rec.checked is True, f"click toggles checked False->True (got {rec.checked})")
    check(len(spy_calls) == 0, f"no delegate auto-toggle (setData CheckStateRole calls={len(spy_calls)})")

    QTest.mouseClick(win._view.viewport(), Qt.LeftButton, Qt.NoModifier, rect.center())
    app.processEvents()
    check(rec.checked is False, f"second click toggles True->False (got {rec.checked})")

    # ---- Bug 2 ----
    print("\n=== Bug 2: theme/language visible in both languages ===")
    for label in ("zh", "en"):
        if label == "en":
            win.toggle_language()
            app.processEvents()
        buttons = toolbar_buttons(win)
        names = {b.text() for b in buttons}
        hidden = [b.text() for b in buttons if not b.isVisible()]
        tb_w = win._toolbar.width()
        # overflow: any visible button extends past the toolbar width
        overflow = [b.text() for b in buttons if b.isVisible() and b.geometry().right() > tb_w]
        check(win._theme_btn.isVisible() and win._lang_btn.isVisible(),
              f"[{label}] theme & lang buttons visible (hidden={hidden})")
        check(not overflow, f"[{label}] no button overflows toolbar (overflow={overflow})")

    win.close()
    app.processEvents()
    print()
    print(f"RESULT: {len(failures)} failure(s)")
    for f in failures:
        print("  -", f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())