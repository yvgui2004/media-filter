"""Recognition-mode widgets shared by the welcome flow, settings and popover.

Three modes drive how much leaves the machine:

* ``local``  — built-in tags only, nothing uploaded
* ``hybrid`` — local first, upload only frames that may hit the user's labels
* ``cloud``  — upload every sampled frame
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget,
)

from ..tokens import parse_color

MODES: tuple[str, ...] = ("local", "hybrid", "cloud")

#: i18n key suffixes; the widgets fall back to Chinese when a key is missing.
MODE_KEYS: dict[str, dict[str, str]] = {
    "local": {
        "name": "mode.local.name",
        "desc": "mode.local.desc",
        "foot": "mode.local.foot",
        "target": "mode.local.target",
    },
    "hybrid": {
        "name": "mode.hybrid.name",
        "desc": "mode.hybrid.desc",
        "foot": "mode.hybrid.foot",
        "target": "mode.hybrid.target",
    },
    "cloud": {
        "name": "mode.cloud.name",
        "desc": "mode.cloud.desc",
        "foot": "mode.cloud.foot",
        "target": "mode.cloud.target",
    },
}

MODE_FALLBACK: dict[str, dict[str, str]] = {
    "local": {
        "name": "本地",
        "desc": "只用本机模型识别，任何画面都不上传。",
        "foot": "免费 · 离线",
        "target": "不发送任何画面，全部在本机完成。",
    },
    "hybrid": {
        "name": "混合",
        "desc": "本地先筛，只把可能命中「我的标签」的画面发给云端。",
        "foot": "推荐 · 仅目标上传",
        "target": "只上传可能命中「我的标签」的画面。",
    },
    "cloud": {
        "name": "全云端",
        "desc": "所有抽帧都上传，标签和自定义标签都由云端识别。",
        "foot": "最准 · 全部上传",
        "target": "全部抽帧都会上传。",
    },
}


def mode_text(tr, mode: str, field: str = "name") -> str:
    keys = MODE_KEYS.get(mode)
    if keys is None:
        return mode
    key = keys[field]
    text = tr(key)
    fallback = MODE_FALLBACK.get(mode, {}).get(field, mode)
    return fallback if text == key else text


# The tabbed settings page renders the cards at 1.15x their prototype size.
_COMPACT_SCALE = 1.15


def _scaled(value: float) -> int:
    return int(round(value * _COMPACT_SCALE))


def _label(text: str, name: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    return label


class RadioDot(QWidget):
    """14px radio dot matching the HTML prototype."""

    def __init__(self, tokens: dict[str, str], size: int = 14,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._checked = False
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def set_checked(self, checked: bool) -> None:
        if checked != self._checked:
            self._checked = checked
            self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        k = self.width() / 14
        rect = QRectF(self.rect()).adjusted(0.75 * k, 0.75 * k,
                                            -0.75 * k, -0.75 * k)
        if self._checked:
            accent = parse_color(self._tokens["accent"])
            painter.setPen(QPen(accent, 1.5 * k))
            painter.setBrush(accent)
            painter.drawEllipse(rect)
            inner = rect.adjusted(4 * k, 4 * k, -4 * k, -4 * k)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(parse_color(self._tokens["on_accent"]))
            painter.drawEllipse(inner)
        else:
            painter.setPen(QPen(parse_color(self._tokens["ink_3"]), 1.5 * k))
            painter.setBrush(parse_color(self._tokens["surface"]))
            painter.drawEllipse(rect)
        painter.end()


class ModeCard(QAbstractButton):
    """Large selectable card used by the first-run welcome page."""

    def __init__(self, mode: str, tr, tokens: dict[str, str],
                 parent: QWidget | None = None, compact: bool = False) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._mode = mode
        self._compact = compact
        self._hover = False
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(_scaled(104) if compact else 112)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        if compact:
            layout.setContentsMargins(
                _scaled(11), _scaled(10), _scaled(11), _scaled(10)
            )
            layout.setSpacing(_scaled(5))
        else:
            layout.setContentsMargins(12, 12, 12, 12)
            layout.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(_scaled(7) if compact else 7)
        self.dot = RadioDot(tokens, _scaled(14) if compact else 14)
        self.title = _label(mode_text(tr, mode), "ModeTitle")
        top.addWidget(self.dot)
        top.addWidget(self.title)
        top.addStretch(1)
        layout.addLayout(top)

        self.desc = _label(mode_text(tr, mode, "desc"), "ModeDesc")
        self.desc.setWordWrap(True)
        layout.addWidget(self.desc)
        layout.addStretch(1)
        self.foot = _label(mode_text(tr, mode, "foot"), "ModeFoot")
        layout.addWidget(self.foot)

        self._sync()

    def mode(self) -> str:
        return self._mode

    def sizeHint(self) -> QSize:
        if self._compact:
            return QSize(_scaled(229), _scaled(104))
        return QSize(229, 112)

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def checkStateSet(self) -> None:  # noqa: N802
        self._sync()

    def nextCheckState(self) -> None:  # noqa: N802
        # Clicking the selected card must not clear the whole group.
        if not self.isChecked():
            super().nextCheckState()

    def _sync(self) -> None:
        self.dot.set_checked(self.isChecked())
        if self.isChecked():
            size = _scaled(10) if self._compact else 11
            self.foot.setStyleSheet(
                f"font-size: {size}px; font-weight: 600; color: {self._tokens['accent']};"
            )
        else:
            self.foot.setStyleSheet("")
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        inset = 0.5 if self._compact else 0.75
        rect = QRectF(self.rect()).adjusted(inset, inset, -inset, -inset)
        tokens = self._tokens
        selected = self.isChecked()
        if selected:
            painter.setPen(QPen(
                parse_color(tokens["accent"]), 1.0 if self._compact else 1.5
            ))
            painter.setBrush(parse_color(tokens["accent_soft"]))
        else:
            painter.setPen(QPen(
                parse_color(tokens["ink_3"] if self._hover else tokens["line_strong"]),
                1.0,
            ))
            painter.setBrush(parse_color(tokens["surface"]))
        painter.drawRoundedRect(rect, _scaled(10) if self._compact else 10,
                                _scaled(10) if self._compact else 10)
        painter.end()


class DefaultModeRow(QAbstractButton):
    """Compact radio row used by the settings page ("默认识别方式")."""

    def __init__(self, mode: str, tr, tokens: dict[str, str],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._mode = mode
        self._hover = False
        self._current = False
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(58)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 9, 10, 9)
        layout.setSpacing(9)
        self.dot = RadioDot(tokens)
        layout.addWidget(self.dot, 0, Qt.AlignmentFlag.AlignTop)

        copy = QVBoxLayout()
        copy.setContentsMargins(0, 0, 0, 0)
        copy.setSpacing(2)
        name_row = QHBoxLayout()
        name_row.setSpacing(6)
        self.title = _label(mode_text(tr, mode), "ModeTitle")
        self.badge = _label(tr("mode.current_badge"), "CurrentBadge")
        self.badge.setVisible(False)
        name_row.addWidget(self.title)
        name_row.addWidget(self.badge)
        name_row.addStretch(1)
        copy.addLayout(name_row)
        self.desc = _label(mode_text(tr, mode, "desc"), "ModeDesc")
        self.desc.setWordWrap(True)
        copy.addWidget(self.desc)
        layout.addLayout(copy, 1)

        self._sync()

    def mode(self) -> str:
        return self._mode

    def set_current(self, current: bool) -> None:
        self._current = current
        self.badge.setVisible(current)
        self.update()

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def checkStateSet(self) -> None:  # noqa: N802
        self._sync()

    def nextCheckState(self) -> None:  # noqa: N802
        if not self.isChecked():
            super().nextCheckState()

    def _sync(self) -> None:
        self.dot.set_checked(self.isChecked())
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        tokens = self._tokens
        if self.isChecked():
            painter.setPen(QPen(parse_color(tokens["accent"]), 1.0))
            painter.setBrush(parse_color(tokens["accent_soft"]))
        else:
            painter.setPen(QPen(
                parse_color(tokens["line_strong"] if self._hover else tokens["line"]),
                1.0,
            ))
            painter.setBrush(parse_color(tokens["surface"]))
        painter.drawRoundedRect(rect, 8, 8)
        painter.end()


class ModeCardRow(QWidget):
    """Three mode cards in a horizontal row."""

    modeChanged = Signal(str)

    def __init__(self, tr, tokens: dict[str, str],
                 parent: QWidget | None = None, compact: bool = False) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(_scaled(8) if compact else 12)
        self.cards: dict[str, ModeCard] = {}
        for mode in MODES:
            card = ModeCard(mode, tr, tokens, self, compact=compact)
            card.clicked.connect(lambda *_args, m=mode: self.modeChanged.emit(m))
            self.cards[mode] = card
            layout.addWidget(card, 1)

    def set_mode(self, mode: str) -> None:
        card = self.cards.get(mode)
        if card is not None:
            card.setChecked(True)

    def mode(self) -> str:
        for mode, card in self.cards.items():
            if card.isChecked():
                return mode
        return "local"


class DefaultModeList(QWidget):
    """The compact three-row default-mode picker."""

    modeChanged = Signal(str)

    def __init__(self, tr, tokens: dict[str, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.rows: dict[str, DefaultModeRow] = {}
        for mode in MODES:
            row = DefaultModeRow(mode, tr, tokens, self)
            row.clicked.connect(lambda *_args, m=mode: self.modeChanged.emit(m))
            self.rows[mode] = row
            layout.addWidget(row)

    def set_mode(self, mode: str) -> None:
        row = self.rows.get(mode)
        if row is not None:
            row.setChecked(True)

    def set_current(self, mode: str) -> None:
        for key, row in self.rows.items():
            row.set_current(key == mode)

    def mode(self) -> str:
        for mode, row in self.rows.items():
            if row.isChecked():
                return mode
        return "local"