"""Launch the real GUI, populate it with sample data, and dump screenshots of
each screen + dialog. Also lets any Qt warnings surface on stderr.

Run: .venv/Scripts/python.exe scripts/inspect_ui.py 2> _inspect/stderr.log
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PySide6.QtWidgets import QApplication

from mediafilter.app import LOCALE_DIR
from mediafilter.config import Config
from mediafilter.core.ffmpeg import default_presets
from mediafilter.core.models import FileRecord, MediaMetadata
from mediafilter.i18n import Translator
from mediafilter.ui.main_window import MainWindow
from mediafilter.ui.theme import apply_theme
from mediafilter.ui.widgets.batch_dialog import BatchCommandDialog
from mediafilter.ui.widgets.format_convert import FormatConvertDialog

OUT = Path(__file__).resolve().parent.parent / "_inspect"


def settle(app, ms=600):
    deadline = time.time() + ms / 1000.0
    while time.time() < deadline:
        app.processEvents()


def make_records():
    def rec(name, size, dur, vbr, abr, checked=False):
        m = MediaMetadata(duration=dur, video_bitrate=vbr, audio_bitrate=abr)
        return FileRecord(
            path=Path("D:/media") / name, name=name,
            extension=name.rsplit(".", 1)[-1], size=size, metadata=m, checked=checked,
        )

    rows = [
        rec("movie_a_2024.mkv", 4_500_000_000, 7320.0, 5_000_000, 192_000),
        rec("movie_b_2024.mp4", 2_100_000_000, 5400.0, 3_000_000, 128_000, checked=True),
        rec("tv_episode_01.mkv", 900_000_000, 2700.0, 2_500_000, 128_000),
        rec("concert_live.flac", 45_000_000, 3600.0, 0, 960_000),
        rec("song_01.mp3", 4_000_000, 240.0, 0, 128_000),
        rec("broken_clip.avi", 1_000_000_000, 0.0, 0, 0),
    ]
    rows[-1].error = "ffprobe exit code 1: Invalid data found when processing input"
    return rows


def main() -> int:
    OUT.mkdir(exist_ok=True)
    app = QApplication(sys.argv)
    config = Config.load()
    tr = Translator(LOCALE_DIR)
    tr.set_fallback("en")
    tr.set_language("zh")

    apply_theme(app, "light")
    win = MainWindow(tr, config)
    records = make_records()
    win._model.set_records(records)
    win._populate_filter_formats(records)
    win.resize(1080, 640)
    win.show()
    settle(app)
    win.grab().save(str(OUT / "1_main_light_zh.png"))

    # batch command dialog
    dlg = BatchCommandDialog(records, win._tr, default_presets(), win)
    dlg.show()
    settle(app)
    dlg.grab().save(str(OUT / "2_batch_dialog.png"))
    dlg.close()

    # format convert dialog
    dlg2 = FormatConvertDialog(records, win._tr, win)
    dlg2.show()
    settle(app)
    dlg2.grab().save(str(OUT / "3_convert_dialog.png"))
    dlg2.close()

    # language toggle -> English
    win.toggle_language()
    settle(app)
    win.grab().save(str(OUT / "4_main_light_en.png"))

    # dark theme
    win.cycle_theme()  # light -> dark (order: system, light, dark -> from light goes dark)
    settle(app)
    win.grab().save(str(OUT / "5_main_dark_zh.png"))

    win.close()
    settle(app, 200)
    print("done. files in", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())