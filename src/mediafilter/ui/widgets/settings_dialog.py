"""Recognition settings and the first-run welcome flow.

Sections mirror ``.interface-design/settings.md`` and
``recognition-mode-prototype.html``: default mode, API connection, built-in
tags, advanced options. Everything is a draft until Save; Cancel discards it
all. The welcome variant additionally shows the three mode cards and a
custom-tags entry.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from PySide6.QtCore import QRectF, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPainterPath, QPen,
)
from PySide6.QtWidgets import (
    QAbstractButton, QButtonGroup, QFrame, QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLayout, QLineEdit,
    QMessageBox, QPushButton, QScrollArea, QSizePolicy, QStackedWidget,
    QToolButton, QVBoxLayout, QWidget,
)

from ...config import Config
from ...core import secret_store
from ...core.cloud_models import (
    IMAGE, TEXT, UNKNOWN, VERIFIED_IMAGE, CloudModelError, ModelInfo,
    list_models, normalize_base_url, probe_vision,
)
from ...core.vocabulary import (
    ALL_TAG_IDS, DEFAULT_ENABLED, TAG_GROUPS, group_label, tag_label,
)
from ..dialog_base import (
    AppDialog, count_label, dialog_button, hint_label,
    lede_label, message_box, note_label, section_label,
)
from ..icons import brand_pixmap, line_icon
from ..tokens import LIGHT, parse_color
from .flow_layout import FlowLayout
from .mode_widgets import MODES, DefaultModeList, ModeCardRow, mode_text
from .model_picker import ModelPicker
from .my_tags_dialog import MyTagsDialog

DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# Workers are not parented to the dialog: closing the dialog while a request
# is in flight must not destroy a running QThread.  The module keeps them alive
# until their ``finished`` signal arrives; late signals are disconnected by Qt
# when the dialog is gone.
_ACTIVE_WORKERS: set[QThread] = set()

_FRAME_POLICIES = ("auto", "fast", "fine")
_ADVANCED_OPEN = False

# Width assumed for the wrapping tag grid when Qt asks for a height without
# knowing the final width. Wide enough for the largest built-in group to stay
# on one line, so minimum heights stay close to the real rendering.
_TAGS_WIDTH = 560
_TAGS_WIDTH_COMPACT = 644

# The regular B4 settings page is the 900x570 prototype enlarged by 1.15.
# First-run keeps the original roomier metrics, so every scaled value below
# is only used on the tabbed page.
_SETTINGS_SCALE = 1.15


def _scaled(value: float) -> int:
    return int(round(value * _SETTINGS_SCALE))


def _track_worker(worker: QThread) -> None:
    _ACTIVE_WORKERS.add(worker)
    worker.finished.connect(lambda: _release_worker(worker))


def _release_worker(worker: QThread) -> None:
    _ACTIVE_WORKERS.discard(worker)
    worker.deleteLater()


def wait_for_active_workers(timeout_ms: int = 5000) -> None:
    """Give in-flight model calls a chance to finish before app shutdown."""
    deadline = time.monotonic() + timeout_ms / 1000
    for worker in list(_ACTIVE_WORKERS):
        remaining = int(max(0.0, deadline - time.monotonic()) * 1000)
        if remaining <= 0:
            break
        try:
            worker.wait(remaining)
        except RuntimeError:
            continue


def _t(tr, key: str, fallback: str) -> str:
    text = tr(key)
    return fallback if text == key else text


def _link_button(text: str, tokens: dict[str, str],
                 large: bool = False) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("InlineLink")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setFixedHeight(_scaled(20) if large else 20)
    button.setMinimumWidth(0)
    font_size = _scaled(12) if large else 12
    button.setStyleSheet(
        "QPushButton#InlineLink { background: transparent; border: none; "
        f"color: {tokens['ink_3']}; font-size: {font_size}px; padding: 0; "
        "min-width: 0; min-height: 0; }"
        f"QPushButton#InlineLink:hover {{ color: {tokens['accent']}; }}"
    )
    return button


class _StatusRow(QWidget):
    """6px status dot + 11px text + optional detail/action."""

    def __init__(self, tokens: dict[str, str], with_action: bool = False,
                 large: bool = False) -> None:
        super().__init__()
        self._tokens = tokens
        self._with_action = with_action
        self._large = large
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(_scaled(6) if large else 6)
        self.dot = QLabel()
        dot_size = _scaled(6) if large else 6
        self.dot.setFixedSize(dot_size, dot_size)
        row.addWidget(self.dot)
        self.text = QLabel()
        row.addWidget(self.text)
        self.detail: QLabel | None = None
        self.action: QPushButton | None = None
        if with_action:
            self.detail = QLabel()
            row.addWidget(self.detail)
            self.action = QPushButton()
            self.action.setObjectName("InlineLink")
            self.action.setCursor(Qt.CursorShape.PointingHandCursor)
            self.action.setFixedHeight(_scaled(18) if large else 18)
            self.action.setMinimumWidth(0)
            row.addWidget(self.action)
        row.addStretch(1)
        self.set_status("idle", "")

    def _style_link(self) -> None:
        if self.action is None:
            return
        size = _scaled(12) if self._large else 12
        self.action.setStyleSheet(
            "QPushButton#InlineLink { background: transparent; border: none; "
            f"color: {self._tokens['accent']}; font-size: {size}px; padding: 0; "
            "min-width: 0; min-height: 0; }"
            f"QPushButton#InlineLink:hover {{ color: {self._tokens['accent_strong']}; }}"
        )

    def set_status(
        self,
        tone: str,
        text: str,
        detail: str = "",
        action: str = "",
    ) -> None:
        self._style_link()
        colors = {
            "idle": self._tokens["ink_3"],
            "ok": self._tokens["green"],
            "bad": self._tokens["red"],
            "busy": self._tokens["accent"],
        }
        color = colors.get(tone, self._tokens["ink_3"])
        radius = _scaled(3) if self._large else 3
        self.dot.setStyleSheet(
            f"background: {color}; border-radius: {radius}px;"
        )
        self.text.setText(text)
        self.text.setStyleSheet(
            f"color: {color}; font-size: {_scaled(12) if self._large else 12}px;"
        )
        if self.detail is not None:
            self.detail.setText(detail)
            self.detail.setStyleSheet(
                f"color: {self._tokens['ink_3']}; "
                f"font-size: {_scaled(11) if self._large else 11}px;"
            )
            if self.action is not None:
                self.action.setText(action)
                self.action.setVisible(bool(action))


class _ModelListWorker(QThread):
    ok = Signal(list)
    failed = Signal(str)

    def __init__(self, base_url: str, api_key: str, parent=None) -> None:
        super().__init__(parent)
        self._base = base_url
        self._key = api_key

    def run(self) -> None:
        try:
            self.ok.emit(list_models(self._base, self._key))
        except CloudModelError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # network stack variations
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class _ProbeWorker(QThread):
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, base_url: str, api_key: str, model_id: str,
                 parent=None) -> None:
        super().__init__(parent)
        self._base = base_url
        self._key = api_key
        self._model = model_id

    def run(self) -> None:
        try:
            self.done.emit(probe_vision(self._base, self._key, self._model))
        except CloudModelError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Small custom controls
# ---------------------------------------------------------------------------


class CheckRow(QAbstractButton):
    """16px rounded checkbox + 11px label, painted to match the prototype."""

    def __init__(self, text: str, tokens: dict[str, str],
                 parent: QWidget | None = None, compact: bool = False) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._text = text
        self._box = _scaled(16) if compact else 16
        self._text_left = _scaled(24) if compact else 24
        self._height = _scaled(20) if compact else 20
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(self._height)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        font = QFont(self.font())
        font.setPixelSize(_scaled(10) if compact else 11)
        self.setFont(font)
        self.toggled.connect(lambda _checked: self.update())

    def sizeHint(self) -> QSize:
        metrics = QFontMetrics(self.font())
        trailing = _scaled(4) if self._box != 16 else 4
        return QSize(
            self._text_left + metrics.horizontalAdvance(self._text) + trailing,
            self._height,
        )

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        tokens = self._tokens
        box = self._box
        k = box / 16
        top = (self.height() - box) / 2
        inset = 0.75 * k
        rect = (inset, top + inset, box - 2 * inset, box - 2 * inset)
        if self.isChecked():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(parse_color(tokens["accent"]))
        else:
            painter.setPen(QPen(parse_color(tokens["line_strong"]), 1.5 * k))
            painter.setBrush(parse_color(tokens["surface"]))
        painter.drawRoundedRect(QRectF(*rect), 4 * k, 4 * k)
        if self.isChecked():
            path = QPainterPath()
            path.moveTo(4.2 * k, top + 8.4 * k)
            path.lineTo(6.8 * k, top + 11.0 * k)
            path.lineTo(11.9 * k, top + 4.6 * k)
            painter.setPen(QPen(parse_color(tokens["on_accent"]), 1.7 * k,
                                Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                                Qt.PenJoinStyle.RoundJoin))
            painter.drawPath(path)
        painter.setPen(parse_color(tokens["ink_2"]))
        painter.setFont(self.font())
        painter.drawText(
            QRectF(self._text_left, 0, self.width() - self._text_left,
                   self.height()),
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            self._text,
        )
        painter.end()


class Segment(QFrame):
    """Three-button segmented control (抽帧强度)."""

    changed = Signal(str)

    def __init__(self, tr, tokens: dict[str, str],
                 parent: QWidget | None = None,
                 compact: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("SegmentBox")
        self._tokens = tokens
        self._compact = compact
        margin = _scaled(2) if compact else 2
        layout = QHBoxLayout(self)
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(0)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.buttons: dict[str, QPushButton] = {}
        for policy in _FRAME_POLICIES:
            button = QPushButton(tr(f"settings.frame_{policy}"))
            button.setObjectName("Segment")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFixedHeight(_scaled(24) if compact else 26)
            button.setMinimumWidth(_scaled(56) if compact else 56)
            self._group.addButton(button)
            layout.addWidget(button)
            self.buttons[policy] = button
            button.clicked.connect(lambda _checked=False, p=policy: self.changed.emit(p))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_policy(self, policy: str) -> None:
        button = self.buttons.get(policy)
        if button is not None:
            button.setChecked(True)

    def policy(self) -> str:
        for key, button in self.buttons.items():
            if button.isChecked():
                return key
        return "auto"


class _SettingsTab(QAbstractButton):
    """One underline tab with an index, name and live status on the right."""

    def __init__(self, index: int, title: str, tokens: dict[str, str],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._index = f"{index:02d}"
        self._title = title
        self._meta = ""
        self._tokens = tokens
        self._hover = False
        self._keyboard_focus = False
        self._tab_order: list[_SettingsTab] = []
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedHeight(_scaled(36))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName(title)

    def set_meta(self, text: str) -> None:
        if text == self._meta:
            return
        self._meta = text
        self.setAccessibleDescription(text)
        self.update()

    def set_tab_order(self, tabs: list["_SettingsTab"]) -> None:
        self._tab_order = tabs

    def sizeHint(self) -> QSize:
        return QSize(_scaled(160), _scaled(36))

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def focusInEvent(self, event) -> None:
        self._keyboard_focus = event.reason() in (
            Qt.FocusReason.TabFocusReason,
            Qt.FocusReason.BacktabFocusReason,
            Qt.FocusReason.ShortcutFocusReason,
        )
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        self._keyboard_focus = False
        self.update()
        super().focusOutEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            if self._tab_order:
                step = -1 if event.key() == Qt.Key.Key_Left else 1
                current = self._tab_order.index(self) if self in self._tab_order else 0
                target = self._tab_order[(current + step) % len(self._tab_order)]
                target.setFocus(Qt.FocusReason.OtherFocusReason)
                target.click()
            return
        super().keyPressEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        tokens = self._tokens
        rect = QRectF(self.rect())
        checked = self.isChecked()
        if checked:
            painter.fillRect(rect, parse_color(tokens["accent_soft"]))
        elif self._hover:
            painter.fillRect(rect, parse_color(tokens["row_hover"]))

        if self._index != "01":
            painter.setPen(QPen(parse_color(tokens["line"]), 1))
            painter.drawLine(
            int(rect.left() + 0.5), _scaled(8),
            int(rect.left() + 0.5), int(rect.bottom()) - _scaled(8),
        )

        color = tokens["accent"] if checked else tokens["ink_3"]
        index_font = QFont(self.font())
        index_font.setFamilies(["Cascadia Mono", "Consolas", "Courier New"])
        index_font.setPixelSize(_scaled(9))
        title_font = QFont(self.font())
        title_font.setPixelSize(_scaled(11))
        title_font.setWeight(QFont.Weight.DemiBold)
        meta_font = QFont(self.font())
        meta_font.setPixelSize(_scaled(9))

        painter.setFont(index_font)
        painter.setPen(parse_color(color))
        painter.drawText(
            QRectF(_scaled(4), 0, _scaled(18), self.height()),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            self._index,
        )
        painter.setFont(title_font)
        painter.setPen(parse_color(tokens["ink"] if checked else tokens["ink_2"]))
        painter.drawText(
            QRectF(_scaled(23), 0, self.width() - _scaled(70), self.height()),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            self._title,
        )
        if self._meta:
            painter.setFont(meta_font)
            painter.setPen(parse_color(color))
            painter.drawText(
                QRectF(0, 0, self.width() - _scaled(5), self.height()),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                self._meta,
            )

        if checked:
            painter.fillRect(
                QRectF(rect.left(), rect.bottom() - 2, rect.width(), 2),
                parse_color(tokens["accent"]),
            )
        if self._keyboard_focus:
            painter.setPen(QPen(parse_color(tokens["accent"]), 1))
            painter.drawRoundedRect(
                rect.adjusted(_scaled(2), _scaled(2), -_scaled(2), -_scaled(2)),
                _scaled(5), _scaled(5),
            )
        painter.end()


class _FrameStrip(QWidget):
    """Eight tiny cells; filled cells show how much of a video is sampled."""

    def __init__(self, tokens: dict[str, str], cells: int = 8,
                 cell_height: int = 6, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._cells = cells
        self._active = 0
        self._cell_height = cell_height
        self.setFixedHeight(cell_height)
        self.setMinimumWidth(_scaled(80))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def set_active(self, count: int) -> None:
        count = max(0, min(self._cells, count))
        if count != self._active:
            self._active = count
            self.update()

    def sizeHint(self) -> QSize:
        return QSize(150, self._cell_height)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        tokens = self._tokens
        gap = 2.0
        width = (self.width() - gap * (self._cells - 1)) / self._cells
        for index in range(self._cells):
            rect = QRectF(index * (width + gap), 0.5, width, self.height() - 1)
            if index < self._active:
                painter.setPen(QPen(parse_color(tokens["accent"]), 1))
                painter.setBrush(parse_color(tokens["accent"]))
            else:
                painter.setPen(QPen(parse_color(tokens["line_strong"]), 1))
                painter.setBrush(parse_color(tokens["sunken"]))
            painter.drawRoundedRect(rect, 1.5, 1.5)
        painter.end()


class _RailLine(QWidget):
    """A label/value row in the right-hand summary card."""

    def __init__(self, label: str, value: str, tokens: dict[str, str],
                 first: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._first = first
        self.setFixedHeight(_scaled(22))
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(_scaled(8))
        self.label = QLabel(label)
        self.label.setObjectName("RailLabel")
        row.addWidget(self.label)
        row.addStretch(1)
        self.value = QLabel(value)
        self.value.setObjectName("RailValue")
        self.value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        row.addWidget(self.value)

    def set_value(self, text: str) -> None:
        if text != self.value.text():
            self.value.setText(text)

    def paintEvent(self, _event) -> None:
        if self._first:
            return
        painter = QPainter(self)
        painter.setPen(QPen(parse_color(self._tokens["line"]), 1))
        painter.drawLine(0, 0, int(self.width()), 0)
        painter.end()


class BuiltinTagsPanel(QWidget):
    """The 26 built-in tags, grouped, with 全选 / 清空."""

    changed = Signal(int)

    def __init__(self, tr, tokens: dict[str, str], enabled: list[str],
                 show_header: bool = True, parent: QWidget | None = None,
                 title_key: str = "settings.tags_title",
                 compact: bool = False) -> None:
        super().__init__(parent)
        self._tr = tr
        self._tokens = tokens
        self._compact = compact
        self._buttons: dict[str, QPushButton] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(_scaled(5) if compact else 7)

        self.header = QWidget(self)
        head = QHBoxLayout(self.header)
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(_scaled(8) if compact else 8)
        head.addWidget(section_label(tr(title_key)))
        self.count = QLabel()
        self.count.setObjectName("TagCount")
        head.addWidget(self.count)
        head.addStretch(1)
        self._all_btn = _link_button(tr("settings.tags_all"), tokens, large=compact)
        self._none_btn = _link_button(tr("settings.tags_none"), tokens, large=compact)
        head.addWidget(self._all_btn)
        head.addWidget(self._none_btn)
        self.header.setVisible(show_header)
        layout.addWidget(self.header)

        enabled_set = set(enabled)
        for group_key, tag_ids in TAG_GROUPS:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(_scaled(5) if compact else 12)
            group = QLabel(group_label(tr, group_key))
            group.setObjectName("TagGroupLabel")
            group_text = group.text()
            if compact and len(group_text) <= 2:
                group.setFixedWidth(_scaled(26))
            else:
                group.setFixedWidth(_scaled(44) if compact else 44)
            group.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            row.addWidget(group)
            chip_holder = QWidget()
            chip_holder.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            flow = FlowLayout(
                chip_holder,
                h_spacing=_scaled(3) if compact else 5,
                v_spacing=_scaled(4) if compact else 5,
            )
            for tag_id in tag_ids:
                button = QPushButton()
                button.setObjectName("TagChip")
                button.setCheckable(True)
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.setFixedHeight(_scaled(22) if compact else 26)
                button.setChecked(tag_id in enabled_set)
                button.setProperty("tagId", tag_id)
                self._paint_text(button, tag_id)
                button.toggled.connect(
                    lambda checked, b=button, t=tag_id: self._on_toggled(b, t, checked)
                )
                self._buttons[tag_id] = button
                flow.addWidget(button)
            row.addWidget(chip_holder, 1)
            layout.addLayout(row)

        self.note = note_label(tr("settings.tags_note"))
        layout.addWidget(self.note)

        self._all_btn.clicked.connect(lambda: self.set_all(True))
        self._none_btn.clicked.connect(lambda: self.set_all(False))
        self._refresh_count()

    def _paint_text(self, button: QPushButton, tag_id: str) -> None:
        label = tag_label(self._tr, tag_id)
        button.setText(("✓ " if button.isChecked() else "") + label)

    def _on_toggled(self, button: QPushButton, tag_id: str, checked: bool) -> None:
        self._paint_text(button, tag_id)
        self._refresh_count()
        self.changed.emit(self.count_enabled())

    def set_all(self, enabled: bool) -> None:
        for button in self._buttons.values():
            button.blockSignals(True)
            button.setChecked(enabled)
            button.blockSignals(False)
        for tag_id, button in self._buttons.items():
            self._paint_text(button, tag_id)
        self._refresh_count()
        self.changed.emit(self.count_enabled())

    def set_enabled_ids(self, ids: list[str]) -> None:
        enabled = set(ids)
        for tag_id, button in self._buttons.items():
            button.blockSignals(True)
            button.setChecked(tag_id in enabled)
            button.blockSignals(False)
            self._paint_text(button, tag_id)
        self._refresh_count()
        self.changed.emit(self.count_enabled())

    def count_enabled(self) -> int:
        return sum(1 for button in self._buttons.values() if button.isChecked())

    def enabled_ids(self) -> list[str]:
        return [tag for tag in ALL_TAG_IDS if self._buttons[tag].isChecked()]

    # Qt asks a height-for-width widget for its height at its *minimum* width
    # when sizing a parent. With FlowLayout that means every chip on its own
    # line and a minimum height several times too tall, which the scroll area
    # then honours — leaving a large blank gap under the content. Report the
    # height for the width we are actually given instead.
    def hasHeightForWidth(self) -> bool:  # noqa: N802 (Qt name)
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        layout = self.layout()
        if layout is None:
            return super().heightForWidth(width)
        floor = _TAGS_WIDTH_COMPACT if self._compact else _TAGS_WIDTH
        return layout.totalHeightForWidth(max(width, floor))

    def sizeHint(self) -> QSize:  # noqa: N802
        hint = super().sizeHint()
        floor = _TAGS_WIDTH_COMPACT if self._compact else _TAGS_WIDTH
        width = self.width() if self.width() > 0 else floor
        return QSize(hint.width(), self.heightForWidth(width))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        hint = super().minimumSizeHint()
        floor = _TAGS_WIDTH_COMPACT if self._compact else _TAGS_WIDTH
        width = max(self.width(), floor)
        return QSize(hint.width(), self.heightForWidth(width))

    def _refresh_count(self) -> None:
        self.count.setText(self._tr("settings.tags_count", n=self.count_enabled()))


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------


class SettingsDialog(AppDialog):
    def __init__(
        self,
        config: Config,
        tr,
        parent=None,
        tokens: dict[str, str] | None = None,
        variant: str = "settings",
    ) -> None:
        super().__init__(tokens, parent)
        self._config = config
        self._tr = tr
        self._tokens = tokens or LIGHT
        self._variant = variant if variant in ("settings", "first_run") else "settings"
        self._first_run = self._variant == "first_run"

        self._models: list[ModelInfo] = []
        self._model_state = "none"
        self._list_worker: _ModelListWorker | None = None
        self._probe_worker: _ProbeWorker | None = None
        self._saved_key = ""
        self._key_error = ""
        self._key_unreadable = False
        self._request_base = ""
        self._probe_base = ""
        self._probe_key = ""
        self._loaded_base = ""
        self._pending_cache: dict[str, str] = {}
        self._probe_at = ""
        self._auto_started = False
        self._api_tone = "idle"
        self._api_text = ""
        self._tabs: dict[str, _SettingsTab] = {}
        self._pages: dict[str, QWidget] = {}
        self._stack: QStackedWidget | None = None
        self._scroll: QScrollArea | None = None
        self._body: QWidget | None = None
        self._adv_toggle: QToolButton | None = None
        self._adv_panel: QWidget | None = None
        self._api_effect: QGraphicsOpacityEffect | None = None

        tags = [tag for tag in config.tag_palette if tag in ALL_TAG_IDS]
        self._enabled_tags = tags or list(DEFAULT_ENABLED)
        self._custom_labels = list(config.custom_labels)
        mode = config.recognition_mode if config.recognition_mode in MODES else "local"
        if (
            self._first_run
            and not config.first_run_done
            and config.cloud_api_key_dpapi
            and config.recognition_mode == "local"
        ):
            mode = "hybrid"
        self._mode = mode
        self._frame_policy = (
            config.frame_policy if config.frame_policy in _FRAME_POLICIES else "auto"
        )

        self.setWindowTitle(
            tr("first_run.window_title") if self._first_run else tr("settings.title")
        )
        self.setMinimumSize(680, 620)
        if not self._first_run:
            self.setMinimumSize(_scaled(840), _scaled(540))
        self._size_dialog()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        if self._first_run:
            self._build_first_run(outer)
        else:
            self._build_tabbed_page(outer)

        self._load_saved_state()
        self._wire()
        self._update_summary()

    def _build_first_run(self, outer: QVBoxLayout) -> None:
        """The welcome flow keeps its single scroll column."""
        self._scroll = QScrollArea()
        self._scroll.setObjectName("SettingsScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._body = QWidget()
        self._body.setObjectName("SettingsBody")
        body = QVBoxLayout(self._body)
        body.setContentsMargins(24, 22, 24, 18)
        body.setSpacing(12)
        self._scroll.setWidget(self._body)
        outer.addWidget(self._scroll, 1)

        self._build_intro(body)
        self._build_mode_section(body)
        body.addWidget(self._rule())
        self._build_api_section(body)
        body.addWidget(self._rule())
        self._build_custom_section(body)
        self._build_tags_section(body)
        body.addWidget(self._rule())
        self._build_advanced_section(body)
        body.addStretch(1)
        self._build_footer(outer)

    # -- B4: tabs + persistent summary rail -------------------------------

    def _build_tabbed_page(self, outer: QVBoxLayout) -> None:
        self._build_settings_header(outer)
        self._build_tab_bar(outer)
        self._build_tab_stack(outer)
        self._build_footer(outer)
        self._apply_micro_type()

    def _apply_micro_type(self) -> None:
        """QSS has no letter-spacing; small labels need it to read like the
        prototype's tracked uppercase/meta rows."""
        tracking = {
            "RailTitle": 1.0,
            "FactLabel": 0.5,
            "FieldLabel": 0.6,
            "SectionLabel": 0.5,
        }
        for label in self.findChildren(QLabel):
            spacing = tracking.get(label.objectName())
            if spacing is None:
                continue
            font = label.font()
            font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
            label.setFont(font)

    def _chip(self, text: str, accent: bool = False) -> QLabel:
        chip = QLabel(text)
        chip.setObjectName("HeaderChipAccent" if accent else "HeaderChip")
        chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chip.setFixedHeight(_scaled(21))
        return chip

    def _build_settings_header(self, outer: QVBoxLayout) -> None:
        header = QWidget()
        header.setObjectName("SettingsHeader")
        row = QHBoxLayout(header)
        row.setContentsMargins(_scaled(22), _scaled(11), _scaled(22), _scaled(7))
        row.setSpacing(_scaled(12))

        copy = QVBoxLayout()
        copy.setContentsMargins(0, 0, 0, 0)
        copy.setSpacing(1)
        title = QLabel(self._tr("settings.title"))
        title.setObjectName("SettingsHeading")
        copy.addWidget(title)
        lede = QLabel(self._tr("settings.lede"))
        lede.setObjectName("SettingsSub")
        lede.setWordWrap(True)
        copy.addWidget(lede)
        row.addLayout(copy, 1)

        chips = QHBoxLayout()
        chips.setContentsMargins(0, _scaled(2), 0, 0)
        chips.setSpacing(_scaled(5))
        self._chip_mode = self._chip("", accent=True)
        self._chip_tags = self._chip("")
        self._chip_frame = self._chip("")
        chips.addWidget(self._chip_mode)
        chips.addWidget(self._chip_tags)
        chips.addWidget(self._chip_frame)
        row.addLayout(chips, 0)
        outer.addWidget(header)

    def _build_tab_bar(self, outer: QVBoxLayout) -> None:
        wrap = QWidget()
        row = QHBoxLayout(wrap)
        row.setContentsMargins(_scaled(24), _scaled(5), _scaled(24), 0)
        row.setSpacing(0)
        self._tab_group = QButtonGroup(self)
        self._tab_group.setExclusive(True)
        order: list[_SettingsTab] = []
        specs = (
            ("mode", "settings.tab_mode"),
            ("api", "settings.tab_api"),
            ("tags", "settings.tab_tags"),
            ("advanced", "settings.tab_advanced"),
        )
        for index, (key, title_key) in enumerate(specs, start=1):
            tab = _SettingsTab(index, self._tr(title_key), self._tokens, wrap)
            tab.clicked.connect(lambda _checked=False, k=key: self._show_tab(k))
            self._tab_group.addButton(tab)
            self._tabs[key] = tab
            order.append(tab)
            row.addWidget(tab, 1)
        for tab in order:
            tab.set_tab_order(order)
        order[0].setChecked(True)
        outer.addWidget(wrap)
        outer.addWidget(self._inset_rule(_scaled(24), _scaled(24)))

    def _inset_rule(self, left: int, right: int) -> QWidget:
        wrap = QWidget()
        row = QHBoxLayout(wrap)
        row.setContentsMargins(left, 0, right, 0)
        row.setSpacing(0)
        row.addWidget(self._rule())
        return wrap

    def _build_tab_stack(self, outer: QVBoxLayout) -> None:
        main = QWidget()
        row = QHBoxLayout(main)
        row.setContentsMargins(
            _scaled(24), _scaled(10), _scaled(24), _scaled(10)
        )
        row.setSpacing(_scaled(14))

        pane = QFrame()
        pane.setObjectName("SettingsPane")
        pane_layout = QVBoxLayout(pane)
        pane_layout.setContentsMargins(0, 0, 0, 0)
        pane_layout.setSpacing(0)
        self._stack = QStackedWidget()
        self._stack.setObjectName("SettingsStack")
        builders = {
            "mode": self._build_mode_page,
            "api": self._build_api_page,
            "tags": self._build_tags_page,
            "advanced": self._build_advanced_page,
        }
        for key, _title_key in (
            ("mode", "settings.tab_mode"),
            ("api", "settings.tab_api"),
            ("tags", "settings.tab_tags"),
            ("advanced", "settings.tab_advanced"),
        ):
            page = builders[key]()
            self._pages[key] = page
            self._stack.addWidget(page)
        pane_layout.addWidget(self._stack)
        row.addWidget(pane, 1)
        row.addWidget(self._build_summary_rail(), 0)
        outer.addWidget(main, 1)

    def _stack_page(self, spacing: int = _scaled(8)) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page.setObjectName("SettingsPage")
        box = QVBoxLayout(page)
        box.setContentsMargins(
            _scaled(14), _scaled(13), _scaled(14), _scaled(12)
        )
        box.setSpacing(spacing)
        return page, box

    def _pane_header(self, title: str, lede: str) -> QWidget:
        header = QWidget()
        box = QVBoxLayout(header)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(1)
        title_label = QLabel(title)
        title_label.setObjectName("PaneTitle")
        box.addWidget(title_label)
        lede_label = QLabel(lede)
        lede_label.setObjectName("PaneLede")
        lede_label.setWordWrap(True)
        box.addWidget(lede_label)
        return header

    def _fact_card(self, label: str) -> tuple[QFrame, QLabel, QLabel]:
        card = QFrame()
        card.setObjectName("FactCard")
        box = QVBoxLayout(card)
        box.setContentsMargins(_scaled(9), _scaled(7), _scaled(9), _scaled(7))
        box.setSpacing(1)
        label_widget = QLabel(label)
        label_widget.setObjectName("FactLabel")
        box.addWidget(label_widget)
        value = QLabel()
        value.setObjectName("FactValue")
        box.addWidget(value)
        detail = QLabel()
        detail.setObjectName("FactDetail")
        detail.setWordWrap(True)
        box.addWidget(detail)
        return card, value, detail

    def _build_mode_page(self) -> QWidget:
        page, box = self._stack_page()
        box.addWidget(self._pane_header(
            self._tr("settings.pane_mode_title"),
            self._tr("settings.pane_mode_lede"),
        ))
        self._mode_cards = ModeCardRow(self._tr, self._tokens, page, compact=True)
        self._mode_list = None
        self._mode_cards.set_mode(self._mode)
        box.addWidget(self._mode_cards)

        scope = QFrame()
        scope.setObjectName("ScopeNote")
        scope_row = QHBoxLayout(scope)
        scope_row.setContentsMargins(
            _scaled(9), _scaled(5), _scaled(9), _scaled(5)
        )
        scope_row.setSpacing(_scaled(9))
        self._scope_strip = _FrameStrip(
            self._tokens, cell_height=_scaled(6), parent=scope
        )
        self._scope_strip.setFixedWidth(_scaled(150))
        scope_row.addWidget(self._scope_strip, 0)
        self._scope_note = QLabel()
        self._scope_note.setObjectName("ScopeText")
        self._scope_note.setWordWrap(True)
        scope_row.addWidget(self._scope_note, 1)
        box.addWidget(scope)

        facts = QHBoxLayout()
        facts.setContentsMargins(0, 0, 0, 0)
        facts.setSpacing(_scaled(8))
        card, self._fact_scope_value, self._fact_scope_detail = self._fact_card(
            self._tr("settings.fact_upload_scope")
        )
        facts.addWidget(card, 1)
        card, self._fact_frames_value, self._fact_frames_detail = self._fact_card(
            self._tr("settings.fact_frames")
        )
        facts.addWidget(card, 1)
        card, self._fact_original_value, self._fact_original_detail = self._fact_card(
            self._tr("settings.fact_original")
        )
        facts.addWidget(card, 1)
        box.addLayout(facts)

        box.addStretch(1)
        self._current_note = QLabel(self._tr(
            "settings.current_mode_note",
            mode=mode_text(self._tr, self._config.recognition_mode),
        ))
        self._current_note.setObjectName("Hint")
        self._current_note.setWordWrap(True)
        box.addWidget(self._current_note)
        return page

    def _build_api_page(self) -> QWidget:
        page, box = self._stack_page(spacing=_scaled(6))
        box.addWidget(self._pane_header(
            self._tr("settings.pane_api_title"),
            self._tr("settings.pane_api_lede"),
        ))
        self._build_api_section(box, with_header=False, compact=True)
        layout = self._api_body.layout()
        if layout is not None:
            layout.setSpacing(_scaled(6))
        box.addStretch(1)
        return page

    def _build_tags_page(self) -> QWidget:
        page, box = self._stack_page()
        box.addWidget(self._pane_header(
            self._tr("settings.pane_tags_title"),
            self._tr("settings.pane_tags_lede"),
        ))
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(_scaled(16))

        left = QWidget()
        left.setFixedWidth(_scaled(254))
        left_box = QVBoxLayout(left)
        left_box.setContentsMargins(0, 0, 0, 0)
        left_box.setSpacing(_scaled(6))
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(_scaled(6))
        head.addWidget(section_label(self._tr("settings.custom_title")))
        head.addStretch(1)
        self._custom_count = QLabel(self._tr(
            "settings.custom_ratio", n=len(self._custom_labels), max=10,
        ))
        self._custom_count.setObjectName("DialogCount")
        head.addWidget(self._custom_count)
        self._custom_edit = _link_button(
            self._tr("settings.custom_edit"), self._tokens, large=True
        )
        head.addWidget(self._custom_edit)
        left_box.addLayout(head)

        self._custom_chips = QWidget()
        self._custom_chips.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum,
        )
        self._custom_chips_layout = FlowLayout(
            self._custom_chips, h_spacing=_scaled(5), v_spacing=_scaled(5),
        )
        left_box.addWidget(self._custom_chips)

        self._custom_note = note_label(self._tr("settings.custom_note"))
        left_box.addWidget(self._custom_note)
        left_box.addStretch(1)
        row.addWidget(left, 0)

        right = QWidget()
        right_box = QVBoxLayout(right)
        right_box.setContentsMargins(0, 0, _scaled(16), 0)
        right_box.setSpacing(0)
        self._tags_panel = BuiltinTagsPanel(
            self._tr, self._tokens, self._enabled_tags,
            show_header=True, parent=page,
            title_key="settings.builtin_title", compact=True,
        )
        right_box.addWidget(self._tags_panel)
        row.addWidget(right, 1)
        box.addLayout(row, 1)
        self._rebuild_custom_chips()
        return page

    def _build_advanced_page(self) -> QWidget:
        page, box = self._stack_page()
        box.addWidget(self._pane_header(
            self._tr("settings.pane_advanced_title"),
            self._tr("settings.pane_advanced_lede"),
        ))

        columns = QHBoxLayout()
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(_scaled(10))

        sampling = QFrame()
        sampling.setObjectName("AdvPanel")
        sampling.setMinimumHeight(_scaled(170))
        sampling.setMaximumHeight(_scaled(188))
        sampling_box = QVBoxLayout(sampling)
        sampling_box.setContentsMargins(
            _scaled(11), _scaled(10), _scaled(11), _scaled(10)
        )
        sampling_box.setSpacing(_scaled(7))
        sampling_box.addWidget(self._field_label(self._tr("settings.frame_title")))
        self._segment = Segment(self._tr, self._tokens, sampling, compact=True)
        self._segment.set_policy(self._frame_policy)
        sampling_box.addWidget(self._segment)
        self._frame_note = note_label(
            self._tr(f"settings.frame_note_{self._frame_policy}")
        )
        sampling_box.addWidget(self._frame_note)
        columns.addWidget(sampling, 1)

        checks = QFrame()
        checks.setObjectName("AdvPanel")
        checks.setMinimumHeight(_scaled(170))
        checks.setMaximumHeight(_scaled(188))
        checks_box = QVBoxLayout(checks)
        checks_box.setContentsMargins(
            _scaled(11), _scaled(10), _scaled(11), _scaled(10)
        )
        checks_box.setSpacing(_scaled(5))
        self._upload_only = CheckRow(
            self._tr("settings.upload_only"), self._tokens, compact=True,
        )
        self._upload_only.setChecked(self._config.upload_target_only)
        checks_box.addWidget(self._upload_only)
        checks_box.addWidget(self._hint(self._tr("settings.upload_only_hint")))
        checks_box.addSpacing(_scaled(4))
        self._color_local = CheckRow(
            self._tr("settings.color_local"), self._tokens, compact=True,
        )
        self._color_local.setChecked(self._config.local_color_tags)
        checks_box.addWidget(self._color_local)
        checks_box.addWidget(self._hint(self._tr("settings.color_local_hint")))
        columns.addWidget(checks, 1)
        box.addLayout(columns, 0)

        facts = QHBoxLayout()
        facts.setContentsMargins(0, 0, 0, 0)
        facts.setSpacing(_scaled(8))
        card, self._adv_fact_frames, _detail = self._fact_card(
            self._tr("settings.adv_fact_frames")
        )
        facts.addWidget(card, 1)
        card, self._adv_fact_upload, _detail = self._fact_card(
            self._tr("settings.adv_fact_upload")
        )
        facts.addWidget(card, 1)
        card, self._adv_fact_color, _detail = self._fact_card(
            self._tr("settings.adv_fact_color")
        )
        facts.addWidget(card, 1)
        box.addLayout(facts)

        box.addStretch(1)
        note = QLabel(self._tr("settings.advanced_note"))
        note.setObjectName("Hint")
        note.setWordWrap(True)
        box.addWidget(note)
        self._adv_panel = page
        return page

    def _build_summary_rail(self) -> QWidget:
        rail = QWidget()
        rail.setObjectName("SettingsRail")
        rail.setFixedWidth(_scaled(214))
        column = QVBoxLayout(rail)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(_scaled(8))

        card = QFrame()
        card.setObjectName("RailCard")
        card_box = QVBoxLayout(card)
        card_box.setContentsMargins(
            _scaled(11), _scaled(10), _scaled(11), _scaled(9)
        )
        card_box.setSpacing(0)
        title = QLabel(self._tr("settings.summary_title"))
        title.setObjectName("RailTitle")
        card_box.addWidget(title)
        self._rail_mode = _RailLine(
            self._tr("settings.summary_mode"), "—", self._tokens, first=True,
        )
        self._rail_connection = _RailLine(
            self._tr("settings.summary_connection"), "—", self._tokens,
        )
        self._rail_custom = _RailLine(
            self._tr("settings.summary_my_labels"), "—", self._tokens,
        )
        self._rail_builtin = _RailLine(
            self._tr("settings.summary_builtin"), "—", self._tokens,
        )
        self._rail_frame = _RailLine(
            self._tr("settings.summary_frame"), "—", self._tokens,
        )
        for line in (
            self._rail_mode, self._rail_connection, self._rail_custom,
            self._rail_builtin, self._rail_frame,
        ):
            card_box.addWidget(line)
        self._rail_strip = _FrameStrip(
            self._tokens, cell_height=_scaled(6), parent=card
        )
        strip_row = QHBoxLayout()
        strip_row.setContentsMargins(0, _scaled(7), 0, 0)
        strip_row.addWidget(self._rail_strip)
        card_box.addLayout(strip_row)
        column.addWidget(card)

        scope = QFrame()
        scope.setObjectName("RailCard")
        scope_box = QVBoxLayout(scope)
        scope_box.setContentsMargins(
            _scaled(11), _scaled(10), _scaled(11), _scaled(9)
        )
        scope_box.setSpacing(0)
        scope_title = QLabel(self._tr("settings.summary_scope_title"))
        scope_title.setObjectName("RailTitle")
        scope_box.addWidget(scope_title)
        self._rail_scope_frames = _RailLine(
            self._tr("settings.fact_frames"), "—", self._tokens, first=True,
        )
        self._rail_scope_upload = _RailLine(
            self._tr("settings.summary_scope_upload"), "—", self._tokens,
        )
        self._rail_scope_original = _RailLine(
            self._tr("settings.summary_scope_original"), "—", self._tokens,
        )
        for line in (
            self._rail_scope_frames, self._rail_scope_upload,
            self._rail_scope_original,
        ):
            scope_box.addWidget(line)
        column.addWidget(scope)

        column.addStretch(1)
        note = QLabel(self._tr("settings.summary_note"))
        note.setObjectName("RailNote")
        note.setWordWrap(True)
        column.addWidget(note)
        return rail

    def _show_tab(self, key: str) -> None:
        page = self._pages.get(key)
        if page is None or self._stack is None:
            return
        self._stack.setCurrentWidget(page)
        for tab_key, tab in self._tabs.items():
            tab.setChecked(tab_key == key)

    # -- construction helpers --------------------------------------------

    def _size_dialog(self) -> None:
        screen = QGuiApplication.primaryScreen()
        available = screen.availableGeometry().height() if screen else 900
        if self._first_run:
            width = 760
            height = int(round(width * 815 / 760))
            ceiling = int(available * 0.9)
            floor = 620
        else:
            # Same 1200:760 proportion as the main window, at 75% scale,
            # then enlarged 1.15x: 1035x656 reads as the workspace shrunk
            # into a dialog without the controls feeling cramped.
            width = _scaled(900)
            height = int(round(width * 760 / 1200))
            ceiling = int(available * 0.88)
            floor = _scaled(520)
        self.resize(width, max(floor, min(height, ceiling)))

    def _rule(self) -> QFrame:
        rule = QFrame()
        rule.setObjectName("DialogRule")
        rule.setFixedHeight(1)
        return rule

    def _field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("FieldLabel")
        return label

    def _build_intro(self, body: QVBoxLayout) -> None:
        tr = self._tr
        if self._first_run:
            brand = QHBoxLayout()
            brand.setContentsMargins(0, 0, 0, 3)
            brand.setSpacing(8)
            mark = QLabel()
            mark.setFixedSize(22, 22)
            mark.setPixmap(brand_pixmap(
                22, self._tokens["accent"], self._tokens["on_accent"],
            ))
            brand.addWidget(mark)
            name = QLabel("Media Filter")
            name.setObjectName("BrandName")
            brand.addWidget(name)
            brand.addStretch(1)
            body.addLayout(brand)
            eyebrow = QLabel(tr("first_run.eyebrow"))
            eyebrow.setObjectName("FieldLabel")
            body.addWidget(eyebrow)
            title = QLabel(tr("first_run.title"))
            title.setStyleSheet(
                f"font-size: 19px; font-weight: 600; color: {self._tokens['ink']};"
            )
            body.addWidget(title)
            body.addWidget(lede_label(tr("first_run.lede")))
        else:
            body.addWidget(lede_label(tr("settings.lede")))

    def _build_mode_section(self, body: QVBoxLayout) -> None:
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(section_label(self._tr("settings.mode_title")))
        head.addStretch(1)
        if not self._first_run:
            head.addWidget(hint_label(self._tr("settings.mode_default_note")))
        body.addLayout(head)

        if self._first_run:
            self._mode_cards = ModeCardRow(self._tr, self._tokens, self)
            self._mode_cards.set_mode(self._mode)
            body.addWidget(self._mode_cards)
            self._mode_list = None
        else:
            self._mode_cards = None
            self._mode_list = DefaultModeList(self._tr, self._tokens, self)
            self._mode_list.set_mode(self._mode)
            self._mode_list.set_current(self._config.recognition_mode)
            body.addWidget(self._mode_list)
            self._current_note = QLabel(
                self._tr(
                    "settings.current_mode_note",
                    mode=mode_text(self._tr, self._config.recognition_mode),
                )
            )
            self._current_note.setObjectName("Hint")
            self._current_note.setWordWrap(True)
            body.addWidget(self._current_note)

    def _build_api_section(self, body: QVBoxLayout,
                           with_header: bool = True,
                           compact: bool = False) -> None:
        tr = self._tr
        if with_header:
            head = QHBoxLayout()
            head.setSpacing(_scaled(8) if compact else 8)
            head.addWidget(section_label(tr("settings.api_title")))
            head.addStretch(1)
            head.addWidget(hint_label(tr("settings.api_compatible")))
            body.addLayout(head)

        self._api_body = QWidget()
        api = QVBoxLayout(self._api_body)
        api.setContentsMargins(0, 0, 0, 0)
        api.setSpacing(_scaled(8) if compact else 8)

        api.addWidget(self._field_label(tr("settings.api_key")))
        key_row = QHBoxLayout()
        key_row.setSpacing(_scaled(8) if compact else 8)
        self._key = QLineEdit()
        self._key.setObjectName("FieldInput")
        self._key.setFixedHeight(_scaled(32) if compact else 34)
        self._key.setEchoMode(QLineEdit.EchoMode.Password)
        self._key.setPlaceholderText(tr("settings.api_key_placeholder"))
        self._key.setAccessibleName(tr("settings.api_key"))
        self._eye_action = self._key.addAction(
            line_icon(
                "eye", self._tokens["ink_3"], _scaled(15) if compact else 15
            ),
            QLineEdit.ActionPosition.TrailingPosition,
        )
        self._eye_action.setToolTip(tr("settings.show_key"))
        self._eye_action.triggered.connect(self._toggle_key_visibility)
        key_row.addWidget(self._key, 1)
        self._test_btn = dialog_button(tr("settings.test"), "ghost")
        self._test_btn.setMinimumWidth(_scaled(96) if compact else 96)
        self._test_btn.setFixedHeight(_scaled(32) if compact else 34)
        key_row.addWidget(self._test_btn)
        api.addLayout(key_row)

        self._key_required = QLabel(tr("settings.key_required"))
        self._key_required.setStyleSheet(
            f"color: {self._tokens['red']}; "
            f"font-size: {_scaled(11) if compact else 11}px;"
        )
        self._key_required.setVisible(False)
        api.addWidget(self._key_required)

        self._api_status = _StatusRow(self._tokens, large=compact)
        api.addWidget(self._api_status)

        api.addWidget(self._field_label("BASE URL"))
        self._base = QLineEdit()
        self._base.setObjectName("FieldInput")
        self._base.setFixedHeight(_scaled(32) if compact else 34)
        self._base.setPlaceholderText(DEFAULT_BASE_URL)
        self._base.setText(self._config.cloud_base_url or DEFAULT_BASE_URL)
        self._base.setAccessibleName("BASE URL")
        api.addWidget(self._base)

        model_head = QHBoxLayout()
        model_head.setSpacing(_scaled(8) if compact else 8)
        model_head.addWidget(self._field_label(tr("settings.model")))
        model_head.addStretch(1)
        self._model_count = count_label()
        model_head.addWidget(self._model_count)
        api.addLayout(model_head)

        self._picker = ModelPicker(tr, self._tokens, self, compact=compact)
        self._picker.setAccessibleName(tr("settings.model_title"))
        self._picker.selected.connect(self._on_model_selected)
        self._picker.refreshRequested.connect(self._load_models)
        api.addWidget(self._picker)

        self._model_status = _StatusRow(
            self._tokens, with_action=True, large=compact
        )
        api.addWidget(self._model_status)

        api.addWidget(note_label(tr("settings.key_note")))
        body.addWidget(self._api_body)

        self._local_api_note = note_label(tr("settings.local_api_note"))
        self._local_api_note.setVisible(False)
        body.addWidget(self._local_api_note)

    def _build_custom_section(self, body: QVBoxLayout) -> None:
        tr = self._tr
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(section_label(tr("settings.custom_title")))
        head.addStretch(1)
        self._custom_count = QLabel(
            tr("settings.custom_count", n=len(self._custom_labels))
        )
        self._custom_count.setObjectName("Hint")
        head.addWidget(self._custom_count)
        self._custom_edit = dialog_button(tr("settings.custom_edit"), "ghost")
        self._custom_edit.setFixedWidth(76)
        head.addWidget(self._custom_edit)
        body.addLayout(head)
        self._custom_note = note_label(tr("settings.custom_note"))
        body.addWidget(self._custom_note)

    def _build_tags_section(self, body: QVBoxLayout) -> None:
        tr = self._tr
        self._tags_panel = BuiltinTagsPanel(
            tr, self._tokens, self._enabled_tags,
            show_header=not self._first_run, parent=self,
        )
        if self._first_run:
            self._tags_toggle = QToolButton()
            self._tags_toggle.setObjectName("AdvHead")
            self._tags_toggle.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonTextBesideIcon
            )
            self._tags_toggle.setIcon(line_icon("chevron-right", self._tokens["ink_3"], 14))
            self._tags_toggle.setIconSize(QSize(14, 14))
            self._tags_toggle.setFixedHeight(34)
            self._tags_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
            self._tags_toggle.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            self._update_tags_toggle_text(False)
            self._tags_toggle.clicked.connect(self._toggle_tags)
            body.addWidget(self._tags_toggle)
            self._tags_panel.setVisible(False)
            body.addWidget(self._tags_panel)
        else:
            body.addWidget(self._tags_panel)

    def _build_advanced_section(self, body: QVBoxLayout) -> None:
        tr = self._tr
        self._adv_toggle = QToolButton()
        self._adv_toggle.setObjectName("AdvHead")
        self._adv_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self._adv_toggle.setIconSize(QSize(14, 14))
        self._adv_toggle.setFixedHeight(34)
        self._adv_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._adv_toggle.setText(tr("settings.advanced_title"))
        body.addWidget(self._adv_toggle)

        self._adv_panel = QWidget()
        panel = QVBoxLayout(self._adv_panel)
        panel.setContentsMargins(0, 2, 0, 0)
        panel.setSpacing(9)

        panel.addWidget(self._field_label(tr("settings.frame_title")))
        self._segment = Segment(tr, self._tokens, self)
        self._segment.set_policy(self._frame_policy)
        panel.addWidget(self._segment)
        self._frame_note = note_label(
            tr(f"settings.frame_note_{self._frame_policy}")
        )
        panel.addWidget(self._frame_note)

        self._upload_only = CheckRow(tr("settings.upload_only"), self._tokens)
        self._upload_only.setChecked(self._config.upload_target_only)
        panel.addWidget(self._upload_only)
        panel.addWidget(self._hint(tr("settings.upload_only_hint")))

        self._color_local = CheckRow(tr("settings.color_local"), self._tokens)
        self._color_local.setChecked(self._config.local_color_tags)
        panel.addWidget(self._color_local)
        panel.addWidget(self._hint(tr("settings.color_local_hint")))

        self._adv_panel.setVisible(_ADVANCED_OPEN)
        body.addWidget(self._adv_panel)
        self._sync_adv_head()
        self._adv_toggle.clicked.connect(self._toggle_advanced)

    def _hint(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("CheckHint")
        label.setWordWrap(True)
        label.setContentsMargins(_scaled(24), 0, 0, 0)
        return label

    def _build_footer(self, outer: QVBoxLayout) -> None:
        tr = self._tr
        self._footer_rule = self._rule()
        outer.addWidget(self._footer_rule)
        footer_widget = QWidget()
        footer_widget.setObjectName(
            "DialogFooter" if self._first_run else "SettingsFooter"
        )
        footer = QHBoxLayout(footer_widget)
        if self._first_run:
            footer.setContentsMargins(24, 10, 24, 20)
            footer.setSpacing(10)
        else:
            footer.setContentsMargins(
                _scaled(24), _scaled(10), _scaled(24), _scaled(20)
            )
            footer.setSpacing(_scaled(10))

        if self._first_run:
            footer.addStretch(1)
            self._skip_btn = dialog_button(tr("first_run.skip"))
            self._save_btn = dialog_button(tr("first_run.start"), "primary")
            footer.addWidget(self._skip_btn)
            footer.addWidget(self._save_btn)
        else:
            self._reset_btn = _link_button(
                tr("settings.reset"), self._tokens, large=True
            )
            footer.addWidget(self._reset_btn)
            footer.addStretch(1)
            self._cancel_btn = dialog_button(tr("settings.cancel"))
            self._save_btn = dialog_button(tr("settings.save"), "primary")
            for button in (self._cancel_btn, self._save_btn):
                button.setFixedHeight(_scaled(32))
            effect = QGraphicsDropShadowEffect(self._save_btn)
            effect.setBlurRadius(_scaled(4))
            effect.setOffset(0, 1)
            effect.setColor(QColor(20, 35, 44, 28))
            self._save_btn.setGraphicsEffect(effect)
            footer.addWidget(self._cancel_btn)
            footer.addWidget(self._save_btn)
        outer.addWidget(footer_widget)

    def _wire(self) -> None:
        if self._mode_cards is not None:
            self._mode_cards.modeChanged.connect(self._on_mode_changed)
        if self._mode_list is not None:
            self._mode_list.modeChanged.connect(self._on_mode_changed)
        self._tags_panel.changed.connect(self._on_tags_changed)
        self._segment.changed.connect(self._on_frame_policy_changed)
        self._test_btn.clicked.connect(self._load_models)
        self._key.textChanged.connect(self._on_key_changed)
        self._base.textChanged.connect(self._on_base_changed)
        self._save_btn.clicked.connect(self._save)
        self._custom_edit.clicked.connect(self._edit_custom_tags)
        if self._first_run:
            self._skip_btn.clicked.connect(self._skip)
        else:
            self._reset_btn.clicked.connect(self._reset_page)
            self._cancel_btn.clicked.connect(self.reject)
        if self._model_status.action is not None:
            self._model_status.action.clicked.connect(self._model_action)
        self._upload_only.toggled.connect(lambda _checked: self._update_advanced_facts())
        self._color_local.toggled.connect(lambda _checked: self._update_advanced_facts())
        self._update_save()
        self._refresh_mode_state()

    # -- initial state ----------------------------------------------------

    def _load_saved_state(self) -> None:
        tr = self._tr
        try:
            self._saved_key = secret_store.unprotect(self._config.cloud_api_key_dpapi)
            self._key.setText(self._saved_key)
        except secret_store.SecretStoreError as exc:
            self._key_error = str(exc)
            self._key_unreadable = True
            self._set_api_status("bad", tr("settings.key_unreadable"))

        if self._config.cloud_model:
            model = ModelInfo(
                id=self._config.cloud_model,
                name=self._config.cloud_model_name or self._config.cloud_model,
                context=self._config.cloud_model_context,
                capability=_config_capability(self._config.cloud_model_capability),
            )
            self._picker.set_model(model)
            self._apply_model_state(self._state_for_model(model), model=model)
        else:
            self._apply_model_state("none")

        if not self._key_error:
            self._set_api_status("idle", tr("settings.api_untested"))
        self._set_model_count(len(self._models))
        self._update_save()

    # -- mode / tags ------------------------------------------------------

    def _on_mode_changed(self, _mode: str) -> None:
        self._refresh_mode_state()

    def _on_frame_policy_changed(self, policy: str) -> None:
        if policy not in _FRAME_POLICIES:
            return
        self._frame_policy = policy
        self._frame_note.setText(self._tr(f"settings.frame_note_{policy}"))
        self._update_summary()

    def selected_mode(self) -> str:
        """The default mode currently drafted in the page."""
        if self._mode_cards is not None:
            return self._mode_cards.mode()
        if self._mode_list is not None:
            return self._mode_list.mode()
        return "local"

    def _selected_mode(self) -> str:
        return self.selected_mode()

    def _refresh_mode_state(self) -> None:
        mode = self._selected_mode()
        local = mode == "local"
        self._api_body.setEnabled(not local)
        # The prototype fades the whole API block in local mode; without this
        # the fields look editable even though clicks do nothing. The effect
        # stays detached (disabled) when the section is live so text rendering
        # is untouched.
        if self._api_effect is None:
            self._api_effect = QGraphicsOpacityEffect(self._api_body)
            self._api_effect.setOpacity(0.55)
            self._api_body.setGraphicsEffect(self._api_effect)
        self._api_effect.setEnabled(local)
        self._local_api_note.setVisible(local)
        if self._first_run:
            self._custom_edit.setEnabled(not local)
            self._custom_note.setText(
                self._tr("settings.local_custom_note") if local
                else self._tr("settings.custom_note")
            )
        if local:
            self._key_required.setVisible(False)
        else:
            self._update_save()
        self._update_summary()

    def _on_tags_changed(self, count: int) -> None:
        if self._first_run:
            self._update_tags_toggle_text(self._tags_panel.isVisible())
        self._update_summary()

    def _update_tags_toggle_text(self, expanded: bool) -> None:
        count = self._tags_panel.count_enabled()
        text = self._tr("settings.tags_collapsed", n=count)
        if expanded:
            text = self._tr("settings.tags_expanded", n=count)
        self._tags_toggle.setText("  " + text)
        self._tags_toggle.setIcon(
            line_icon(
                "chevron-down" if expanded else "chevron-right",
                self._tokens["ink_3"], 14,
            )
        )

    def _toggle_tags(self) -> None:
        visible = self._tags_panel.isHidden()
        self._tags_panel.setVisible(visible)
        self._update_tags_toggle_text(visible)

    def _toggle_advanced(self) -> None:
        global _ADVANCED_OPEN
        if self._adv_panel is None or self._adv_toggle is None:
            return
        _ADVANCED_OPEN = not _ADVANCED_OPEN
        self._adv_panel.setVisible(_ADVANCED_OPEN)
        self._sync_adv_head()

    def _sync_adv_head(self) -> None:
        # isVisible() is False until the dialog is shown, which used to leave
        # the chevron pointing right on a panel that was already open.
        if self._adv_panel is None or self._adv_toggle is None:
            return
        expanded = not self._adv_panel.isHidden()
        self._adv_toggle.setIcon(
            line_icon(
                "chevron-down" if expanded else "chevron-right",
                self._tokens["ink_3"], 14,
            )
        )

    def _edit_custom_tags(self) -> None:
        dialog = MyTagsDialog(self._custom_labels, self._tr, self, tokens=self._tokens)
        if dialog.exec() == int(MyTagsDialog.DialogCode.Accepted):
            self._custom_labels = dialog.labels()
            self._refresh_custom_state()

    def _refresh_custom_state(self) -> None:
        if self._first_run:
            self._custom_count.setText(
                self._tr("settings.custom_count", n=len(self._custom_labels))
            )
        else:
            self._custom_count.setText(self._tr(
                "settings.custom_ratio", n=len(self._custom_labels), max=10,
            ))
            self._rebuild_custom_chips()
        self._update_summary()

    def _rebuild_custom_chips(self) -> None:
        if not hasattr(self, "_custom_chips"):
            return
        layout = self._custom_chips_layout
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        if not self._custom_labels:
            empty = QLabel(self._tr("settings.tags_empty"))
            empty.setObjectName("TagsEmpty")
            layout.addWidget(empty)
        else:
            for label in self._custom_labels:
                chip = QLabel(label)
                chip.setObjectName("PreviewChip")
                chip.setFixedHeight(22)
                chip.setToolTip(label)
                layout.addWidget(chip)
        self._custom_chips.updateGeometry()

    # -- API / model state (worker plumbing kept from the original page) ---

    def _set_api_status(self, tone: str, text: str) -> None:
        self._api_tone = tone
        self._api_text = text
        self._api_status.set_status(tone, text)
        self._update_summary()

    def _connection_label(self) -> str:
        mode = self._selected_mode()
        if mode == "local":
            return self._tr("settings.connection_local")
        if not hasattr(self, "_key") or not self._key.text().strip():
            return self._tr("settings.connection_unset")
        if self._api_tone == "ok":
            return self._tr("settings.connection_ok")
        if self._api_tone == "busy":
            return self._tr("settings.connection_busy")
        if self._api_tone == "bad":
            return self._tr("settings.connection_bad")
        return self._tr("settings.connection_untested")

    def _update_advanced_facts(self) -> None:
        if not hasattr(self, "_adv_fact_frames"):
            return
        self._adv_fact_frames.setText(
            self._tr(f"settings.frame_{self._frame_policy}")
        )
        self._adv_fact_upload.setText(
            self._tr("settings.on") if self._upload_only.isChecked()
            else self._tr("settings.off")
        )
        self._adv_fact_color.setText(
            self._tr("settings.on") if self._color_local.isChecked()
            else self._tr("settings.off")
        )

    def _update_summary(self) -> None:
        """Keep the header chips, tab metas and right rail in one state."""
        if not hasattr(self, "_chip_mode") or not hasattr(self, "_tags_panel"):
            return
        mode = self._selected_mode()
        mode_name = mode_text(self._tr, mode)
        scope = self._tr(f"mode.scope_{mode}")
        builtin = self._tags_panel.count_enabled()
        custom = len(self._custom_labels)
        policy = self._frame_policy
        active = {"local": 0, "hybrid": 3, "cloud": 8}.get(mode, 0)

        self._chip_mode.setText(f"{mode_name} · {scope}")
        self._chip_tags.setText(self._tr("settings.header_tags", n=builtin))
        self._chip_frame.setText(self._tr(f"settings.frame_chip_{policy}"))

        self._tabs["mode"].set_meta(mode_name)
        self._tabs["api"].set_meta(self._connection_label())
        tags_meta = (
            f"{custom} + {builtin}" if custom
            else self._tr("settings.header_tags", n=builtin)
        )
        self._tabs["tags"].set_meta(tags_meta)
        self._tabs["advanced"].set_meta(self._tr(f"settings.frame_{policy}"))

        self._scope_note.setText(self._tr(f"settings.scope_note_{mode}"))
        self._scope_strip.set_active(active)

        self._fact_scope_value.setText(self._tr(f"settings.fact_scope_{mode}"))
        self._fact_scope_detail.setText(
            self._tr(f"settings.fact_scope_{mode}_detail")
        )
        self._fact_frames_value.setText(
            self._tr(f"settings.fact_frames_{policy}")
        )
        self._fact_frames_detail.setText(self._tr("settings.fact_frames_detail"))
        self._fact_original_value.setText(self._tr("settings.fact_original_value"))
        self._fact_original_detail.setText(
            self._tr("settings.fact_original_detail")
        )

        self._rail_mode.set_value(f"{mode_name} · {scope}")
        self._rail_connection.set_value(self._connection_label())
        self._rail_custom.set_value(f"{custom} / 10")
        self._rail_builtin.set_value(f"{builtin} / {len(ALL_TAG_IDS)}")
        self._rail_frame.set_value(self._tr(f"settings.frame_{policy}"))
        self._rail_strip.set_active(active)
        self._rail_scope_frames.set_value(
            self._tr(f"settings.scope_frames_{policy}")
        )
        self._rail_scope_upload.set_value(
            self._tr(f"settings.summary_upload_{mode}")
        )
        self._rail_scope_original.set_value(
            self._tr("settings.summary_original")
        )
        if not self._first_run and hasattr(self, "_custom_count"):
            self._custom_count.setText(self._tr(
                "settings.custom_ratio", n=custom, max=10,
            ))
        self._update_advanced_facts()

    def _set_model_status(
        self, tone: str, text: str, detail: str = "", action: str = ""
    ) -> None:
        self._model_status.set_status(tone, text, detail, action)

    def _set_model_count(self, count: int) -> None:
        if count:
            self._model_count.setText(
                _t(self._tr, "settings.model_count", "{n} 个模型").format(n=count)
            )
        else:
            self._model_count.setText("")

    def _update_save(self) -> None:
        self._save_btn.setEnabled(self._model_state not in ("text", "checking"))

    def _toggle_key_visibility(self) -> None:
        if self._key.echoMode() == QLineEdit.EchoMode.Password:
            self._key.setEchoMode(QLineEdit.EchoMode.Normal)
            self._eye_action.setIcon(line_icon("eye-off", self._tokens["ink_3"], 15))
            self._eye_action.setToolTip(self._tr("settings.hide_key"))
        else:
            self._key.setEchoMode(QLineEdit.EchoMode.Password)
            self._eye_action.setIcon(line_icon("eye", self._tokens["ink_3"], 15))
            self._eye_action.setToolTip(self._tr("settings.show_key"))

    def _on_key_changed(self) -> None:
        self._key_error = ""
        self._key_unreadable = False
        self._key_required.setVisible(False)
        if self._key.text().strip() != self._saved_key:
            self._set_api_status("idle", self._tr("settings.api_untested"))
        self._update_summary()

    def _on_base_changed(self) -> None:
        if normalize_base_url(self._base.text()) != self._loaded_base:
            self._set_api_status("idle", self._tr("settings.api_untested"))
            current = self._picker.model()
            if current is not None:
                self._apply_model_state(
                    self._state_for_model(current, trust_saved=False), model=current
                )

    # -- model loading ----------------------------------------------------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._auto_started:
            return
        self._auto_started = True
        if self._selected_mode() != "local":
            QTimer.singleShot(0, self._auto_load)

    def _auto_load(self) -> None:
        try:
            if not self.isVisible():
                return
        except RuntimeError:
            return
        base = self._base.text().strip()
        key = self._key.text().strip()
        if not base:
            return
        if key or "127.0.0.1" in base or "localhost" in base:
            self._load_models()

    def _load_models(self) -> None:
        if self._list_worker is not None and self._list_worker.isRunning():
            return
        base = normalize_base_url(self._base.text())
        if not base:
            self._set_api_status("bad", self._tr("settings.base_required"))
            self._base.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        key = self._key.text().strip()
        self._request_base = base
        self._test_btn.setEnabled(False)
        self._test_btn.setText(self._tr("settings.testing"))
        self._set_api_status("busy", self._tr("settings.api_testing"))
        self._picker.set_loading(True)

        worker = _ModelListWorker(base, key)
        _track_worker(worker)
        worker.ok.connect(self._on_models_loaded)
        worker.failed.connect(self._on_models_failed)
        worker.finished.connect(self._list_finished)
        self._list_worker = worker
        worker.start()

    def _list_finished(self) -> None:
        if self.sender() is not self._list_worker:
            return
        self._list_worker = None
        self._test_btn.setEnabled(True)
        self._test_btn.setText(self._tr("settings.test"))
        self._picker.set_loading(False)

    def _on_models_loaded(self, models: list[ModelInfo]) -> None:
        current_base = normalize_base_url(self._base.text())
        if self._request_base and current_base != self._request_base:
            return
        self._models = models
        self._loaded_base = self._request_base or current_base
        self._picker.set_models(models)
        self._set_model_count(len(models))
        self._set_api_status("ok", self._tr("settings.api_ok", n=len(models)))
        current = self._picker.model()
        if current is None:
            saved_id = self._config.cloud_model
            chosen = next((m for m in models if m.id == saved_id), None)
            if chosen is None:
                chosen = next((m for m in models if m.recommended), None)
            if chosen is None:
                chosen = next((m for m in models if m.capability == IMAGE), None)
            if chosen is None and models:
                chosen = models[0]
            if chosen is not None:
                self._picker.set_model(chosen)
                self._apply_model_state(self._state_for_model(chosen), model=chosen)
        elif self._model_state != "checking":
            self._apply_model_state(self._state_for_model(current), model=current)

    def _on_models_failed(self, message: str) -> None:
        if (
            self._request_base
            and normalize_base_url(self._base.text()) != self._request_base
        ):
            return
        self._set_api_status("bad", self._tr("settings.api_bad", msg=_short(message)))
        self._picker.set_error(message)
        if self._picker.model() is None:
            self._apply_model_state("none")

    # -- model state ------------------------------------------------------

    def _cache_key(self, model: ModelInfo) -> str:
        base = normalize_base_url(self._base.text())
        return f"{base}|{model.id}|png"

    def _state_for_model(self, model: ModelInfo, trust_saved: bool = True) -> str:
        cached = self._pending_cache.get(
            self._cache_key(model),
            self._config.cloud_model_cache.get(self._cache_key(model), ""),
        )
        if cached == VERIFIED_IMAGE:
            return "verified"
        if cached == TEXT:
            return "text"
        if trust_saved and model.capability == VERIFIED_IMAGE:
            return "verified"
        if model.capability == IMAGE:
            return "meta"
        if model.capability == TEXT:
            return "text"
        return "unknown"

    def _on_model_selected(self, model: ModelInfo) -> None:
        self._apply_model_state(self._state_for_model(model), model=model)

    def _apply_model_state(self, state: str, model: ModelInfo | None = None) -> None:
        self._model_state = state
        if model is not None:
            if state == "verified":
                self._picker.set_selected_capability(VERIFIED_IMAGE)
            elif state == "text":
                self._picker.set_selected_capability(TEXT)
            elif state == "meta":
                self._picker.set_selected_capability(model.capability)
            elif state == "checking":
                pass
            else:
                self._picker.set_selected_capability(UNKNOWN)

        tr = self._tr
        if state == "none":
            self._set_model_status("idle", tr("settings.model_none_status"), "")
        elif state == "meta":
            self._set_model_status(
                "ok", tr("settings.model_status_image"),
                tr("settings.model_detail_meta"), tr("settings.model_verify"),
            )
        elif state == "verified":
            self._set_model_status(
                "ok", tr("settings.model_status_image"),
                tr("settings.model_detail_verified"), tr("settings.model_reverify"),
            )
        elif state == "text":
            self._set_model_status(
                "bad", tr("settings.model_status_text"),
                tr("settings.model_detail_text"), tr("settings.model_change"),
            )
        elif state == "checking":
            self._set_model_status(
                "busy", tr("settings.model_status_checking"),
                tr("settings.model_detail_checking"), "",
            )
        elif state == "error":
            self._set_model_status(
                "bad", tr("settings.model_status_error"),
                tr("settings.model_detail_error"), tr("settings.model_retry"),
            )
        else:
            self._set_model_status(
                "busy", tr("settings.model_status_unknown"),
                tr("settings.model_detail_unknown"), tr("settings.model_verify"),
            )
        self._update_save()

    def _model_action(self) -> None:
        model = self._picker.model()
        if model is None or self._model_state == "text":
            self._picker.open_popup()
            return
        if self._model_state in ("meta", "verified", "unknown", "error"):
            self._probe_model(model)

    def _probe_model(self, model: ModelInfo) -> None:
        if self._probe_worker is not None and self._probe_worker.isRunning():
            return
        base = normalize_base_url(self._base.text())
        if not base:
            self._set_api_status("bad", self._tr("settings.base_required"))
            self._base.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        key = self._key.text().strip()
        self._probe_base = base
        self._probe_key = self._cache_key(model)
        self._apply_model_state("checking", model=model)
        worker = _ProbeWorker(base, key, model.id)
        _track_worker(worker)
        worker.done.connect(lambda result: self._on_probe_done(model, result))
        worker.failed.connect(lambda message: self._on_probe_failed(model, message))
        worker.finished.connect(self._probe_finished)
        self._probe_worker = worker
        worker.start()

    def _probe_finished(self) -> None:
        if self.sender() is not self._probe_worker:
            return
        self._probe_worker = None

    def _on_probe_done(self, model: ModelInfo, result) -> None:
        capability = getattr(result, "capability", UNKNOWN)
        detail = getattr(result, "detail", "")
        key = self._probe_key or self._cache_key(model)
        current = self._picker.model()
        same_model = current is not None and current.id == model.id
        same_context = (
            same_model
            and normalize_base_url(self._base.text()) == self._probe_base
        )
        if capability == VERIFIED_IMAGE:
            self._pending_cache[key] = VERIFIED_IMAGE
            if same_context:
                self._probe_at = _now_iso()
                self._apply_model_state("verified", model=model)
        elif capability == TEXT:
            self._pending_cache[key] = TEXT
            if same_context:
                self._probe_at = _now_iso()
                self._apply_model_state("text", model=model)
        else:
            self._pending_cache.pop(key, None)
            if not same_context:
                return
            self._picker.set_selected_capability(UNKNOWN)
            self._set_model_status(
                "busy", self._tr("settings.model_status_unknown"),
                _short(detail) if detail else self._tr("settings.model_detail_unknown"),
                self._tr("settings.model_retry"),
            )
            self._model_state = "unknown"
            self._update_save()

    def _on_probe_failed(self, model: ModelInfo, message: str) -> None:
        current = self._picker.model()
        if current is None or current.id != model.id:
            return
        if normalize_base_url(self._base.text()) != self._probe_base:
            return
        self._model_state = "error"
        self._set_model_status(
            "bad", self._tr("settings.model_status_error"),
            _short(message), self._tr("settings.model_retry"),
        )
        self._update_save()

    # -- reset / save -----------------------------------------------------

    def _reset_page(self) -> None:
        answer = message_box(
            self, "question", self._tr("settings.title"),
            self._tr("settings.reset_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != int(QMessageBox.StandardButton.Yes):
            return
        self._key.clear()
        self._base.setText(DEFAULT_BASE_URL)
        self._models = []
        self._pending_cache = {}
        self._probe_at = ""
        self._picker.set_model(None)
        self._picker.set_models([])
        self._set_model_count(0)
        self._set_api_status("idle", self._tr("settings.api_untested"))
        self._apply_model_state("none")
        if self._mode_list is not None:
            self._mode_list.set_mode("local")
        if self._mode_cards is not None:
            self._mode_cards.set_mode("local")
        self._tags_panel.set_enabled_ids(list(DEFAULT_ENABLED))
        self._frame_policy = "auto"
        self._segment.set_policy("auto")
        self._on_frame_policy_changed("auto")
        self._upload_only.setChecked(True)
        self._color_local.setChecked(True)
        self._refresh_mode_state()
        self._show_tab("mode")
        self._update_save()
        self._update_summary()

    def _skip(self) -> None:
        self._config.recognition_mode = self._selected_mode()
        self._config.first_run_prompted = True
        self._config.save()
        self.reject()

    def _save(self) -> None:
        tr = self._tr
        mode = self._selected_mode()
        key = self._key.text().strip()
        base = normalize_base_url(self._base.text())
        model = self._picker.model()
        previous_model = self._config.cloud_model

        if mode in ("hybrid", "cloud") and not key:
            self._show_tab("api")
            self._key_required.setVisible(True)
            self._key.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        if self._model_state == "text":
            self._show_tab("api")
            self._apply_model_state("text", model=model)
            return
        if (model is not None or key) and not base:
            self._show_tab("api")
            self._set_api_status("bad", tr("settings.base_required"))
            self._base.setFocus(Qt.FocusReason.OtherFocusReason)
            return

        if key != self._saved_key:
            if key:
                try:
                    self._config.cloud_api_key_dpapi = secret_store.protect(key)
                except secret_store.SecretStoreError as exc:
                    message_box(self, "critical", tr("settings.title"), str(exc))
                    return
                self._config.cloud_api_key_hint = secret_store.key_hint(key)
            else:
                self._config.cloud_api_key_dpapi = ""
                self._config.cloud_api_key_hint = ""
        elif self._key_unreadable and not key:
            self._config.cloud_api_key_dpapi = ""
            self._config.cloud_api_key_hint = ""

        self._config.cloud_base_url = base or DEFAULT_BASE_URL
        if model is None:
            self._config.cloud_model = ""
            self._config.cloud_model_name = ""
            self._config.cloud_model_context = ""
            self._config.cloud_model_capability = UNKNOWN
            self._config.cloud_model_probe_at = ""
        else:
            self._config.cloud_model = model.id
            self._config.cloud_model_name = model.name
            self._config.cloud_model_context = model.context
            if self._model_state == "verified":
                capability = VERIFIED_IMAGE
            elif self._model_state == "text":
                capability = TEXT
            elif self._model_state == "meta":
                capability = model.capability
            else:
                capability = UNKNOWN
            self._config.cloud_model_capability = capability
            if self._model_state in ("verified", "text"):
                self._config.cloud_model_probe_at = self._probe_at or _now_iso()
            elif model.id != previous_model:
                self._config.cloud_model_probe_at = self._probe_at
        for cache_key, value in self._pending_cache.items():
            self._config.cloud_model_cache[cache_key] = value

        self._config.recognition_mode = mode
        enabled = self._tags_panel.enabled_ids()
        self._config.tag_palette = [tag for tag in ALL_TAG_IDS if tag in enabled]
        self._config.custom_labels = list(self._custom_labels)
        self._config.frame_policy = self._segment.policy()
        self._config.upload_target_only = self._upload_only.isChecked()
        self._config.local_color_tags = self._color_local.isChecked()
        self._config.first_run_done = True
        self._config.first_run_prompted = True
        self._config.guide_dismissed = True
        self.accept()


def _config_capability(value: str) -> str:
    return value if value in (IMAGE, VERIFIED_IMAGE, TEXT, UNKNOWN) else UNKNOWN


def _short(text: str, limit: int = 110) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")