import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from mediafilter.config import Config
from mediafilter.i18n import Translator
from mediafilter.ui.main_window import MainWindow
from mediafilter.ui.theme import apply_theme

app = QApplication([])
app.setFont(QFont("Microsoft YaHei", 9))
cfg = Config()
cfg.ai_sample_frames = 2
cfg.ai_threads = 2
tr = Translator(Path("src/mediafilter/i18n/locales"))
tr.set_fallback("en")
tr.set_language("zh")
apply_theme(app, "light")

w = MainWindow(tr, cfg)
w.resize(1280, 760)
if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
    w.move(-3200, -3200)
w.show()


def wait_until(predicate, timeout=240):
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.05)
    return False


folder = sys.argv[1] if len(sys.argv) > 1 else "."
w.start_scan(folder)
assert wait_until(lambda: w._worker is None), "scan timed out"
print("records:", w._model.rowCount())

t0 = time.time()
w.start_tagging()
assert wait_until(lambda: w._tag_worker is None), "tagging timed out"
print(f"tagging took {time.time() - t0:.1f}s")

for i in range(w._model.rowCount()):
    r = w._model.record(i)
    print(f"{r.name:45s} {r.duration:7.1f}s  tags={r.tags}  err={r.ai_error}")

print("tag combo:", [w._tag_combo.itemText(i) for i in range(w._tag_combo.count())])

Path("assets").mkdir(exist_ok=True)
w.grab().save("assets/screenshot_ai.png")

idx = w._tag_combo.findText("人物")
if idx > 0:
    w._tag_combo.setCurrentIndex(idx)
    app.processEvents()
    print("visible after tag filter:", w._proxy.rowCount())
    w.grab().save("assets/screenshot_ai_filter.png")
print("saved screenshots")