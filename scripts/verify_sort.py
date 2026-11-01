"""Verify the sort selector, toolbar selection buttons, and bottom action bar.

Run: .venv/Scripts/python.exe scripts/verify_sort.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton

from mediafilter.app import LOCALE_DIR
from mediafilter.config import Config
from mediafilter.core.models import FileRecord
from mediafilter.i18n import Translator
from mediafilter.ui.main_window import MainWindow
from mediafilter.ui.table_model import FileRecordModel
from mediafilter.ui.theme import apply_theme

failures: list[str] = []


def check(cond, label):
    print(f"[{'PASS' if cond else 'FAIL'}] {label}")
    if not cond:
        failures.append(label)


def _rec(name, size, mtime):
    return FileRecord(path=Path("D:/media") / name, name=name,
                      extension=name.rsplit(".", 1)[-1], size=size, mtime=mtime)


def proxy_names(win):
    return [win._proxy.data(win._proxy.index(r, FileRecordModel.COL_NAME), Qt.DisplayRole)
            for r in range(win._proxy.rowCount())]


def main() -> int:
    app = QApplication(sys.argv)
    config = Config.load()
    tr = Translator(LOCALE_DIR)
    tr.set_fallback("en")
    tr.set_language("zh")
    apply_theme(app, "light")

    win = MainWindow(tr, config)
    # size order differs from mtime order so we can tell the two apart
    win._model.set_records([_rec("a.mp4", 100, 300), _rec("b.mp4", 300, 100), _rec("c.mp4", 200, 200)])
    win._populate_filter_formats(win._model.records())
    win._apply_sort()

    # -- sort combo contents ---------------------------------------------
    check(win._sort_combo.count() == 6, f"sort combo has 6 options ({win._sort_combo.count()})")
    check(win._sort_combo.itemText(0) == "文件名", f"first option is 文件名 ({win._sort_combo.itemText(0)!r})")
    check(win._sort_combo.currentData() == FileRecordModel.COL_NAME, "default sort column is name")
    check(win._order_btn.text() == "↑", f"default order button ↑ ({win._order_btn.text()!r})")

    # -- sort by size asc ------------------------------------------------
    win._sort_combo.setCurrentIndex(win._sort_combo.findData(FileRecordModel.COL_SIZE))
    check(proxy_names(win) == ["a.mp4", "c.mp4", "b.mp4"], f"size asc -> a,c,b ({proxy_names(win)})")

    # -- toggle descending ------------------------------------------------
    win._toggle_sort_order()
    check(win._order_btn.text() == "↓", f"order button ↓ ({win._order_btn.text()!r})")
    check(proxy_names(win) == ["b.mp4", "c.mp4", "a.mp4"], f"size desc -> b,c,a ({proxy_names(win)})")

    # -- sort by mtime asc ------------------------------------------------
    win._sort_combo.setCurrentIndex(win._sort_combo.findData(FileRecordModel.COL_MTIME))
    if not win._sort_ascending:
        win._toggle_sort_order()
    check(win._order_btn.text() == "↑", f"order button ↑ after mtime ({win._order_btn.text()!r})")
    check(proxy_names(win) == ["b.mp4", "c.mp4", "a.mp4"], f"mtime asc -> b,c,a ({proxy_names(win)})")

    # -- header click stays in sync with the dropdown ---------------------
    win._view.sortByColumn(FileRecordModel.COL_DURATION, Qt.DescendingOrder)
    check(win._sort_combo.currentData() == FileRecordModel.COL_DURATION, "header click syncs combo column")
    check(win._sort_ascending is False and win._order_btn.text() == "↓",
          "header click syncs descending order")

    # -- selection buttons back in the toolbar -----------------------------
    toolbar_buttons = win._toolbar.findChildren(QPushButton)
    for attr in ("_select_all_btn", "_deselect_all_btn", "_check_btn", "_uncheck_btn"):
        check(getattr(win, attr) in toolbar_buttons, f"{attr} in the toolbar")

    # -- result-oriented buttons in the bottom bar -------------------------
    for attr in ("_export_btn", "_batch_btn", "_convert_btn"):
        b = getattr(win, attr)
        check(b not in toolbar_buttons, f"{attr} not in the toolbar")
        check(b in win._stats.findChildren(QPushButton), f"{attr} in the bottom bar")

    win.close()
    app.processEvents()
    print()
    print(f"RESULT: {len(failures)} failure(s)")
    for f in failures:
        print("  -", f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())