"""Main window: the Light Table layout wired to scanning, filtering and tagging."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QEvent, QModelIndex, QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
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
    QStackedWidget,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..config import Config
from ..core import secret_store
from ..core.cloud_tagger import CloudTagConfig
from ..core.ffmpeg import Preset, default_presets
from ..core.formats import format_duration, format_size
from ..core.probe import find_ffmpeg, find_ffprobe
from ..core.sampling import sample_counts
from ..core.scanner import DEFAULT_EXTENSIONS, VIDEO_EXTENSIONS
from ..core.tagger import find_model
from ..core.vocabulary import ALL_TAG_IDS, DEFAULT_ENABLED, tag_label
from ..export import export_txt
from ..i18n import Translator
from .delegates import RecordDelegate
from .dialog_base import (
    message_box,
    set_dialog_tokens,
    set_dialog_translator,
)
from .cloud_tag_worker import CloudTagWorker
from .empty_state import EmptyState
from .filter_proxy import FilterProxyModel
from .icons import brand_pixmap, line_icon
from .motion import REVEAL, animate_height, set_faded_visible
from .select_field import SelectField
from .table_model import FileRecordModel
from .tag_worker import TagWorker
from .theme import apply_theme, palette_for, resolve_mode
from .titlebar import FolderChip, TitleBar
from .toast import Toast
from .widgets import (
    BatchCommandDialog, FormatConvertDialog, MyTagsDialog, SettingsDialog,
)
from .widgets.mode_switch import AiModeSwitch, UploadConfirmDialog
from .worker import ScanWorker

_THEME_MODES = ("system", "light", "dark")

# Sort dropdown options: (i18n column key -> model column).
_SORT_FIELDS = (
    ("col.name", FileRecordModel.COL_NAME),
    ("col.size", FileRecordModel.COL_SIZE),
    ("col.duration", FileRecordModel.COL_DURATION),
    ("col.bitrate", FileRecordModel.COL_BITRATE),
    ("col.format", FileRecordModel.COL_FORMAT),
    ("col.mtime", FileRecordModel.COL_MTIME),
    ("col.tags", FileRecordModel.COL_TAGS),
)

_COLUMN_WIDTHS = {
    FileRecordModel.COL_CHECK: 40,
    FileRecordModel.COL_SIZE: 96,
    FileRecordModel.COL_DURATION: 92,
    FileRecordModel.COL_BITRATE: 96,
    FileRecordModel.COL_FORMAT: 86,
    FileRecordModel.COL_MTIME: 132,
    FileRecordModel.COL_TAGS: 200,
}

_RESIZE_BORDER = 6

logger = logging.getLogger(__name__)

# WM_NCHITTEST results.
_HTLEFT, _HTRIGHT, _HTTOP, _HTBOTTOM = 10, 11, 12, 15
_HTTOPLEFT, _HTTOPRIGHT, _HTBOTTOMLEFT, _HTBOTTOMRIGHT = 13, 14, 16, 17


def _restore_owned_dialog(owner: int, pid: int) -> None:
    """Restore a shell file dialog that opens maximized and center it.

    Windows keeps the common-dialog placement per executable. Once that entry
    is stored maximized, IFileDialog fills the screen and has no resize border
    until it is restored. The native dialog runs its own modal message loop, so
    this polls from a helper thread instead of relying on Qt timers.
    """
    try:
        import ctypes
        import time
        from ctypes import wintypes
    except Exception:
        return

    user32 = ctypes.windll.user32
    try:
        user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.IsZoomed.argtypes = [wintypes.HWND]
        user32.IsZoomed.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND, ctypes.POINTER(wintypes.DWORD)
        ]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.GetWindowPlacement.argtypes = [wintypes.HWND, ctypes.c_void_p]
        user32.GetWindowPlacement.restype = wintypes.BOOL
        user32.SetWindowPlacement.argtypes = [wintypes.HWND, ctypes.c_void_p]
        user32.SetWindowPlacement.restype = wintypes.BOOL
        user32.SystemParametersInfoW.argtypes = [
            wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT
        ]
    except Exception:
        pass

    class WINDOWPLACEMENT(ctypes.Structure):
        _fields_ = [
            ("length", wintypes.UINT),
            ("flags", wintypes.UINT),
            ("showCmd", wintypes.UINT),
            ("ptMinPosition", wintypes.POINT),
            ("ptMaxPosition", wintypes.POINT),
            ("rcNormalPosition", wintypes.RECT),
        ]

    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def find_dialog() -> int:
        found: list[int] = []

        def callback(hwnd, _):
            if not user32.IsWindowVisible(hwnd):
                return True
            cls = ctypes.create_unicode_buffer(32)
            user32.GetClassNameW(hwnd, cls, 32)
            if cls.value != "#32770":
                return True
            window_pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
            if window_pid.value != pid:
                return True
            found.append(int(hwnd))
            return False

        user32.EnumWindows(enum_proc(callback), 0)
        return found[0] if found else 0

    deadline = time.monotonic() + 4.0
    hwnd = 0
    while time.monotonic() < deadline:
        hwnd = find_dialog()
        if hwnd:
            break
        time.sleep(0.02)
    if not hwnd or not user32.IsZoomed(hwnd):
        return

    placement = WINDOWPLACEMENT()
    placement.length = ctypes.sizeof(placement)
    width = height = 0
    if user32.GetWindowPlacement(wintypes.HWND(hwnd), ctypes.byref(placement)):
        normal = placement.rcNormalPosition
        width = normal.right - normal.left
        height = normal.bottom - normal.top

    dialog = wintypes.RECT()
    work = wintypes.RECT()
    user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(dialog))
    user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(work), 0)  # SPI_GETWORKAREA
    if width <= 0 or height <= 0:
        width = dialog.right - dialog.left
        height = dialog.bottom - dialog.top
    max_w = max(480, work.right - work.left - 24)
    max_h = max(360, work.bottom - work.top - 24)
    width = min(width, max_w)
    height = min(height, max_h)

    owner_rect = wintypes.RECT()
    user32.GetWindowRect(wintypes.HWND(owner), ctypes.byref(owner_rect))
    cx = (owner_rect.left + owner_rect.right) // 2
    cy = (owner_rect.top + owner_rect.bottom) // 2
    x = max(work.left + 12, min(cx - width // 2, work.right - width - 12))
    y = max(work.top + 12, min(cy - height // 2, work.bottom - height - 12))

    # Restore and reposition in one call so a cross-thread ShowWindow cannot
    # race with SetWindowPos and leave the dialog where it was.
    placement.showCmd = 1  # SW_SHOWNORMAL
    placement.flags = 0
    placement.rcNormalPosition = wintypes.RECT(x, y, x + width, y + height)
    user32.SetWindowPlacement(wintypes.HWND(hwnd), ctypes.byref(placement))


class _TableView(QTableView):
    """Table view that reports a left-button rubber-band selection as a drag.

    A plain click still only selects; once the mouse moves past the drag
    threshold and is released, ``dragged`` fires carrying the model index the
    drag started on. The window uses that anchor to decide check vs uncheck.
    """

    dragged = Signal(object)   # proxy index the drag started on (may be invalid)
    toggleRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._press_pos = None
        self._press_index = QModelIndex()
        self._dragging = False
        self._hover_row = -1
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

    def _set_hover_row(self, row: int) -> None:
        if row == self._hover_row:
            return
        self._hover_row = row
        self.viewport().update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_pos = event.pos()
            self._press_index = self.indexAt(event.pos())
            self._dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        index = self.indexAt(event.pos())
        self._set_hover_row(index.row() if index.isValid() else -1)
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

    def leaveEvent(self, event):
        self._set_hover_row(-1)
        super().leaveEvent(event)

    def keyPressEvent(self, event):
        selection = self.selectionModel()
        if event.key() == Qt.Key_Space and selection is not None and selection.hasSelection():
            self.toggleRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class MainWindow(QMainWindow):
    def __init__(self, tr: Translator, config: Config, parent=None):
        super().__init__(parent)
        self._translator = tr
        self._tr = tr.tr                # callable tr(key, **kwargs)
        self._config = config
        self._worker: ScanWorker | None = None
        self._tag_worker: TagWorker | None = None
        self._ffprobe_path = find_ffprobe()
        self._ffmpeg_path = find_ffmpeg(self._ffprobe_path)
        self._filter_formats: list[str] = []   # extensions currently selectable
        self._sort_ascending = True
        self._syncing_sort = False
        self._scanning = False
        self._has_scanned = False
        self._palette = palette_for(config.theme_mode)
        self._dwm_done = False
        self._mode = (
            config.recognition_mode
            if config.recognition_mode in ("local", "hybrid", "cloud")
            else "local"
        )
        self._first_run_checked = False

        self.setWindowTitle("Media Filter")
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setMinimumSize(980, 620)

        self._build_ui()
        self._apply_palette()
        self._connect_signals()
        self.retranslate()

        # restore saved state
        if config.window_geometry:
            self._restore_geometry(config.window_geometry)
        else:
            self.resize(1200, 760)
            self._center_on_screen()

        if config.window_maximized:
            self.setWindowState(self.windowState() | Qt.WindowMaximized)

    # -- geometry --------------------------------------------------------

    def _center_on_screen(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        frame = self.frameGeometry()
        self.move(
            avail.left() + (avail.width() - frame.width()) // 2,
            avail.top() + (avail.height() - frame.height()) // 2,
        )

    def _restore_geometry(self, text: str) -> None:
        try:
            x, y, w, h = (int(v) for v in text.split(","))
        except (ValueError, TypeError):
            self.resize(1200, 760)
            self._center_on_screen()
            return
        if w < 200 or h < 200:
            self.resize(1200, 760)
            self._center_on_screen()
            return
        screen = QGuiApplication.screenAt(QPoint(x, y))
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            self.setGeometry(x, y, w, h)
            return
        avail = screen.availableGeometry()
        w = min(w, avail.width())
        h = min(h, avail.height())
        x = max(avail.left(), min(x, avail.left() + avail.width() - w))
        y = max(avail.top(), min(y, avail.top() + avail.height() - h))
        self.setGeometry(x, y, w, h)

    # -- construction ----------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("Root")
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._build_titlebar()
        root.addWidget(self._titlebar)

        self._build_filterbar()
        root.addWidget(self._filter_bar)

        self._build_content()
        root.addWidget(self._content, 1)

        self._build_statusbar()
        root.addWidget(self._status_bar)

        self.setCentralWidget(central)
        self._toast = Toast(central)
        self._toast.set_tokens(self._palette)

        find = QShortcut(QKeySequence.StandardKey.Find, self)
        find.activated.connect(self._focus_search)
        settings = QShortcut(QKeySequence("Ctrl+,"), self)
        settings.activated.connect(self.open_settings)

    def _build_titlebar(self) -> None:
        self._titlebar = TitleBar()

        self._brand = QLabel()
        self._brand.setFixedSize(22, 22)
        self._brand.setPixmap(
            brand_pixmap(22, self._palette["accent"], self._palette["on_accent"])
        )

        self._brand_name = QLabel("Media Filter")
        self._brand_name.setObjectName("BrandName")

        self._folder_chip = FolderChip()
        self._folder_chip.setMaximumWidth(220)
        self._folder_chip.clicked.connect(self.open_folder)

        self._search = QLineEdit()
        self._search.setObjectName("Search")
        self._search.setFixedHeight(34)
        self._search.setMinimumWidth(180)
        self._search.setMaximumWidth(280)
        self._search.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self._search.setClearButtonEnabled(True)
        self._search_action = self._search.addAction(
            line_icon("search", self._palette["ink_3"], 15),
            QLineEdit.ActionPosition.LeadingPosition,
        )

        self._refresh_btn = QToolButton()
        self._refresh_btn.setProperty("variant", "icon")
        self._refresh_btn.setFixedSize(34, 34)
        self._refresh_btn.setIconSize(QSize(16, 16))
        self._refresh_btn.clicked.connect(self.refresh_current_folder)

        self._theme_btn = QToolButton()
        self._theme_btn.setProperty("variant", "icon")
        self._theme_btn.setFixedSize(34, 34)
        self._theme_btn.setIconSize(QSize(16, 16))
        self._theme_btn.clicked.connect(self.cycle_theme)

        self._settings_btn = QToolButton()
        self._settings_btn.setObjectName("SettingsButton")
        self._settings_btn.setProperty("variant", "icon")
        self._settings_btn.setFixedSize(34, 34)
        self._settings_btn.setIconSize(QSize(16, 16))
        self._settings_btn.clicked.connect(self.open_settings)

        self._lang_btn = QPushButton()
        self._lang_btn.setProperty("variant", "ghost")
        self._lang_btn.setFixedHeight(34)
        self._lang_btn.setMinimumWidth(46)
        self._lang_btn.clicked.connect(self.toggle_language)

        self._open_btn = QPushButton()
        self._open_btn.setProperty("variant", "primary")
        self._open_btn.setFixedHeight(36)
        self._open_btn.setIconSize(QSize(15, 15))
        self._open_btn.setCursor(Qt.PointingHandCursor)
        self._open_btn.clicked.connect(self.open_folder)

        self._titlebar.add_widget(self._brand)
        self._titlebar.add_widget(self._brand_name)
        self._titlebar.add_widget(self._folder_chip)
        self._titlebar.add_stretch()
        self._titlebar.add_widget(self._search)
        self._titlebar.add_widget(self._refresh_btn)
        self._titlebar.add_widget(self._settings_btn)
        self._titlebar.add_widget(self._theme_btn)
        self._titlebar.add_widget(self._lang_btn)
        self._titlebar.add_widget(self._open_btn)

        self._titlebar.minimizeRequested.connect(self._minimize)
        self._titlebar.maximizeRequested.connect(self.toggle_maximize)
        self._titlebar.closeRequested.connect(self.close)

    def _build_filterbar(self) -> None:
        self._filter_bar = QWidget()
        self._filter_bar.setObjectName("FilterBar")
        self._filter_bar.setAttribute(Qt.WA_StyledBackground, True)
        self._filter_bar.setFixedHeight(44)
        row = QHBoxLayout(self._filter_bar)
        row.setContentsMargins(16, 5, 16, 5)
        row.setSpacing(8)

        self._filter_combo = SelectField()
        self._filter_combo.setFixedWidth(144)

        self._tag_combo = SelectField()
        self._tag_combo.setFixedWidth(144)

        self._sort_combo = SelectField()
        self._sort_combo.setFixedWidth(150)
        self._sort_combo.set_popup_min_width(212)

        divider = QFrame()
        divider.setObjectName("FilterDivider")
        divider.setFixedSize(1, 20)

        self._order_btn = QToolButton()
        self._order_btn.setObjectName("OrderButton")
        self._order_btn.setFixedSize(34, 34)
        self._order_btn.setIconSize(QSize(15, 15))
        self._order_btn.setCursor(Qt.PointingHandCursor)
        self._order_btn.clicked.connect(self._toggle_sort_order)

        row.addWidget(self._filter_combo)
        row.addWidget(self._tag_combo)
        row.addWidget(divider)
        row.addWidget(self._sort_combo)
        row.addWidget(self._order_btn)

        self._threads = SelectField()
        self._threads.set_number_grid(True)
        self._threads.setFixedWidth(96)
        self._threads.addItems([str(i) for i in range(1, 33)])
        self._threads.setCurrentIndex(
            max(1, min(32, self._config.scan_threads)) - 1
        )
        self._threads.setToolTip("1 – 32")
        row.addWidget(self._threads)

        self._select_all_btn = QPushButton()
        self._select_all_btn.setProperty("variant", "ghost")
        self._select_all_btn.setFixedHeight(34)
        self._select_all_btn.setCursor(Qt.PointingHandCursor)
        self._select_all_btn.clicked.connect(self.select_all)
        self._deselect_all_btn = QPushButton()
        self._deselect_all_btn.setProperty("variant", "ghost")
        self._deselect_all_btn.setFixedHeight(34)
        self._deselect_all_btn.setCursor(Qt.PointingHandCursor)
        self._deselect_all_btn.clicked.connect(self.deselect_all)
        row.addWidget(self._select_all_btn)
        row.addWidget(self._deselect_all_btn)

        row.addStretch(1)

        self._stop_btn = QPushButton()
        self._stop_btn.setObjectName("StopButton")
        self._stop_btn.setFixedHeight(34)
        self._stop_btn.setCursor(Qt.PointingHandCursor)
        self._stop_btn.setVisible(False)
        self._stop_btn.clicked.connect(self.cancel_scan)

        self._ai = AiModeSwitch(self._tr, self._palette, self)
        self._ai.set_mode(self._mode)
        self._ai.set_custom_count(len(self._config.custom_labels))
        self._ai.runRequested.connect(self.on_ai_clicked)
        self._ai.modeChanged.connect(self._on_mode_changed)
        self._ai.tagsRequested.connect(self.open_my_tags)
        self._ai.settingsRequested.connect(self.open_settings)

        row.addWidget(self._stop_btn)
        row.addWidget(self._ai)

    def _build_content(self) -> None:
        self._content = QWidget()
        self._content.setObjectName("ContentArea")
        self._content.setAttribute(Qt.WA_StyledBackground, True)
        col = QVBoxLayout(self._content)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)

        self._scan_line = QProgressBar()
        self._scan_line.setObjectName("ScanLine")
        self._scan_line.setFixedHeight(2)
        self._scan_line.setTextVisible(False)
        self._scan_line.setRange(0, 1)
        self._scan_line.setValue(0)
        self._hide_progress()
        col.addWidget(self._scan_line)

        self._guide = QWidget()
        self._guide.setObjectName("GuideBar")
        self._guide.setAttribute(Qt.WA_StyledBackground, True)
        self._guide.setFixedHeight(40)
        guide_row = QHBoxLayout(self._guide)
        guide_row.setContentsMargins(16, 0, 10, 0)
        guide_row.setSpacing(10)
        self._guide_text = QLabel()
        self._guide_text.setObjectName("GuideText")
        guide_row.addWidget(self._guide_text)
        self._guide_action = QPushButton()
        self._guide_action.setObjectName("GuideAction")
        self._guide_action.setCursor(Qt.PointingHandCursor)
        self._guide_action.clicked.connect(self.open_settings)
        guide_row.addWidget(self._guide_action)
        guide_row.addStretch(1)
        self._guide_close = QToolButton()
        self._guide_close.setObjectName("GuideClose")
        self._guide_close.setFixedSize(24, 24)
        self._guide_close.setIconSize(QSize(14, 14))
        self._guide_close.setCursor(Qt.PointingHandCursor)
        self._guide_close.clicked.connect(self._dismiss_guide)
        guide_row.addWidget(self._guide_close)
        self._guide.setVisible(False)
        self._guide_open = False
        col.addWidget(self._guide)

        self._model = FileRecordModel(self)
        self._proxy = FilterProxyModel(self)
        self._proxy.setSourceModel(self._model)

        self._view = _TableView()
        self._view.setModel(self._proxy)
        self._delegate = RecordDelegate(self._palette, self._view)
        self._view.setItemDelegate(self._delegate)
        self._view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._view.setSortingEnabled(True)
        self._view.setAlternatingRowColors(False)
        self._view.setShowGrid(False)
        self._view.setWordWrap(False)
        self._view.setTextElideMode(Qt.ElideRight)
        self._view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._view.setContextMenuPolicy(Qt.CustomContextMenu)
        self._view.setFrameShape(QFrame.NoFrame)
        self._view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self._view.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self._view.setCornerButtonEnabled(False)

        vheader = self._view.verticalHeader()
        vheader.setVisible(False)
        vheader.setDefaultSectionSize(RecordDelegate.ROW_HEIGHT)
        vheader.setSectionResizeMode(QHeaderView.Fixed)

        header = self._view.horizontalHeader()
        header.setFixedHeight(34)
        header.setSectionsClickable(True)
        header.setHighlightSections(False)
        header.setSortIndicatorShown(False)
        header.setStretchLastSection(False)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header_font = QFont(self.font())
        header_font.setPixelSize(11)
        header_font.setWeight(QFont.DemiBold)
        header_font.setLetterSpacing(QFont.AbsoluteSpacing, 0.4)
        header.setFont(header_font)
        header.setSectionResizeMode(FileRecordModel.COL_NAME, QHeaderView.Stretch)
        for column, width in _COLUMN_WIDTHS.items():
            header.setSectionResizeMode(column, QHeaderView.Interactive)
            header.resizeSection(column, width)

        self._empty = EmptyState()
        self._empty.primaryClicked.connect(self.open_folder)
        self._empty.linkClicked.connect(self._open_last_folder)

        # A separate page for "filters hid everything": different copy and a
        # one-click reset instead of "open a folder".
        self._empty_filter = EmptyState()
        self._empty_filter.primaryClicked.connect(self._clear_filters)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._view)
        self._stack.addWidget(self._empty)
        self._stack.addWidget(self._empty_filter)
        col.addWidget(self._stack, 1)

    def _build_statusbar(self) -> None:
        self._status_bar = QWidget()
        self._status_bar.setObjectName("StatusBar")
        self._status_bar.setAttribute(Qt.WA_StyledBackground, True)
        self._status_bar.setFixedHeight(48)
        row = QHBoxLayout(self._status_bar)
        row.setContentsMargins(16, 0, 16, 0)
        row.setSpacing(18)

        self._stat_keys: dict[str, QLabel] = {}
        self._files_value = self._add_stat(row, "files", 36)
        self._selected_value = self._add_stat(row, "selected", 28, accent=True)
        self._duration_value = self._add_stat(row, "duration", 58)
        self._size_value = self._add_stat(row, "size", 70)

        self._status_label = QLabel()
        self._status_label.setObjectName("StatusMessage")
        self._status_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self._status_label.setMinimumWidth(180)
        self._status_label.setMaximumWidth(520)
        row.addWidget(self._status_label)
        row.addStretch(1)

        self._export_btn = QPushButton()
        self._export_btn.setProperty("variant", "ghost")
        self._export_btn.setFixedHeight(34)
        self._export_btn.setCursor(Qt.PointingHandCursor)
        self._export_btn.clicked.connect(self.export_report)

        self._batch_btn = QPushButton()
        self._batch_btn.setProperty("variant", "ghost")
        self._batch_btn.setFixedHeight(34)
        self._batch_btn.setCursor(Qt.PointingHandCursor)
        self._batch_btn.clicked.connect(self.open_batch)

        self._convert_btn = QPushButton()
        self._convert_btn.setProperty("variant", "ghost")
        self._convert_btn.setFixedHeight(34)
        self._convert_btn.setCursor(Qt.PointingHandCursor)
        self._convert_btn.clicked.connect(self.open_convert)

        row.addWidget(self._export_btn)
        row.addWidget(self._batch_btn)
        row.addWidget(self._convert_btn)

    def _add_link(self, row: QHBoxLayout, slot) -> QPushButton:
        button = QPushButton()
        button.setObjectName("SelectionLink")
        button.setCursor(Qt.PointingHandCursor)
        button.setFixedHeight(22)
        button.clicked.connect(slot)
        row.addWidget(button)
        return button

    def _add_stat(self, row: QHBoxLayout, key: str, width: int, accent: bool = False) -> QLabel:
        box = QWidget()
        line = QHBoxLayout(box)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(6)
        label = QLabel()
        label.setObjectName("StatKey")
        value = QLabel("0")
        value.setObjectName("StatValueAccent" if accent else "StatValue")
        value.setMinimumWidth(width)
        line.addWidget(label)
        line.addWidget(value)
        row.addWidget(box)
        self._stat_keys[key] = label
        return value

    def _connect_signals(self) -> None:
        self._search.textChanged.connect(self._proxy.set_search)
        self._search.textChanged.connect(self._refresh_stats)
        self._search.textChanged.connect(self._sync_empty_state)
        self._filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        self._tag_combo.currentIndexChanged.connect(self._on_tag_filter_changed)
        self._sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        self._view.horizontalHeader().sortIndicatorChanged.connect(self._on_header_sort_changed)
        self._model.checkedChanged.connect(self._refresh_stats)
        self._view.clicked.connect(self._on_clicked)
        self._view.doubleClicked.connect(self._on_double_clicked)
        self._view.dragged.connect(self._on_drag_finished)
        self._view.toggleRequested.connect(self._toggle_selected_checks)
        self._view.customContextMenuRequested.connect(self._show_context_menu)
        self._view.selectionModel().selectionChanged.connect(self._refresh_stats)
        self._view.installEventFilter(self)

    # -- i18n / theme ----------------------------------------------------

    def retranslate(self) -> None:
        tr = self._tr
        set_dialog_translator(tr)
        self.setWindowTitle(tr("app.title"))

        text_map = {
            "toolbar.open_folder": self._open_btn,
            "toolbar.export": self._export_btn,
            "toolbar.batch": self._batch_btn,
            "toolbar.convert": self._convert_btn,
            "toolbar.cancel": self._stop_btn,
        }
        for key, widget in text_map.items():
            widget.setText(tr(key))

        self._search.setPlaceholderText(tr("toolbar.search"))
        self._filter_combo.setLabel(tr("field.format"))
        self._tag_combo.setLabel(tr("field.tag"))
        self._sort_combo.setLabel(tr("field.sort"))
        self._threads.setLabel(tr("field.threads"))
        self._refresh_btn.setToolTip(tr("toolbar.refresh"))
        self._settings_btn.setToolTip(tr("toolbar.settings"))
        self._open_btn.setToolTip(tr("toolbar.open_folder"))
        self._lang_btn.setText(tr("lang.toggle"))
        self._titlebar.set_button_texts(
            tr("window.minimize"), tr("window.maximize"),
            tr("window.restore"), tr("window.close"),
        )
        self._delegate.set_strings(tr("tag.failed"))
        self._view.viewport().update()
        self._stat_keys["files"].setText(tr("stat.files_label"))
        self._stat_keys["selected"].setText(tr("stat.selected_label"))
        self._stat_keys["duration"].setText(tr("stat.duration_label"))
        self._stat_keys["size"].setText(tr("stat.size_label"))
        self._select_all_btn.setText(tr("toolbar.select_all"))
        self._deselect_all_btn.setText(tr("toolbar.deselect_all"))
        self._guide_text.setText(tr("guide.text"))
        self._guide_action.setText(tr("guide.open"))
        self._guide_close.setToolTip(tr("guide.dismiss"))
        self._guide_close.setIcon(line_icon("close", self._palette["ink_3"], 14))
        self._ai.retranslate(tr)
        self._update_order_button()
        self._update_theme_button()
        self._update_ai_button()
        self._update_folder_chip()

        self._model.set_headers([
            "", tr("col.name"), tr("col.size"),
            tr("col.duration"), tr("col.bitrate"), tr("col.format"), tr("col.mtime"),
            tr("col.tags"),
        ])
        self._rebuild_filter_combo()
        self._rebuild_sort_combo()
        self._rebuild_tag_combo()
        self._threads.setFixedWidth(max(96, self._threads.sizeHint().width()))
        self._sync_minimum_width()
        self._refresh_stats()
        self._update_empty_texts()
        self._update_filtered_texts()
        if not self._scanning and (self._tag_worker is None or not self._tag_worker.isRunning()):
            self._set_status(tr("status.ready"))
        self._sync_empty_state()

    def _sync_minimum_width(self) -> None:
        """980 px is tuned for Chinese; longer translations (English) grow the
        window minimum instead of squeezing the toolbar controls."""
        bars = [bar for bar in (self._titlebar, self._filter_bar, self._status_bar)
                if bar is not None]
        for widget in (self._ai.main, self._ai, *bars):
            layout = widget.layout()
            if layout is not None:
                layout.invalidate()
                layout.activate()
        needed = max([980] + [bar.minimumSizeHint().width() for bar in bars])
        self.setMinimumWidth(needed)

    def cycle_theme(self) -> None:
        idx = _THEME_MODES.index(self._config.theme_mode)
        self._config.theme_mode = _THEME_MODES[(idx + 1) % len(_THEME_MODES)]
        self._config.save()
        app = QApplication.instance()
        if isinstance(app, QApplication):
            self._palette = apply_theme(app, self._config.theme_mode)
        self._apply_palette()
        self.retranslate()

    def toggle_language(self) -> None:
        new = "en" if self._translator.language == "zh" else "zh"
        self._translator.set_language(new)
        self._config.language = new
        self._config.save()
        self.retranslate()

    def _apply_palette(self) -> None:
        p = self._palette
        set_dialog_tokens(p)
        self._brand.setPixmap(brand_pixmap(22, p["accent"], p["on_accent"]))
        self._titlebar.set_tokens(p)
        self._folder_chip.set_tokens(p)
        self._delegate.set_tokens(p)
        self._empty.set_tokens(p)
        self._empty_filter.set_tokens(p)
        self._toast.set_tokens(p)
        for field in (
            self._filter_combo,
            self._tag_combo,
            self._sort_combo,
            self._threads,
        ):
            field.set_tokens(p)
        self._search_action.setIcon(line_icon("search", p["ink_3"], 15))
        self._refresh_btn.setIcon(line_icon("refresh", p["ink_3"], 16))
        self._settings_btn.setIcon(line_icon("settings", p["ink_3"], 16))
        self._open_btn.setIcon(line_icon("folder", p["on_accent"], 15))
        self._guide_close.setIcon(line_icon("close", p["ink_3"], 14))
        self._ai.set_tokens(p)
        self._update_ai_button()
        self._update_theme_button()
        self._update_order_button()
        self._view.viewport().update()

    def _update_theme_button(self) -> None:
        resolved = resolve_mode(self._config.theme_mode)
        name = "moon" if resolved == "light" else "sun"
        self._theme_btn.setIcon(line_icon(name, self._palette["ink_3"], 16))
        self._theme_btn.setToolTip(
            self._tr("theme.toggle") + ": " + self._tr(_theme_key(self._config.theme_mode))
        )

    def _update_ai_button(self) -> None:
        running = self._tag_worker is not None and self._tag_worker.isRunning()
        self._ai.set_busy(running)
        self._ai.set_mode(self._mode)
        self._ai.setToolTip(self._tr("toolbar.ai_tip", mode=self._tr(
            f"mode.{self._mode}.name"
        )))

    def _update_folder_chip(self) -> None:
        folder = self._config.last_folder
        if folder and Path(folder).is_dir():
            path = Path(folder)
            name = path.name or str(path)
            parent = str(path.parent) if path.parent != path else ""
            self._folder_chip.set_folder(name, parent)
            self._folder_chip.setToolTip(str(path))
        else:
            self._folder_chip.set_folder(self._tr("folder.none"), "")
            self._folder_chip.setToolTip(self._tr("toolbar.open_folder"))

    def _set_status(self, text: str) -> None:
        self._status_label.setText(text or "")
        self._status_label.setToolTip(text or "")

    # -- toast -----------------------------------------------------------

    def _show_toast(self, text: str) -> None:
        toast = getattr(self, "_toast", None)
        if toast is None or not text:
            return
        toast.show_message(text)
        self._place_toast()

    def _place_toast(self) -> None:
        toast = getattr(self, "_toast", None)
        if toast is None:
            return
        parent = toast.parentWidget()
        if parent is None:
            return
        toast.adjustSize()
        top = self._status_bar.mapTo(parent, QPoint(0, 0)).y()
        x = max(8, (parent.width() - toast.width()) // 2)
        y = max(8, top - toast.height() - 12)
        toast.move(x, y)
        toast.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place_toast()

    def _focus_search(self) -> None:
        self._search.setFocus(Qt.ShortcutFocusReason)
        self._search.selectAll()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape and self._search.text():
            self._search.clear()
            self._search.clearFocus()
            event.accept()
            return
        super().keyPressEvent(event)

    def eventFilter(self, watched, event):
        # The table view consumes Ctrl+A itself (row highlight only). Catch it
        # first so the shortcut also ticks the checkboxes, matching the button.
        if (
            watched is self._view
            and event.type() == QEvent.Type.KeyPress
            and event.key() == Qt.Key.Key_A
            and event.modifiers() == Qt.KeyboardModifier.ControlModifier
        ):
            self.select_all()
            event.accept()
            return True
        return super().eventFilter(watched, event)

    # -- filter combo ----------------------------------------------------

    def _rebuild_filter_combo(self) -> None:
        current = self._filter_for_index(self._filter_combo.currentIndex())
        self._filter_combo.blockSignals(True)
        self._filter_combo.clear()
        self._filter_combo.addItem(self._tr("value.all"))
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
        self._refresh_stats()
        self._sync_empty_state()

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
        return col if isinstance(col, int) else FileRecordModel.COL_NAME

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
        name = "arrow-up" if self._sort_ascending else "arrow-down"
        self._order_btn.setIcon(line_icon(name, self._palette["ink_2"], 15))
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

    # -- empty state -----------------------------------------------------

    def _update_empty_texts(self) -> None:
        tr = self._tr
        if self._has_scanned:
            title = tr("empty.no_files_title")
            body = tr("empty.no_files_body")
        else:
            title = tr("empty.title")
            body = tr("empty.body")
        link = ""
        tip = ""
        folder = self._config.last_folder
        if folder and Path(folder).is_dir():
            link = tr("empty.last_folder", path=folder)
            tip = tr("empty.link_tip", path=folder)
        self._empty.set_content(title, body, tr("toolbar.open_folder"), link, tip)

    def _sync_empty_state(self) -> None:
        filtered = (
            self._model.rowCount() > 0
            and self._proxy.rowCount() == 0
            and not self._scanning
        )
        if self._model.rowCount() == 0 and not self._scanning:
            self._update_empty_texts()
            self._stack.setCurrentWidget(self._empty)
        elif filtered:
            self._update_filtered_texts()
            self._stack.setCurrentWidget(self._empty_filter)
        else:
            self._stack.setCurrentWidget(self._view)

    def _update_filtered_texts(self) -> None:
        tr = self._tr
        self._empty_filter.set_content(
            tr("empty.filtered_title"),
            tr("empty.filtered_body"),
            tr("empty.clear_filters"),
            primary_icon="refresh",
        )

    def _clear_filters(self) -> None:
        """Reset search and both dropdowns, then show every row again."""
        tr = self._tr
        widgets = (self._search, self._filter_combo, self._tag_combo)
        for widget in widgets:
            widget.blockSignals(True)
        self._search.clear()
        self._filter_combo.setCurrentIndex(0)
        self._tag_combo.setCurrentIndex(0)
        for widget in widgets:
            widget.blockSignals(False)
        self._proxy.set_search("")
        self._proxy.set_formats(set())
        self._proxy.set_tags(set())
        self._refresh_stats()
        self._sync_empty_state()
        self._show_toast(tr("toast.filters_cleared"))

    def _open_last_folder(self) -> None:
        folder = self._config.last_folder
        if folder and Path(folder).is_dir():
            self.start_scan(folder)
        else:
            self.open_folder()

    # -- scanning --------------------------------------------------------

    def _settle_native_dialog_later(self) -> None:
        """Guard the next shell file dialog against a remembered maximize."""
        if sys.platform != "win32":
            return
        try:
            owner = int(self.winId())
        except Exception:
            return
        threading.Thread(
            target=_restore_owned_dialog,
            args=(owner, os.getpid()),
            name="mf-dialog-placement",
            daemon=True,
        ).start()

    def open_folder(self) -> None:
        self._settle_native_dialog_later()
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
            message_box(self, "info", self._tr("app.title"), self._tr("msg.scanning"))
            return
        if not self._ffprobe_path:
            message_box(self, "warning", self._tr("app.title"), self._tr("msg.ffprobe_missing"))
            return

        self._config.last_folder = folder
        self._config.scan_threads = self._thread_count()
        self._config.save()

        self._scanning = True
        self._has_scanned = False
        self._model.set_records([])
        self._filter_formats = []
        self._rebuild_filter_combo()
        self._rebuild_tag_combo()
        self._update_folder_chip()

        self._scan_line.setRange(0, 0)
        self._show_progress()
        self._stop_btn.setVisible(True)
        self._stop_btn.setEnabled(True)
        self._set_status(self._tr("status.preparing"))
        self._sync_empty_state()

        self._worker = ScanWorker(
            folder, self._ffprobe_path, self._thread_count(),
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

    def _thread_count(self) -> int:
        try:
            return int(self._threads.currentText())
        except (TypeError, ValueError):
            return self._config.scan_threads

    def _on_progress(self, done: int, total: int) -> None:
        self._scan_line.setRange(0, max(1, total))
        self._scan_line.setValue(done)
        self._set_status(self._tr("status.scanning", done=done, total=total))

    def _show_progress(self) -> None:
        set_faded_visible(self._scan_line, True, REVEAL)

    def _hide_progress(self) -> None:
        set_faded_visible(self._scan_line, False, REVEAL)

    def _finish_scan(self) -> None:
        self._scanning = False
        self._hide_progress()
        self._stop_btn.setVisible(False)
        self._stop_btn.setEnabled(False)
        self._worker = None

    def _on_scan_done(self, records: list) -> None:
        self._has_scanned = True
        self._finish_scan()
        self._model.set_records(records)
        self._populate_filter_formats(records)
        self._rebuild_tag_combo()
        self._apply_sort()
        errors = sum(1 for r in records if r.error)
        logger.info("scan finished: files=%d errors=%d", len(records), errors)
        self._set_status(self._tr("status.done", files=len(records), errors=errors))
        self._sync_empty_state()

    def _on_scan_aborted(self, records: list) -> None:
        self._has_scanned = bool(records)
        self._finish_scan()
        if records:
            self._model.set_records(records)
            self._populate_filter_formats(records)
            self._rebuild_tag_combo()
            self._apply_sort()
        self._set_status(self._tr("status.cancelled"))
        logger.info("scan cancelled: partial=%d", len(records))
        self._sync_empty_state()

    def _on_scan_failed(self, message: str) -> None:
        logger.error("scan failed: %s", message)
        self._finish_scan()
        self._set_status(message)
        self._sync_empty_state()
        message_box(self, "critical", self._tr("app.title"), message)

    # -- AI tagging ------------------------------------------------------

    def on_ai_clicked(self) -> None:
        if self._tag_worker is not None and self._tag_worker.isRunning():
            self._tag_worker.cancel()
            return
        self._request_ai()

    def _ai_targets(self) -> list:
        targets = self._target_records()
        if not targets:
            targets = self._model.records()
        return [
            r for r in targets
            # has_video is authoritative; the extension fallback keeps files
            # whose metadata could not be read from silently disappearing.
            if r.has_video or (r.metadata is None and r.extension in VIDEO_EXTENSIONS)
        ]

    def _on_mode_changed(self, mode: str) -> None:
        if mode not in ("local", "hybrid", "cloud"):
            mode = "local"
        previous = self._mode
        self._mode = mode
        # One source of truth: the pill and the settings page edit the same
        # value, and switching here also becomes the next launch default.
        self._config.recognition_mode = mode
        self._config.save()
        self._update_ai_button()
        if mode != previous:
            self._show_toast(self._tr(
                "toast.mode_switched", mode=self._tr(f"mode.{mode}.name")
            ))

    def _apply_saved_mode(self) -> None:
        """Show the mode saved in the settings page on the main window pill."""
        mode = self._config.recognition_mode
        self._mode = mode if mode in ("local", "hybrid", "cloud") else "local"
        self._ai.set_mode(self._mode)
        self._update_ai_button()

    def _request_ai(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            message_box(self, "info", self._tr("app.title"), self._tr("msg.ai_running"))
            return
        if self._tag_worker is not None and self._tag_worker.isRunning():
            return
        targets = self._ai_targets()
        if not targets:
            message_box(self, "info", self._tr("app.title"), self._tr("msg.ai_no_targets"))
            return

        mode = self._ai.mode()
        self._mode = mode
        if mode == "local":
            self.start_tagging(targets)
            return
        if mode == "hybrid" and not self._config.custom_labels:
            self._set_status(self._tr("status.hybrid_fallback"))
            self.start_tagging(targets)
            return

        labels = [
            tag_label(self._tr, tag_id)
            for tag_id in (self._config.tag_palette or list(DEFAULT_ENABLED))
            if tag_id in ALL_TAG_IDS
        ]
        video_counts = sample_counts(
            (rec.duration for rec in targets), self._config.frame_policy
        )
        frames = sum(video_counts)
        dialog = UploadConfirmDialog(
            len(targets), frames, mode,
            self._config.cloud_base_url,
            self._config.cloud_model or self._tr("settings.model_none"),
            labels, self._tr, self, tokens=self._palette,
            custom_labels=list(self._config.custom_labels),
            on_labels_saved=self._save_confirm_labels,
            frame_counts=video_counts,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.start_cloud_tagging(targets, mode)

    def _save_confirm_labels(self, labels: list[str]) -> None:
        """Edits made from the upload card's My labels entry are global."""
        self._config.custom_labels = list(labels)
        self._config.save()

    def start_cloud_tagging(self, targets: list, mode: str) -> None:
        """Cloud / hybrid run: validate config, then start the worker."""
        if self._tag_worker is not None and self._tag_worker.isRunning():
            return
        if not targets:
            return
        try:
            key = secret_store.unprotect(self._config.cloud_api_key_dpapi)
        except secret_store.SecretStoreError as exc:
            message_box(
                self, "warning", self._tr("app.title"),
                self._tr("msg.cloud_key_unreadable", err=str(exc)),
            )
            return
        if not key:
            message_box(
                self, "warning", self._tr("app.title"),
                self._tr("msg.cloud_key_missing"),
            )
            return
        if not self._config.cloud_model:
            message_box(
                self, "warning", self._tr("app.title"),
                self._tr("msg.cloud_model_missing"),
            )
            return
        if self._config.cloud_model_capability == "text":
            message_box(
                self, "warning", self._tr("app.title"),
                self._tr("msg.cloud_text_model"),
            )
            return
        if not self._ffmpeg_path:
            message_box(
                self, "warning", self._tr("app.title"),
                self._tr("msg.ffprobe_missing"),
            )
            return

        local_model = None
        if mode == "hybrid":
            local_model = find_model(self._config.ai_model_path)
            if local_model is None:
                message_box(
                    self, "warning", self._tr("app.title"),
                    self._tr("msg.ai_model_missing"),
                )
                return

        labels = [
            tag_label(self._tr, tag_id)
            for tag_id in (self._config.tag_palette or list(DEFAULT_ENABLED))
            if tag_id in ALL_TAG_IDS
        ]
        labels += list(self._config.custom_labels)
        worker = CloudTagWorker(
            targets, self._ffmpeg_path,
            CloudTagConfig(
                base_url=self._config.cloud_base_url,
                api_key=key,
                model=self._config.cloud_model,
                labels=labels,
            ),
            mode=mode,
            custom_labels=list(self._config.custom_labels),
            sample_frames=self._config.ai_sample_frames,
            frame_policy=self._config.frame_policy,
            enabled_tags=[
                tag_id for tag_id in (self._config.tag_palette or list(DEFAULT_ENABLED))
                if tag_id in ALL_TAG_IDS
            ],
            threads=self._config.ai_threads,
            local_model_path=local_model,
            upload_target_only=self._config.upload_target_only,
            parent=self,
        )
        self._scan_line.setRange(0, max(1, len(targets)))
        self._scan_line.setValue(0)
        self._show_progress()
        self._set_status(self._tr("status.cloud_starting"))
        self._start_tag_worker(worker)

    def _start_tag_worker(self, worker) -> None:
        self._tag_worker = worker
        worker.tagged.connect(self._on_tagged)
        worker.progress.connect(self._on_tag_progress)
        worker.finished_ok.connect(self._on_tag_done)
        worker.failed.connect(self._on_tag_failed)
        worker.start()
        self._update_ai_button()

    def start_tagging(self, targets: list | None = None) -> None:
        if self._worker is not None and self._worker.isRunning():
            message_box(self, "info", self._tr("app.title"), self._tr("msg.ai_running"))
            return
        if self._tag_worker is not None and self._tag_worker.isRunning():
            return

        if targets is None:
            targets = self._ai_targets()
        if not targets:
            message_box(self, "info", self._tr("app.title"), self._tr("msg.ai_no_targets"))
            return

        model = find_model(self._config.ai_model_path)
        if model is None:
            message_box(self, "warning", self._tr("app.title"), self._tr("msg.ai_model_missing"))
            return
        if not self._ffmpeg_path:
            message_box(self, "warning", self._tr("app.title"), self._tr("msg.ffprobe_missing"))
            return

        self._scan_line.setRange(0, max(1, len(targets)))
        self._scan_line.setValue(0)
        self._show_progress()
        self._set_status(self._tr("status.ai_starting"))
        self._update_ai_button()

        self._tag_worker = TagWorker(
            targets, model, self._ffmpeg_path,
            sample_frames=self._config.ai_sample_frames,
            frame_policy=self._config.frame_policy,
            threads=self._config.ai_threads,
            conf=self._config.ai_conf,
            enabled_tags=[
                tag_id for tag_id in (self._config.tag_palette or list(DEFAULT_ENABLED))
                if tag_id in ALL_TAG_IDS
            ],
            parent=self,
        )
        self._start_tag_worker(self._tag_worker)

    def _on_tagged(self, path: str, tags: list, error: str) -> None:
        self._model.update_tags(path, tags, error or None)

    def _on_tag_progress(self, done: int, total: int) -> None:
        self._scan_line.setRange(0, max(1, total))
        self._scan_line.setValue(done)
        self._set_status(self._tr("status.ai_scanning", done=done, total=total))

    def _on_tag_done(self, total: int, tagged_ok: int, failed: int) -> None:
        logger.info("tagging finished: total=%d ok=%d failed=%d", total, tagged_ok, failed)
        self._tag_worker = None
        self._hide_progress()
        self._rebuild_tag_combo()
        self._set_status(self._tr("status.ai_done", n=tagged_ok, failed=failed))
        self._update_ai_button()

    def _on_tag_failed(self, message: str) -> None:
        logger.error("tagging failed: %s", message)
        self._tag_worker = None
        self._hide_progress()
        self._update_ai_button()
        message_box(self, "critical", self._tr("app.title"), self._tr("msg.ai_failed", err=message))

    def _rebuild_tag_combo(self) -> None:
        current = self._tag_combo.currentText() if self._tag_combo.count() else ""
        self._tag_combo.blockSignals(True)
        self._tag_combo.clear()
        self._tag_combo.addItem(self._tr("value.all"))
        self._tag_combo.addItems(self._model.all_tags())
        if current:
            idx = self._tag_combo.findText(current)
            self._tag_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._tag_combo.blockSignals(False)
        self._on_tag_filter_changed()

    def _on_tag_filter_changed(self) -> None:
        if self._tag_combo.currentIndex() <= 0:
            self._proxy.set_tags(set())
        else:
            text = self._tag_combo.currentText()
            self._proxy.set_tags({text} if text else set())
        self._refresh_stats()
        self._sync_empty_state()

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

    def _visible_source_rows(self) -> list[int]:
        """Source rows currently passing the filter (i.e. what the user sees)."""
        return [
            self._proxy.mapToSource(self._proxy.index(row, 0)).row()
            for row in range(self._proxy.rowCount())
        ]

    def select_all(self) -> None:
        # "Select all" ticks the checkboxes too: checking is what drives export
        # and batch actions, so requiring a second click was surprising.
        self._view.selectAll()
        self._model.set_checked(self._visible_source_rows(), True)

    def deselect_all(self) -> None:
        self._view.clearSelection()
        self._model.set_checked(self._visible_source_rows(), False)

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

    def _toggle_selected_checks(self) -> None:
        rows = self._selected_source_rows()
        if not rows:
            return
        self._model.set_checked(rows, not self._model.record(rows[0]).checked)

    def _refresh_stats(self) -> None:
        checked = self._model.checked_records()
        self._files_value.setText(str(self._model.rowCount()))
        self._selected_value.setText(str(len(checked)))
        duration = sum(r.duration for r in checked)
        size = sum(r.size for r in checked)
        self._duration_value.setText(format_duration(duration))
        self._size_value.setText(format_size(size))

        visible = self._visible_source_rows()
        all_checked = bool(visible) and all(
            self._model.record(row).checked for row in visible
        )
        self._select_all_btn.setEnabled(bool(visible) and not all_checked)
        self._deselect_all_btn.setEnabled(bool(checked))

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
            message_box(self, "info", self._tr("app.title"), self._tr("msg.nothing_selected"))
            return
        self._settle_native_dialog_later()
        path, _ = QFileDialog.getSaveFileName(
            self, self._tr("toolbar.export"), "media_report.txt", "Text (*.txt)"
        )
        if not path:
            return
        export_txt(records, path, self._tr)
        self._show_toast(self._tr("toast.exported", name=Path(path).name))

    # -- settings, my tags, first run ------------------------------------

    def _maybe_first_run(self) -> None:
        if self._config.first_run_done:
            return
        if not self._config.first_run_prompted:
            self._open_first_run()
        else:
            self._update_guide_bar()

    def _open_first_run(self) -> None:
        self._config.first_run_prompted = True
        dialog = SettingsDialog(
            self._config, self._tr, self, tokens=self._palette,
            variant="first_run",
        )
        chosen = dialog.selected_mode()
        dialog.exec()
        if not self._config.first_run_done:
            self._config.recognition_mode = chosen
        self._config.first_run_prompted = True
        self._config.save()
        self._mode = self._config.recognition_mode
        self._ai.set_mode(self._mode)
        self._ai.set_custom_count(len(self._config.custom_labels))

    def _update_guide_bar(self) -> None:
        visible = (
            not self._config.first_run_done
            and self._config.first_run_prompted
            and not self._config.guide_dismissed
        )
        self._set_guide_visible(visible)

    def _set_guide_visible(self, visible: bool) -> None:
        """Reveal/collapse the 40 px bar instead of popping it in."""
        if visible:
            if self._guide_open:
                return
            self._guide_open = True
            start = self._guide.height() if self._guide.isVisible() else 0
            self._guide.setFixedHeight(start)
            self._guide.setVisible(True)
            animate_height(self._guide, start, 40, REVEAL)
            self._pulse_settings_button()
            return
        if not self._guide_open or not self._guide.isVisible():
            return
        self._guide_open = False

        def collapsed() -> None:
            self._guide.setVisible(False)
            self._guide.setFixedHeight(40)

        animate_height(self._guide, self._guide.height(), 0, REVEAL, collapsed)

    def _dismiss_guide(self) -> None:
        self._config.guide_dismissed = True
        self._config.save()
        self._set_guide_visible(False)

    def _hide_guide(self) -> None:
        if not self._guide.isVisible():
            return
        self._set_guide_visible(False)
        if not self._config.guide_dismissed:
            self._config.guide_dismissed = True
            self._config.save()

    def _pulse_settings_button(self) -> None:
        for index, on in enumerate((True, False, True, False)):
            QTimer.singleShot(
                index * 260,
                lambda on=on: self._set_settings_attention(on),
            )

    def _set_settings_attention(self, on: bool) -> None:
        self._settings_btn.setProperty("attention", on)
        style = self._settings_btn.style()
        style.unpolish(self._settings_btn)
        style.polish(self._settings_btn)

    def open_settings(self) -> None:
        self._hide_guide()
        dialog = SettingsDialog(
            self._config, self._tr, self, tokens=self._palette,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            previous = self._mode
            self._config.save()
            self._apply_saved_mode()
            self._ai.set_custom_count(len(self._config.custom_labels))
            if self._mode != previous:
                self._show_toast(self._tr(
                    "toast.mode_switched", mode=self._tr(f"mode.{self._mode}.name")
                ))
            else:
                self._show_toast(self._tr("status.settings_saved"))

    def open_my_tags(self) -> None:
        dialog = MyTagsDialog(
            self._config.custom_labels, self._tr, self,
            tokens=self._palette,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._config.custom_labels = dialog.labels()
            self._config.save()
            self._ai.set_custom_count(len(self._config.custom_labels))
            self._show_toast(self._tr("status.tags_saved"))

    def open_batch(self) -> None:
        records = self._target_records()
        if not records:
            message_box(self, "info", self._tr("app.title"), self._tr("msg.nothing_selected"))
            return
        dialog = BatchCommandDialog(
            records, self._tr, self._load_presets(), self, tokens=self._palette
        )
        dialog.exec()

    def open_convert(self) -> None:
        records = self._target_records()
        if not records:
            message_box(self, "info", self._tr("app.title"), self._tr("msg.nothing_selected"))
            return
        dialog = FormatConvertDialog(records, self._tr, self, tokens=self._palette)
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
        has_rows = self._model.rowCount() > 0

        act_select_all = menu.addAction(self._tr("menu.select_all"))
        act_deselect_all = menu.addAction(self._tr("menu.deselect_all"))
        act_check = menu.addAction(self._tr("menu.check_selected"))
        act_uncheck = menu.addAction(self._tr("menu.uncheck_selected"))
        menu.addSeparator()
        act_open = menu.addAction(self._tr("menu.open"))
        act_reveal = menu.addAction(self._tr("menu.open_location"))
        act_copy = menu.addAction(self._tr("menu.copy_paths"))
        menu.addSeparator()
        act_delete = menu.addAction(self._tr("menu.delete"))

        act_select_all.setEnabled(has_rows)
        act_deselect_all.setEnabled(has_rows)
        for a in (act_check, act_uncheck, act_open, act_reveal, act_copy, act_delete):
            a.setEnabled(has_sel)

        chosen = menu.exec(self._view.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen is act_select_all:
            self.select_all()
        elif chosen is act_deselect_all:
            self.deselect_all()
        elif chosen is act_check:
            self.check_selected()
        elif chosen is act_uncheck:
            self.uncheck_selected()
        elif chosen is act_open:
            self._open_path(self._model.record(rows[0]).path)
        elif chosen is act_reveal:
            self._reveal(self._model.record(rows[0]).path)
        elif chosen is act_copy:
            lines = [str(self._model.record(r).path) for r in rows]
            QApplication.clipboard().setText("\n".join(lines))
            self._set_status(self._tr("status.copied_paths", n=len(lines)))
        elif chosen is act_delete:
            self.delete_selected()

    def delete_selected(self) -> None:
        rows = self._selected_source_rows()
        if not rows:
            return
        n = len(rows)
        answer = message_box(
            self, "question", self._tr("app.title"), self._tr("msg.delete_confirm", n=n),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        records = [self._model.record(r) for r in rows]
        try:
            from send2trash import send2trash
        except ImportError:
            message_box(
                self, "critical", self._tr("app.title"),
                self._tr("msg.trash_missing"),
            )
            return
        failed = 0
        deleted: list[int] = []
        for row, rec in zip(rows, records):
            try:
                send2trash(str(rec.path))
                deleted.append(row)
            except Exception as exc:
                failed += 1
                logger.warning("delete failed for %s: %s", rec.path, exc)
        if deleted:
            self._model.remove_rows(deleted)
        self._refresh_stats()
        self._sync_empty_state()
        self._set_status(self._tr("status.deleted", n=len(deleted), failed=failed))

    # -- window behaviour ------------------------------------------------

    def toggle_maximize(self) -> None:
        if sys.platform == "win32":
            self._show_window(9 if self.isMaximized() else 3)  # SW_RESTORE / SW_MAXIMIZE
            return
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _minimize(self) -> None:
        if sys.platform == "win32" and self._show_window(6):  # SW_MINIMIZE
            return
        self.showMinimized()

    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange:
            self._titlebar.set_maximized(self.isMaximized())
        super().changeEvent(event)

    def showEvent(self, event):
        if not self._dwm_done and sys.platform == "win32":
            self._dwm_done = True
            self._enable_native_frame()
            self._enable_dwm_corners()
        super().showEvent(event)
        if not self._first_run_checked:
            self._first_run_checked = True
            QTimer.singleShot(0, self._maybe_first_run)

    def _enable_native_frame(self) -> bool:
        """Give the popup window a real frame while keeping our client area.

        DWM only animates minimize/maximize/restore for windows that carry a
        caption and a thick frame; a plain WS_POPUP snaps instantly. Adding
        WS_THICKFRAME | WS_CAPTION restores the native transitions, shadows and
        edge resizing. WM_NCCALCSIZE (handled in nativeEvent) then removes the
        non-client area so the custom titlebar still fills the whole window.
        """
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
            user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
            user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
            user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
            user32.SetWindowPos.argtypes = [
                wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                ctypes.c_int, ctypes.c_int, ctypes.c_uint,
            ]

            hwnd = wintypes.HWND(int(self.winId()))
            style = user32.GetWindowLongPtrW(hwnd, -16)  # GWL_STYLE
            user32.SetWindowLongPtrW(
                hwnd, -16, style | 0x00040000 | 0x00C00000  # WS_THICKFRAME | WS_CAPTION
            )
            user32.SetWindowPos(
                hwnd, None, 0, 0, 0, 0,
                0x0020 | 0x0001 | 0x0002 | 0x0004 | 0x0010,  # FRAMECHANGED, NOSIZE, NOMOVE, NOZORDER, NOACTIVATE
            )
            return True
        except Exception:
            return False

    def _show_window(self, command: int) -> bool:
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
            user32.ShowWindow(wintypes.HWND(int(self.winId())), command)
            return True
        except Exception:
            return False

    def _enable_dwm_corners(self) -> None:
        try:
            import ctypes

            hwnd = int(self.winId())
            preference = ctypes.c_int(2)  # DWMWCP_ROUND
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 33, ctypes.byref(preference), ctypes.sizeof(preference)
            )
        except Exception:
            pass

    def nativeEvent(self, eventType, message):
        if sys.platform == "win32":
            try:
                address = int(message)
            except (TypeError, ValueError):
                address = 0
            if address:
                try:
                    import ctypes
                    from ctypes import wintypes

                    msg = wintypes.MSG.from_address(address)
                    if msg.message == 0x0083 and msg.wParam:  # WM_NCCALCSIZE
                        return True, 0
                    if msg.message == 0x0084:  # WM_NCHITTEST
                        if not self.isMaximized():
                            x = ctypes.c_short(msg.lParam & 0xFFFF).value
                            y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                            code = self._resize_hit_test(x, y)
                            if code is not None:
                                return True, code
                        # With WS_CAPTION the default hit test would report
                        # HTCAPTION over our custom titlebar and swallow button
                        # clicks, so keep the whole client area client-side.
                        return True, 1  # HTCLIENT
                except Exception:
                    pass
        return super().nativeEvent(eventType, message)

    def _resize_hit_test(self, screen_x: int, screen_y: int):
        dpr = self.devicePixelRatioF() or 1.0
        pos = self.mapFromGlobal(QPoint(int(screen_x / dpr), int(screen_y / dpr)))
        left = pos.x() < _RESIZE_BORDER
        right = pos.x() >= self.width() - _RESIZE_BORDER
        top = pos.y() < _RESIZE_BORDER
        bottom = pos.y() >= self.height() - _RESIZE_BORDER
        if top and left:
            return _HTTOPLEFT
        if top and right:
            return _HTTOPRIGHT
        if bottom and left:
            return _HTBOTTOMLEFT
        if bottom and right:
            return _HTBOTTOMRIGHT
        if left:
            return _HTLEFT
        if right:
            return _HTRIGHT
        if top:
            return _HTTOP
        if bottom:
            return _HTBOTTOM
        return None

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
        self._stop_worker(self._worker, "scan")
        self._stop_worker(self._tag_worker, "tagging")
        g = self.normalGeometry() if self.isMaximized() else self.geometry()
        if g.width() > 200 and g.height() > 200:
            self._config.window_geometry = f"{g.x()},{g.y()},{g.width()},{g.height()}"
        self._config.window_maximized = self.isMaximized()
        self._config.save()
        super().closeEvent(event)

    @staticmethod
    def _stop_worker(worker, label: str) -> None:
        """Cancel a running scan/tag thread and make sure it is gone.

        QThread objects are owned by the window. Closing while one is still
        running makes Qt abort with "Destroyed while thread is still running",
        so fall back to terminate() when a cooperative cancel does not finish
        in time (ffprobe can sit on a 120 s timeout).
        """
        if worker is None or not worker.isRunning():
            return
        worker.cancel()
        if worker.wait(1500):
            return
        logger.warning("%s worker did not stop in 1.5 s; terminating", label)
        worker.terminate()
        worker.wait(3000)


def _theme_key(mode: str) -> str:
    return f"theme.{mode}" if mode in ("system", "light", "dark") else "theme.system"