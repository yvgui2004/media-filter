"""Main application window: toolbar, table view, stats and status."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStyle,
    QStyledItemDelegate,
    QTableView,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..config import Config
from ..core.ffmpeg import Preset, default_presets
from ..core.probe import find_ffprobe
from ..core.scanner import DEFAULT_EXTENSIONS
from ..export import export_txt
from ..i18n import Translator
from .filter_proxy import FilterProxyModel
from .stats_bar import StatsBar
from .table_model import FileRecordModel
from .theme import apply_theme
from .worker import ScanWorker
from .widgets import BatchCommandDialog, FormatConvertDialog

_THEME_MODES = ("system", "light", "dark")

# Sort dropdown options: (i18n column key -> model column).
_SORT_FIELDS = (
    ("col.name", FileRecordModel.COL_NAME),
    ("col.size", FileRecordModel.COL_SIZE),
    ("col.duration", FileRecordModel.COL_DURATION),
    ("col.bitrate", FileRecordModel.COL_BITRATE),
    ("col.format", FileRecordModel.COL_FORMAT),
    ("col.mtime", FileRecordModel.COL_MTIME),
)


_SORT_FIELDS = (
    ("col.name", FileRecordModel.COL_NAME),
    ("col.size", FileRecordModel.COL_SIZE),
    ("col.duration", FileRecordModel.COL_DURATION),
    ("col.bitrate", FileRecordModel.COL_BITRATE),
    ("col.format", FileRecordModel.COL_FORMAT),
    ("col.mtime", FileRecordModel.COL_MTIME),
)


class _NoFocusDelegate(QStyledItemDelegate):
    """Item delegate that suppresses the focus rectangle around the current cell.

    Selection highlighting is untouched; only the thin dotted/solid outline Qt
    draws for keyboard focus on the clicked cell is removed.
    """

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.state &= ~QStyle.State_HasFocus


class _TableView(QTableView):
    """Table view that reports a left-button rubber-band selection as a drag.

    A plain click still only selects; once the mouse moves past the drag
    threshold and is released, ``dragged`` fires carrying the model index the
    drag started on. The window uses that anchor to decide check vs uncheck.
    """

    dragged = Signal(object)   # proxy index the drag started on (may be invalid)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._press_pos = None
        self._press_index = QModelIndex()
        self._dragging = False

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_pos = event.pos()
            self._press_index = self.indexAt(event.pos())
            self._dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self._press_pos is not None
                and event.buttons() & Qt.LeftButton
                and (event.pos() - self._press_pos).manhattanLength() >= QApplication.startDragDistance()):
            self._dragging = True
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        was_dragging = self._dragging
        press_index = self._press_index
        self._press_pos = None
        self._press_index = QModelIndex()
        self._dragging = False
        super().mouseReleaseEvent(event)
        if was_dragging and event.button() == Qt.LeftButton:
            self.dragged.emit(press_index)


class MainWindow(QMainWindow):
    def __init__(self, tr: Translator, config: Config, parent=None):
        super().__init__(parent)
        self._translator = tr
        self._tr = tr.tr                # callable tr(key, **kwargs)
        self._config = config
        self._worker: ScanWorker | None = None
        self._ffprobe_path = find_ffprobe()
        self._filter_formats: list[str] = []   # extensions currently selectable
        self._sort_ascending = True
        self._syncing_sort = False

        self._build_ui()
        self._connect_signals()
        self.retranslate()

        # restore saved state
        if config.window_geometry:
            self._restore_geometry(config.window_geometry)
        else:
            self.resize(1080, 640)

    def _restore_geometry(self, text: str) -> None:
        try:
            x, y, w, h = (int(v) for v in text.split(","))
            if w > 200 and h > 200:
                self.setGeometry(x, y, w, h)
        except (ValueError, TypeError):
            self.resize(1080, 640)

    # -- construction ----------------------------------------------------

    def _build_ui(self) -> None:
        self.setWindowTitle("Media Filter")

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # toolbar (primary actions)
        self._toolbar = QToolBar()
        self._toolbar.setMovable(False)
        self.addToolBar(self._toolbar)

        self._open_btn = self._add_tool("toolbar.open_folder", self.open_folder)
        self._refresh_btn = self._add_tool("toolbar.refresh", self.refresh_current_folder)
        self._toolbar.addSeparator()
        self._select_all_btn = self._add_tool("toolbar.select_all", self.select_all)
        self._deselect_all_btn = self._add_tool("toolbar.deselect_all", self.deselect_all)
        self._check_btn = self._add_tool("toolbar.check_selected", self.check_selected)
        self._uncheck_btn = self._add_tool("toolbar.uncheck_selected", self.uncheck_selected)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._toolbar.addWidget(spacer)

        self._theme_btn = QPushButton()
        self._theme_btn.clicked.connect(self.cycle_theme)
        self._toolbar.addWidget(self._theme_btn)
        self._lang_btn = QPushButton()
        self._lang_btn.clicked.connect(self.toggle_language)
        self._toolbar.addWidget(self._lang_btn)

        root.addWidget(self._toolbar)

        # filter row
        filter_row = QWidget()
        fr = QHBoxLayout(filter_row)
        fr.setContentsMargins(12, 6, 12, 6)
        fr.setSpacing(8)

        self._search = QLineEdit()
        fr.addWidget(self._search, 2)

        self._filter_label = QLabel()
        fr.addWidget(self._filter_label)
        self._filter_combo = QComboBox()
        fr.addWidget(self._filter_combo, 1)

        self._sort_label = QLabel()
        fr.addWidget(self._sort_label)
        self._sort_combo = QComboBox()
        fr.addWidget(self._sort_combo)
        self._order_btn = QPushButton()
        self._order_btn.setObjectName("orderButton")
        self._order_btn.setFixedWidth(30)
        self._order_btn.clicked.connect(self._toggle_sort_order)
        fr.addWidget(self._order_btn)

        self._threads_label = QLabel()
        fr.addWidget(self._threads_label)
        self._threads = QSpinBox()
        self._threads.setRange(1, 32)
        self._threads.setValue(self._config.scan_threads)
        fr.addWidget(self._threads)

        self._stop_btn = QPushButton()
        self._stop_btn.clicked.connect(self.cancel_scan)
        self._stop_btn.setEnabled(False)
        fr.addWidget(self._stop_btn)

        root.addWidget(filter_row)

        # table
        self._model = FileRecordModel(self)
        self._proxy = FilterProxyModel(self)
        self._proxy.setSourceModel(self._model)

        self._view = _TableView()
        self._view.setModel(self._proxy)
        self._view.setItemDelegate(_NoFocusDelegate(self._view))
        self._view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._view.setSortingEnabled(True)
        self._view.setAlternatingRowColors(True)
        self._view.setContextMenuPolicy(Qt.CustomContextMenu)
        self._view.verticalHeader().setVisible(False)
        header = self._view.horizontalHeader()
        header.setSectionResizeMode(FileRecordModel.COL_CHECK, QHeaderView.Fixed)
        header.resizeSection(FileRecordModel.COL_CHECK, 34)
        header.setSectionResizeMode(FileRecordModel.COL_NAME, QHeaderView.Stretch)
        header.setSectionResizeMode(FileRecordModel.COL_FORMAT, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(FileRecordModel.COL_MTIME, QHeaderView.ResizeToContents)
        header.resizeSection(FileRecordModel.COL_SIZE, 90)
        header.resizeSection(FileRecordModel.COL_DURATION, 90)
        header.resizeSection(FileRecordModel.COL_BITRATE, 100)
        header.setStretchLastSection(False)
        root.addWidget(self._view, 1)

        # bottom bar: stats on the left, result-oriented actions on the right
        self._stats = StatsBar()

        self._export_btn = QPushButton()
        self._export_btn.clicked.connect(self.export_report)
        self._batch_btn = QPushButton()
        self._batch_btn.clicked.connect(self.open_batch)
        self._convert_btn = QPushButton()
        self._convert_btn.clicked.connect(self.open_convert)
        for b in (self._export_btn, self._batch_btn, self._convert_btn):
            self._stats.add_action(b)

        root.addWidget(self._stats)

        self.setCentralWidget(central)

        # status bar + progress
        self.statusBar().showMessage("")
        self._progress = QProgressBar()
        self._progress.setFixedWidth(220)
        self._progress.setVisible(False)
        self.statusBar().addPermanentWidget(self._progress)

    def _add_tool(self, key: str, slot) -> QPushButton:
        btn = QPushButton()
        btn.clicked.connect(slot)
        self._toolbar.addWidget(btn)
        return btn

    def _connect_signals(self) -> None:
        self._search.textChanged.connect(self._proxy.set_search)
        self._filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        self._sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        self._view.horizontalHeader().sortIndicatorChanged.connect(self._on_header_sort_changed)
        self._model.checkedChanged.connect(self._refresh_stats)
        self._view.clicked.connect(self._on_clicked)
        self._view.doubleClicked.connect(self._on_double_clicked)
        self._view.dragged.connect(self._on_drag_finished)
        self._view.customContextMenuRequested.connect(self._show_context_menu)
        self._view.selectionModel().selectionChanged.connect(self._refresh_stats)

    # -- i18n / theme ----------------------------------------------------

    def retranslate(self) -> None:
        tr = self._tr
        self.setWindowTitle(tr("app.title"))

        text_map = {
            "toolbar.open_folder": self._open_btn,
            "toolbar.refresh": self._refresh_btn,
            "toolbar.select_all": self._select_all_btn,
            "toolbar.deselect_all": self._deselect_all_btn,
            "toolbar.check_selected": self._check_btn,
            "toolbar.uncheck_selected": self._uncheck_btn,
            "toolbar.export": self._export_btn,
            "toolbar.batch": self._batch_btn,
            "toolbar.convert": self._convert_btn,
        }
        for key, widget in text_map.items():
            widget.setText(tr(key))

        self._search.setPlaceholderText(tr("toolbar.search"))
        self._filter_label.setText(tr("toolbar.filter"))
        self._sort_label.setText(tr("toolbar.sort"))
        self._threads_label.setText(tr("toolbar.threads"))
        self._stop_btn.setText(tr("status.cancelled"))
        self._theme_btn.setText(tr("theme.toggle") + ": " + tr(_theme_key(self._config.theme_mode)))
        self._lang_btn.setText(tr("lang.toggle"))
        self._update_order_button()

        self._model.set_headers([
            "", tr("col.name"), tr("col.size"),
            tr("col.duration"), tr("col.bitrate"), tr("col.format"), tr("col.mtime"),
        ])
        self._stats.set_tr(self._tr)
        self._rebuild_filter_combo()
        self._rebuild_sort_combo()
        self._refresh_stats()

    def cycle_theme(self) -> None:
        idx = _THEME_MODES.index(self._config.theme_mode)
        self._config.theme_mode = _THEME_MODES[(idx + 1) % len(_THEME_MODES)]
        self._config.save()
        apply_theme(QApplication.instance(), self._config.theme_mode)
        self.retranslate()

    def toggle_language(self) -> None:
        new = "en" if self._translator.language == "zh" else "zh"
        self._translator.set_language(new)
        self._config.language = new
        self._config.save()
        self.retranslate()

    # -- filter combo ----------------------------------------------------

    def _rebuild_filter_combo(self) -> None:
        current = self._filter_for_index(self._filter_combo.currentIndex())
        self._filter_combo.blockSignals(True)
        self._filter_combo.clear()
        self._filter_combo.addItem(self._tr("toolbar.filter_all"))
        for ext in self._filter_formats:
            self._filter_combo.addItem(ext.upper())
        # restore selection
        target = 0
        if current is not None and current in self._filter_formats:
            target = self._filter_formats.index(current) + 1
        self._filter_combo.setCurrentIndex(target)
        self._filter_combo.blockSignals(False)
        self._on_filter_changed()

    def _filter_for_index(self, i: int):
        if i <= 0 or i > len(self._filter_formats):
            return None
        return self._filter_formats[i - 1]

    def _on_filter_changed(self) -> None:
        ext = self._filter_for_index(self._filter_combo.currentIndex())
        self._proxy.set_formats({ext} if ext else set())

    def _populate_filter_formats(self, records) -> None:
        exts = sorted({r.extension for r in records if r.extension})
        self._filter_formats = exts
        self._rebuild_filter_combo()

    # -- sort controls ---------------------------------------------------

    def _rebuild_sort_combo(self) -> None:
        current = self._sort_column()
        self._sort_combo.blockSignals(True)
        self._sort_combo.clear()
        for key, col in _SORT_FIELDS:
            self._sort_combo.addItem(self._tr(key), col)
        target = self._sort_combo.findData(current)
        self._sort_combo.setCurrentIndex(target if target >= 0 else 0)
        self._sort_combo.blockSignals(False)
        self._apply_sort()

    def _sort_column(self) -> int:
        col = self._sort_combo.currentData()
        return FileRecordModel.COL_NAME if col is None else col

    def _apply_sort(self) -> None:
        order = Qt.AscendingOrder if self._sort_ascending else Qt.DescendingOrder
        self._view.sortByColumn(self._sort_column(), order)

    def _on_sort_changed(self, _index: int) -> None:
        if self._syncing_sort:
            return
        self._apply_sort()

    def _toggle_sort_order(self) -> None:
        self._sort_ascending = not self._sort_ascending
        self._update_order_button()
        self._apply_sort()

    def _update_order_button(self) -> None:
        self._order_btn.setText("↑" if self._sort_ascending else "↓")
        self._order_btn.setToolTip(
            self._tr("sort.asc") if self._sort_ascending else self._tr("sort.desc")
        )

    def _on_header_sort_changed(self, logical_index: int, order) -> None:
        self._syncing_sort = True
        idx = self._sort_combo.findData(logical_index)
        if idx >= 0:
            self._sort_combo.setCurrentIndex(idx)
        self._sort_ascending = order == Qt.AscendingOrder
        self._update_order_button()
        self._syncing_sort = False

    # -- scanning --------------------------------------------------------

    def open_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, self._tr("toolbar.open_folder"), self._config.last_folder or ""
        )
        if folder:
            self.start_scan(folder)

    def refresh_current_folder(self) -> None:
        if self._config.last_folder:
            self.start_scan(self._config.last_folder)
        else:
            self.open_folder()

    def start_scan(self, folder: str) -> None:
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(self, self._tr("app.title"), self._tr("msg.scanning"))
            return
        if not self._ffprobe_path:
            QMessageBox.warning(self, self._tr("app.title"), self._tr("msg.ffprobe_missing"))
            return

        self._config.last_folder = folder
        self._config.scan_threads = self._threads.value()
        self._config.save()

        self._model.set_records([])
        self._filter_formats = []
        self._rebuild_filter_combo()
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._stop_btn.setEnabled(True)

        self._worker = ScanWorker(
            folder, self._ffprobe_path, self._threads.value(),
            extensions=DEFAULT_EXTENSIONS, parent=self,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_scan_done)
        self._worker.aborted.connect(self._on_scan_aborted)
        self._worker.failed.connect(self._on_scan_failed)
        self._worker.start()

    def cancel_scan(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()

    def _on_progress(self, done: int, total: int) -> None:
        self._progress.setMaximum(max(1, total))
        self._progress.setValue(done)
        self.statusBar().showMessage(self._tr("status.scanning", done=done, total=total))

    def _finish_scan(self) -> None:
        self._progress.setVisible(False)
        self._stop_btn.setEnabled(False)
        self._worker = None

    def _on_scan_done(self, records: list) -> None:
        self._finish_scan()
        self._model.set_records(records)
        self._populate_filter_formats(records)
        self._apply_sort()
        errors = sum(1 for r in records if r.error)
        self.statusBar().showMessage(
            self._tr("status.done", files=len(records), errors=errors)
        )

    def _on_scan_aborted(self, records: list) -> None:
        self._finish_scan()
        if records:
            self._model.set_records(records)
            self._populate_filter_formats(records)
            self._apply_sort()
        self.statusBar().showMessage(self._tr("status.cancelled"))

    def _on_scan_failed(self, message: str) -> None:
        self._finish_scan()
        QMessageBox.critical(self, self._tr("app.title"), message)

    # -- selection / checks ---------------------------------------------

    def _selected_source_rows(self) -> list[int]:
        rows = []
        for idx in self._view.selectionModel().selectedRows():
            rows.append(self._proxy.mapToSource(idx).row())
        return sorted(set(rows))

    def _on_clicked(self, index) -> None:
        # The checkbox column relies on an explicit toggle here: Qt's built-in
        # auto-toggle does not fire for this custom model + proxy setup.
        if index.column() == FileRecordModel.COL_CHECK:
            self._model.toggle_check(self._proxy.mapToSource(index).row())

    def _on_double_clicked(self, index) -> None:
        src = self._proxy.mapToSource(index)
        self._model.toggle_check(src.row())

    def select_all(self) -> None:
        self._view.selectAll()

    def deselect_all(self) -> None:
        self._view.clearSelection()

    def check_selected(self) -> None:
        self._model.set_checked(self._selected_source_rows(), True)

    def uncheck_selected(self) -> None:
        self._model.set_checked(self._selected_source_rows(), False)

    def _on_drag_finished(self, proxy_index) -> None:
        rows = self._selected_source_rows()
        if not rows:
            return
        # Direction follows the anchor row the drag started on: dragging from
        # an unchecked row checks the selection, from a checked row unchecks it.
        # A drag that began on empty space (no anchor) defaults to checking.
        target = True
        if proxy_index is not None and proxy_index.isValid():
            src = self._proxy.mapToSource(proxy_index)
            target = not self._model.record(src.row()).checked
        self._model.set_checked(rows, target)

    def _refresh_stats(self) -> None:
        self._stats.set_stats(self._model.rowCount(), self._model.checked_records())

    def _target_records(self):
        records = self._model.checked_records()
        if records:
            return records
        rows = self._selected_source_rows()
        return [self._model.record(r) for r in rows]

    # -- actions ---------------------------------------------------------

    def export_report(self) -> None:
        records = self._target_records()
        if not records:
            QMessageBox.information(self, self._tr("app.title"), self._tr("msg.nothing_selected"))
            return
        path, _ = QFileDialog.getSaveFileName(
            self, self._tr("toolbar.export"), "media_report.txt", "Text (*.txt)"
        )
        if not path:
            return
        export_txt(records, path, self._tr)
        QMessageBox.information(self, self._tr("app.title"),
                                self._tr("msg.export_done", path=path))

    def open_batch(self) -> None:
        records = self._target_records()
        if not records:
            QMessageBox.information(self, self._tr("app.title"), self._tr("msg.nothing_selected"))
            return
        dialog = BatchCommandDialog(records, self._tr, self._load_presets(), self)
        dialog.exec()

    def open_convert(self) -> None:
        records = self._target_records()
        if not records:
            QMessageBox.information(self, self._tr("app.title"), self._tr("msg.nothing_selected"))
            return
        dialog = FormatConvertDialog(records, self._tr, self)
        dialog.exec()

    def _load_presets(self) -> list[Preset]:
        data = self._config.presets
        presets: list[Preset] = []
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and "key" in item and "template" in item:
                    presets.append(Preset(
                        key=item["key"],
                        template=item["template"],
                        name=item.get("name", item["key"]),
                        description=item.get("description", ""),
                    ))
        return presets or default_presets()

    # -- context menu ----------------------------------------------------

    def _show_context_menu(self, pos) -> None:
        menu = QMenu(self)
        rows = self._selected_source_rows()
        has_sel = bool(rows)
        act_open = menu.addAction(self._tr("menu.open"))
        act_reveal = menu.addAction(self._tr("menu.open_location"))
        act_copy = menu.addAction(self._tr("menu.copy_paths"))
        menu.addSeparator()
        act_delete = menu.addAction(self._tr("menu.delete"))
        for a in (act_open, act_reveal, act_copy, act_delete):
            a.setEnabled(has_sel)

        chosen = menu.exec(self._view.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen is act_open:
            self._open_path(self._model.record(rows[0]).path)
        elif chosen is act_reveal:
            self._reveal(self._model.record(rows[0]).path)
        elif chosen is act_copy:
            lines = [str(self._model.record(r).path) for r in rows]
            QApplication.clipboard().setText("\n".join(lines))
        elif chosen is act_delete:
            self.delete_selected()

    def delete_selected(self) -> None:
        rows = self._selected_source_rows()
        if not rows:
            return
        n = len(rows)
        answer = QMessageBox.question(
            self, self._tr("app.title"), self._tr("msg.delete_confirm", n=n),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        records = [self._model.record(r) for r in rows]
        try:
            from send2trash import send2trash
            trash = send2trash
        except ImportError:
            trash = os.remove
        failed = 0
        for rec in records:
            try:
                trash(str(rec.path))
            except Exception:
                failed += 1
        self._model.remove_rows(rows)
        self.statusBar().showMessage(
            self._tr("status.done", files=n - failed, errors=failed)
        )

    # -- platform helpers ------------------------------------------------

    @staticmethod
    def _open_path(path) -> None:
        p = str(path)
        try:
            if sys.platform == "win32":
                os.startfile(p)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.run(["open", p])
            else:
                subprocess.run(["xdg-open", p])
        except Exception:
            pass

    @staticmethod
    def _reveal(path) -> None:
        try:
            if sys.platform == "win32":
                subprocess.run(["explorer", "/select,", str(path)])
            elif sys.platform == "darwin":
                subprocess.run(["open", "-R", str(path)])
            else:
                subprocess.run(["xdg-open", str(Path(path).parent)])
        except Exception:
            pass

    # -- shutdown --------------------------------------------------------

    def closeEvent(self, event) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(3000)
        g = self.geometry()
        self._config.window_geometry = f"{g.x()},{g.y()},{g.width()},{g.height()}"
        self._config.save()
        super().closeEvent(event)


def _theme_key(mode: str) -> str:
    return f"theme.{mode}" if mode in ("system", "light", "dark") else "theme.system"