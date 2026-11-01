"""Programmatic UI verification: assert texts, data rendering, filtering,
stats, dialog contents, i18n parity, and that screenshots aren't blank.

Run: .venv/Scripts/python.exe scripts/verify_ui.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from mediafilter.app import LOCALE_DIR
from mediafilter.config import Config
from mediafilter.core.ffmpeg import default_presets
from mediafilter.core.models import FileRecord, MediaMetadata
from mediafilter.i18n import Translator
from mediafilter.ui.main_window import MainWindow
from mediafilter.ui.table_model import FileRecordModel
from mediafilter.ui.theme import apply_theme
from mediafilter.ui.widgets.batch_dialog import BatchCommandDialog
from mediafilter.ui.widgets.format_convert import FormatConvertDialog

failures: list[str] = []


def check(cond, label):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {label}")
    if not cond:
        failures.append(label)


def make_records():
    def rec(name, size, dur, vbr, abr, checked=False):
        m = MediaMetadata(duration=dur, video_bitrate=vbr, audio_bitrate=abr)
        return FileRecord(path=Path("D:/media") / name, name=name,
                          extension=name.rsplit(".", 1)[-1], size=size,
                          metadata=m, checked=checked)
    rows = [
        rec("movie_a_2024.mkv", 4_500_000_000, 7320.0, 5_000_000, 192_000),
        rec("movie_b_2024.mp4", 2_100_000_000, 5400.0, 3_000_000, 128_000, checked=True),
        rec("tv_episode_01.mkv", 900_000_000, 2700.0, 2_500_000, 128_000),
        rec("concert_live.flac", 45_000_000, 3600.0, 0, 960_000),
        rec("song_01.mp3", 4_000_000, 240.0, 0, 128_000),
        rec("broken_clip.avi", 1_000_000_000, 0.0, 0, 0),
    ]
    rows[-1].error = "ffprobe exit code 1: Invalid data found"
    return rows


def check_i18n_parity():
    en = json.loads((LOCALE_DIR / "en.json").read_text(encoding="utf-8"))
    zh = json.loads((LOCALE_DIR / "zh.json").read_text(encoding="utf-8"))
    check(set(en) == set(zh), f"i18n key parity en({len(en)})==zh({len(zh)})")
    missing_en = set(zh) - set(en)
    missing_zh = set(en) - set(zh)
    if missing_en:
        print("   zh-only keys:", sorted(missing_en))
    if missing_zh:
        print("   en-only keys:", sorted(missing_zh))
    return en, zh


def check_translator_resolves_every_key(tr):
    en = json.loads((LOCALE_DIR / "en.json").read_text(encoding="utf-8"))
    zh = json.loads((LOCALE_DIR / "zh.json").read_text(encoding="utf-8"))
    bad = []
    for table, lang in ((en, "en"), (zh, "zh")):
        tr.set_language(lang)
        for key in table:
            if tr.tr(key) == key:
                bad.append(f"{lang}:{key}")
    check(not bad, f"translator resolves all keys ({len(bad)} unresolved)")
    if bad:
        print("   unresolved:", bad[:10])


def pixel_check(png_path):
    img = QImage(str(png_path))
    if img.isNull():
        check(False, f"screenshot loads: {png_path.name}")
        return
    w, h = img.width(), img.height()
    check(w > 400 and h > 300, f"screenshot size ok {png_path.name} ({w}x{h})")
    colors = set()
    for y in range(0, h, max(1, h // 40)):
        for x in range(0, w, max(1, w // 40)):
            colors.add(img.pixel(x, y))
    check(len(colors) > 8, f"screenshot not blank {png_path.name} ({len(colors)} colors)")


def main() -> int:
    app = QApplication(sys.argv)
    config = Config.load()
    tr = Translator(LOCALE_DIR)
    tr.set_fallback("en")
    tr.set_language("zh")

    check_i18n_parity()
    check_translator_resolves_every_key(tr)

    apply_theme(app, "light")
    tr.set_language("zh")
    win = MainWindow(tr, config)
    records = make_records()
    win._model.set_records(records)
    win._populate_filter_formats(records)
    win.show()
    app.processEvents()

    # -- window / toolbar text --------------------------------------------
    check(win.windowTitle() == "媒体筛选工具", f"title localized ({win.windowTitle()!r})")
    btn_labels = [b.text() for b in win.findChildren(QPushButton) if b.text()]
    leaked = [t for t in btn_labels if t.startswith("toolbar.") or t.startswith("dialog.")
              or t.startswith("theme.") or t.startswith("col.")]
    check(not leaked, f"no raw i18n key leaked into buttons ({leaked})")
    check(win._search.placeholderText() == "搜索文件名…", f"search placeholder ok ({win._search.placeholderText()!r})")
    check("全部格式" in [win._filter_combo.itemText(i) for i in range(win._filter_combo.count())],
          "filter combo has '全部格式'")
    check(win._lang_btn.text() == "EN", f"language button shows target ({win._lang_btn.text()!r})")

    # -- model / data rendering ------------------------------------------
    check(win._model.rowCount() == 6, f"model rowCount==6 ({win._model.rowCount()})")
    check(win._model.columnCount() == 7, f"model columnCount==7")
    headers = [win._model.headerData(i, Qt.Horizontal) for i in range(7)]
    check(headers[1:] == ["文件名", "大小", "时长", "码率", "格式", "修改时间"], f"headers localized ({headers[1:]})")

    idx_size = win._model.index(0, FileRecordModel.COL_SIZE)
    idx_dur = win._model.index(0, FileRecordModel.COL_DURATION)
    idx_br = win._model.index(0, FileRecordModel.COL_BITRATE)
    check(win._model.data(idx_size, Qt.DisplayRole) == "4.19 GB", f"size rendered ({win._model.data(idx_size, Qt.DisplayRole)!r})")
    check(win._model.data(idx_dur, Qt.DisplayRole) == "2:02:00", f"duration rendered ({win._model.data(idx_dur, Qt.DisplayRole)!r})")
    check(win._model.data(idx_br, Qt.DisplayRole) == "5.00 Mbps", f"bitrate rendered ({win._model.data(idx_br, Qt.DisplayRole)!r})")

    check(win._model.data(win._model.index(1, FileRecordModel.COL_CHECK), Qt.CheckStateRole) == Qt.Checked,
          "checked row shows Qt.Checked")

    # -- filter proxy -----------------------------------------------------
    win._proxy.set_formats({"mkv"})
    check(win._proxy.rowCount() == 2, f"format filter mkv -> 2 rows ({win._proxy.rowCount()})")
    win._proxy.set_formats(set())
    win._proxy.set_search("song")
    check(win._proxy.rowCount() == 1, f"search 'song' -> 1 row ({win._proxy.rowCount()})")
    win._proxy.set_search("")

    # -- stats bar --------------------------------------------------------
    stats_text = " | ".join(l.text() for l in win._stats.findChildren(type(win._stats._files)))
    seg = " | ".join(l.text() for l in win._stats.findChildren(type(win._stats._files)))
    check("文件：6" in seg and "已选：1" in seg, f"stats bar totals ({seg!r})")

    # -- dialogs ----------------------------------------------------------
    dlg = BatchCommandDialog(records, win._tr, default_presets(), win)
    check(dlg._preset_combo.count() == 6, f"batch presets == 6 ({dlg._preset_combo.count()})")
    check("{input}" in dlg._template.toPlainText() and "{output}" in dlg._template.toPlainText(),
          "batch template has placeholders")
    cmds = dlg._commands()
    check(len(cmds) == 6 and all(c.startswith("ffmpeg") for c in cmds),
          f"batch generates 6 ffmpeg commands ({len(cmds)})")
    dlg.deleteLater()

    dlg2 = FormatConvertDialog(records, win._tr, win)
    items = [dlg2._target.itemText(i) for i in range(dlg2._target.count())]
    check(items == ["mp4", "mkv", "mov", "webm", "avi", "flv", "ts", "m4v"], f"convert targets ok ({items})")
    check(len(dlg2._commands()) == 6, f"convert generates 6 commands ({len(dlg2._commands())})")
    dlg2.deleteLater()

    # -- zero-size visible widgets ---------------------------------------
    empties = []
    for w in win.findChildren(QWidget):
        if w.isVisible() and (w.width() < 1 or w.height() < 1):
            empties.append(w)
    check(not empties, f"no visible zero-size widgets ({[type(e).__name__ for e in empties]})")

    # -- screenshots ------------------------------------------------------
    out = Path(__file__).resolve().parent.parent / "_inspect"
    for p in sorted(out.glob("*.png")):
        pixel_check(p)

    print()
    print(f"RESULT: {len(failures)} failure(s)")
    for f in failures:
        print("  -", f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())