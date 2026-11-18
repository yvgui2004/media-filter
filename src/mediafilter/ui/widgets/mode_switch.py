"""Main-window AI split button, mode popover and upload confirmation card."""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlparse

from PySide6.QtCore import (
    QEasingCurve, QPoint, QPropertyAnimation, QRectF, QSize, Qt, QTimer, Signal,
)
from PySide6.QtGui import (
    QFont, QFontMetrics, QGuiApplication, QPainter, QPen,
)
from PySide6.QtWidgets import (
    QAbstractButton, QDialog, QFrame, QGraphicsOpacityEffect, QHBoxLayout,
    QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from ..dialog_base import AppDialog, dialog_button
from ..icons import line_icon
from ..motion import FAST, animations_enabled, rise_popup
from ..tokens import LIGHT, parse_color
from .flow_layout import FlowLayout
from .mode_widgets import MODES, mode_text
from .my_tags_dialog import MyTagsDialog


def _transparent(label: QLabel) -> QLabel:
    label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    label.setStyleSheet("background: transparent;")
    return label


def _mix(base: str, tint: str, amount: float) -> str:
    """Opaque blend, so the hairline border reads at fractional DPI."""
    a = parse_color(base)
    b = parse_color(tint)
    channels = (
        round(a.red() + (b.red() - a.red()) * amount),
        round(a.green() + (b.green() - a.green()) * amount),
        round(a.blue() + (b.blue() - a.blue()) * amount),
    )
    return "#%02X%02X%02X" % channels


class _AiMain(QPushButton):
    def __init__(self, tokens: dict[str, str], tr, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._tr = tr
        self.setObjectName("AiMain")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(32)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 8, 0)
        layout.setSpacing(8)
        self.icon_label = _transparent(QLabel())
        self.icon_label.setFixedSize(14, 14)
        layout.addWidget(self.icon_label)
        self.text_label = _transparent(QLabel(tr("toolbar.ai")))
        font = QFont(self.text_label.font())
        font.setPixelSize(12)
        font.setWeight(QFont.Weight.DemiBold)
        self.text_label.setFont(font)
        self.text_label.setStyleSheet("background: transparent;")
        layout.addWidget(self.text_label)
        self.chip = _transparent(QLabel(mode_text(tr, "local")))
        chip_font = QFont(self.chip.font())
        chip_font.setPixelSize(11)
        chip_font.setWeight(QFont.Weight.Medium)
        self.chip.setFont(chip_font)
        self.chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Keep the hairline beside the mode word text-high, not full height.
        self.chip.setFixedHeight(16)
        layout.addWidget(self.chip)
        self.apply_tokens(tokens)

    def apply_tokens(self, tokens: dict[str, str]) -> None:
        self._tokens = tokens
        self.text_label.setStyleSheet(
            f"background: transparent; color: {tokens['ink']}; font-size: 12px;"
        )
        self.chip.setStyleSheet(
            "background: transparent; color: %s; font-size: 11px; padding-left: 8px;"
            "border-left: 1px solid %s;" % (tokens["ink_3"], tokens["line"])
        )

    def set_icon(self, name: str, color: str) -> None:
        self.icon_label.setPixmap(line_icon(name, color, 14).pixmap(14, 14))

    def sizeHint(self) -> QSize:
        layout = self.layout()
        hint = layout.sizeHint() if layout is not None else super().sizeHint()
        return QSize(max(96, hint.width()), 32)


class _AiCaret(QPushButton):
    def __init__(self, tokens: dict[str, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._open = False
        self._hover = False
        self.setObjectName("AiCaret")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(26, 32)
        self.apply_tokens(tokens)

    def set_open(self, open_: bool) -> None:
        if self._open == open_:
            return
        self._open = open_
        self._sync_bg()
        self._apply_icon()

    def enterEvent(self, event) -> None:
        self._hover = True
        self._sync_bg()
        self._apply_icon()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self._sync_bg()
        self._apply_icon()
        super().leaveEvent(event)

    def apply_tokens(self, tokens: dict[str, str]) -> None:
        self._tokens = tokens
        self._sync_bg()
        self._apply_icon()

    def _sync_bg(self) -> None:
        # Painted here rather than via :hover: the split shell sets its own
        # stylesheet, and a deterministic property is easier to reason about.
        active = self._hover or self._open
        bg = self._tokens["accent_soft"] if active else "transparent"
        self.setStyleSheet(
            "background: %s; border: none;"
            " border-top-right-radius: 7px; border-bottom-right-radius: 7px;" % bg
        )

    def _apply_icon(self) -> None:
        # The caret stays quiet (ink_3) until it is hovered or the menu is open.
        active = self._hover or self._open
        color = self._tokens["accent"] if active else self._tokens["ink_3"]
        name = "chevron-up" if self._open else "chevron-down"
        self.setIcon(line_icon(name, color, 12, weight=2.2))
        self.setIconSize(QSize(12, 12))


class AiModeSwitch(QWidget):
    """``[✦ AI 识别  混合 | ⌄]`` — click runs, caret opens the mode menu."""

    runRequested = Signal()
    modeChanged = Signal(str)
    tagsRequested = Signal()
    settingsRequested = Signal()

    def __init__(self, tr, tokens: dict[str, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tr = tr
        self._tokens = tokens
        self._mode = "local"
        self._busy = False
        self._hover = False
        self._menu_open = False
        self._popover: ModePopover | None = None
        self._pulse: QPropertyAnimation | None = None
        self._suppress_open = False
        self._suppress_timer = QTimer(self)
        self._suppress_timer.setSingleShot(True)
        self._suppress_timer.setInterval(220)
        self._suppress_timer.timeout.connect(self._clear_suppress)

        self.setObjectName("AiSwitch")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(34)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        self.main = _AiMain(tokens, tr, self)
        self.separator = QFrame(self)
        self.separator.setObjectName("AiSeparator")
        self.separator.setFixedWidth(1)
        self.separator.setFixedHeight(32)
        self.separator.setStyleSheet(
            f"background: {self._separator_color()}; border: none;"
        )
        self.caret = _AiCaret(tokens, self)
        layout.addWidget(self.main)
        layout.addWidget(self.separator)
        layout.addWidget(self.caret)

        self.main.clicked.connect(self.runRequested)
        self.caret.clicked.connect(self._toggle_popover)
        self.set_mode("local")
        self._sync_shell()
        self._update_icon()

    # -- state -----------------------------------------------------------

    def _separator_color(self) -> str:
        return self._tokens["line"]

    def enterEvent(self, event) -> None:
        self._hover = True
        self._sync_shell()
        self._update_icon()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self._sync_shell()
        self._update_icon()
        super().leaveEvent(event)

    def _sync_shell(self) -> None:
        """Quiet outline shell: white at rest, accent hairline as the pointer arrives."""
        t = self._tokens
        if self._menu_open:
            border = t["accent"]
        elif self._hover:
            border = _mix(t["surface"], t["accent"], 0.45)
        else:
            border = t["line_strong"]
        self.setStyleSheet(
            "QWidget#AiSwitch { background: %s; border: 1px solid %s; border-radius: 8px; }\n"
            "QAbstractButton#AiMain { background: transparent; border: none; }\n"
            "QAbstractButton#AiMain:hover { background: transparent; }\n"
            % (t["surface"], border)
        )

    def _update_icon(self) -> None:
        if self._busy:
            self.main.set_icon("stop", self._tokens["accent"])
        else:
            color = self._tokens["accent_strong"] if self._hover else self._tokens["accent"]
            self.main.set_icon("sparkle", color)

    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> None:
        if mode not in MODES:
            mode = "local"
        self._mode = mode
        self.main.chip.setText(mode_text(self._tr, mode))
        if self._popover is not None:
            self._popover.set_mode(mode)

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.main.text_label.setText(
            self._tr("toolbar.ai_stop") if busy else self._tr("toolbar.ai")
        )
        self._update_icon()
        self.main.chip.setVisible(not busy)
        self.caret.setEnabled(not busy)
        self.caret.setVisible(not busy)
        self.separator.setVisible(not busy)
        self._sync_shell()
        self._set_pulsing(busy)
        if busy and self._popover is not None:
            self._popover.close()

    def _set_pulsing(self, on: bool) -> None:
        """Breathe the busy icon so "working" reads without a spinner."""
        if self._pulse is not None:
            self._pulse.stop()
            self._pulse = None
        existing = self.main.icon_label.graphicsEffect()
        if not on or not animations_enabled():
            if isinstance(existing, QGraphicsOpacityEffect):
                existing.setOpacity(1.0)
            return
        effect = existing
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(self.main.icon_label)
            self.main.icon_label.setGraphicsEffect(effect)
        effect.setOpacity(1.0)
        anim = QPropertyAnimation(effect, b"opacity", self.main.icon_label)
        anim.setDuration(1200)
        anim.setStartValue(1.0)
        anim.setKeyValueAt(0.5, 0.55)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        anim.setLoopCount(-1)
        anim.start()
        self._pulse = anim

    def set_tokens(self, tokens: dict[str, str]) -> None:
        self._tokens = tokens
        self.main.apply_tokens(tokens)
        self.caret.apply_tokens(tokens)
        self.separator.setStyleSheet(
            f"background: {self._separator_color()}; border: none;"
        )
        self._sync_shell()
        self._update_icon()
        if self._popover is not None:
            self._popover.set_tokens(tokens)

    def retranslate(self, tr) -> None:
        self._tr = tr
        self.main.text_label.setText(tr("toolbar.ai_stop") if self._busy else tr("toolbar.ai"))
        self.set_mode(self._mode)
        if self._popover is not None:
            self._popover.retranslate(tr)

    def set_tags_count(self, count: int) -> None:
        if self._popover is not None:
            self._popover.set_tags_count(count)

    # -- popover ---------------------------------------------------------

    def _toggle_popover(self) -> None:
        if self._suppress_open:
            # Qt replays the closing click into the caret; treat it as part
            # of the same gesture so a second click only retracts.
            self._suppress_open = False
            return
        if self._popover is not None and self._popover.isVisible():
            self._popover.close()
            return
        pop = ModePopover(self._tr, self._tokens, self._tags_count)
        pop.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        pop.modePicked.connect(self._on_mode_picked)
        pop.tagsRequested.connect(self._on_tags)
        pop.settingsRequested.connect(self._on_settings)
        pop.closed.connect(self._on_popover_closed)
        pop.destroyed.connect(lambda _obj=None: self._forget_popover(pop))
        self._popover = pop
        pop.set_mode(self._mode)
        pop.adjustSize()
        pos = self.mapToGlobal(QPoint(self.width() - pop.width(), self.height() + 6))
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            x = max(avail.left() + 8, min(pos.x(), avail.right() - pop.width() - 8))
            y = pos.y()
            if y + pop.height() > avail.bottom() - 8:
                y = self.mapToGlobal(QPoint(0, 0)).y() - pop.height() - 6
            pos = QPoint(x, y)
        self._menu_open = True
        self.caret.set_open(True)
        self._sync_shell()
        pop.show()
        rise_popup(pop, pos)

    def _on_popover_closed(self) -> None:
        self._suppress_open = True
        self._suppress_timer.start()
        self._menu_open = False
        self.caret.set_open(False)
        self._sync_shell()

    def _clear_suppress(self) -> None:
        self._suppress_open = False

    def _forget_popover(self, pop) -> None:
        if self._popover is pop:
            self._popover = None

    def _on_mode_picked(self, mode: str) -> None:
        self.set_mode(mode)
        self.modeChanged.emit(mode)
        if self._popover is not None:
            # Hybrid without labels needs its warning read before the menu goes
            # away; every other pick can dismiss immediately like a menu.
            if mode == "hybrid" and self._tags_count == 0:
                self._popover.set_mode(mode)
            else:
                self._popover.close()

    def _on_tags(self) -> None:
        self.tagsRequested.emit()

    def _on_settings(self) -> None:
        self.settingsRequested.emit()

    @property
    def _tags_count(self) -> int:
        return getattr(self, "_custom_count", 0)

    def set_custom_count(self, count: int) -> None:
        self._custom_count = count
        if self._popover is not None:
            self._popover.set_tags_count(count)


_STRIP_CELLS = 8
_STRIP_UPLOADED = {"local": 0, "hybrid": 3, "cloud": 8}


class _FrameStrip(QWidget):
    """Eight schematic frame cells: filled = uploaded, outlined = stays local."""

    def __init__(self, tokens: dict[str, str], uploaded: int,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._uploaded = max(0, min(_STRIP_CELLS, uploaded))
        self._active = True
        self.setFixedHeight(7)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def sizeHint(self) -> QSize:
        return QSize(120, 7)

    def minimumSizeHint(self) -> QSize:
        return QSize(48, 7)

    def set_active(self, active: bool) -> None:
        if self._active != active:
            self._active = active
            self.update()

    def set_tokens(self, tokens: dict[str, str]) -> None:
        self._tokens = tokens
        self.update()

    def paintEvent(self, _event) -> None:
        width = self.width()
        if width <= 0:
            return
        gap = 3.0
        cell = (width - gap * (_STRIP_CELLS - 1)) / _STRIP_CELLS
        if cell <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for index in range(_STRIP_CELLS):
            rect = QRectF(index * (cell + gap), 0.5, cell, 6.0)
            if index < self._uploaded:
                color = (
                    self._tokens["accent"] if self._active
                    else _mix(self._tokens["surface"], self._tokens["accent"], 0.55)
                )
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(parse_color(color))
            else:
                painter.setPen(
                    QPen(parse_color(self._tokens["line_strong"]), 1)
                )
                painter.setBrush(parse_color(self._tokens["sunken"]))
            painter.drawRoundedRect(rect, 2, 2)
        painter.end()


class _PopoverModeCard(QAbstractButton):
    """One upload-scope card: name, scope word, frame strip and one-line brief."""

    def __init__(self, mode: str, tr, tokens: dict[str, str],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mode = mode
        self._tr = tr
        self._tokens = tokens
        self._hover = False
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 9, 11, 10)
        layout.setSpacing(0)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)
        self.title = _transparent(QLabel(mode_text(tr, mode)))
        top.addWidget(self.title)
        self.badge: QLabel | None = None
        if mode == "hybrid":
            self.badge = _transparent(QLabel(tr("mode.recommended")))
            top.addWidget(self.badge)
        top.addStretch(1)
        self.scope = _transparent(QLabel(tr(f"mode.scope_{mode}")))
        top.addWidget(self.scope)
        layout.addLayout(top)

        layout.addSpacing(7)
        self.strip = _FrameStrip(tokens, _STRIP_UPLOADED.get(mode, 0), self)
        layout.addWidget(self.strip)
        layout.addSpacing(6)
        self.desc = _transparent(QLabel(tr(f"mode.{mode}.popover")))
        self.desc.setWordWrap(True)
        layout.addWidget(self.desc)

        self._apply_styles()
        self._sync()

    def mode(self) -> str:
        return self._mode

    def _apply_styles(self) -> None:
        t = self._tokens
        self.title.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {t['ink']}; "
            "background: transparent;"
        )
        self.desc.setStyleSheet(
            f"font-size: 11px; color: {t['ink_2']}; background: transparent;"
        )
        if self.badge is not None:
            self.badge.setStyleSheet(
                "font-size: 9px; font-weight: 600; color: %s; background: %s; "
                "border: 1px solid %s; border-radius: 8px; padding: 0 5px;"
                % (t["accent"], t["accent_soft"],
                   _mix(t["surface"], t["accent"], 0.26))
            )
            self.badge.setFixedHeight(16)
        self._sync()

    def retranslate(self, tr) -> None:
        self._tr = tr
        self.title.setText(mode_text(tr, self._mode))
        self.desc.setText(tr(f"mode.{self._mode}.popover"))
        self.scope.setText(tr(f"mode.scope_{self._mode}"))
        if self.badge is not None:
            self.badge.setText(tr("mode.recommended"))

    def set_tokens(self, tokens: dict[str, str]) -> None:
        self._tokens = tokens
        self.strip.set_tokens(tokens)
        self._apply_styles()
        self.update()

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def _sync(self) -> None:
        checked = self.isChecked()
        color = self._tokens["accent"] if checked else self._tokens["ink_3"]
        self.scope.setStyleSheet(
            f"font-size: 10px; font-weight: 600; color: {color}; "
            "background: transparent;"
        )
        self.strip.set_active(checked)
        self.update()

    def checkStateSet(self) -> None:  # noqa: N802
        self._sync()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self.isChecked():
            painter.setPen(QPen(parse_color(self._tokens["accent"]), 1))
            painter.setBrush(parse_color(self._tokens["accent_soft"]))
        elif self._hover:
            painter.setPen(QPen(parse_color(self._tokens["line_strong"]), 1))
            painter.setBrush(parse_color(self._tokens["hover_strong"]))
        else:
            painter.setPen(QPen(parse_color(self._tokens["line"]), 1))
            painter.setBrush(parse_color(self._tokens["surface"]))
        painter.drawRoundedRect(rect, 9, 9)
        painter.end()


class _PopLink(QAbstractButton):
    def __init__(self, icon: str, text: str, tokens: dict[str, str],
                 with_chevron: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._icon_name = icon
        self._with_chevron = with_chevron
        self._hover = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(30)

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 0, 6, 0)
        row.setSpacing(7)
        self._icon = _transparent(QLabel())
        self._icon.setFixedSize(15, 15)
        self._icon.setPixmap(line_icon(icon, tokens["ink_3"], 15).pixmap(15, 15))
        row.addWidget(self._icon)
        self._text = _transparent(QLabel(text))
        row.addWidget(self._text)
        row.addStretch(1)
        self.count = _transparent(QLabel(""))
        row.addWidget(self.count)
        self.chev = _transparent(QLabel())
        self.chev.setFixedSize(14, 14)
        if with_chevron:
            self.chev.setPixmap(
                line_icon("chevron-right", tokens["ink_3"], 14).pixmap(14, 14)
            )
            row.addWidget(self.chev)
        self._apply_styles()

    def _apply_styles(self) -> None:
        t = self._tokens
        self._text.setStyleSheet(
            f"background: transparent; color: {t['ink_2']}; font-size: 11px;"
        )
        self.count.setStyleSheet(
            f"background: transparent; color: {t['ink_3']}; font-size: 10px;"
        )

    def set_text(self, text: str) -> None:
        self._text.setText(text)

    def set_tokens(self, tokens: dict[str, str]) -> None:
        self._tokens = tokens
        self._icon.setPixmap(
            line_icon(self._icon_name, tokens["ink_3"], 15).pixmap(15, 15)
        )
        if self._with_chevron:
            self.chev.setPixmap(
                line_icon("chevron-right", tokens["ink_3"], 14).pixmap(14, 14)
            )
        self._apply_styles()
        self.update()

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self._hover:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(parse_color(self._tokens["hover_strong"]))
            painter.drawRoundedRect(QRectF(self.rect()), 6, 6)
        painter.end()


class ModePopover(QFrame):
    """360px upload-scope menu: three frame cards, then the two secondary links."""

    modePicked = Signal(str)
    tagsRequested = Signal()
    settingsRequested = Signal()
    closed = Signal()

    def __init__(self, tr, tokens: dict[str, str], tags_count: int = 0,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self._tr = tr
        self._tokens = tokens
        self.setObjectName("ModePopover")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # Clicking the caret again must only close the menu; without this the
        # press is replayed into the caret and the popover pops straight back.
        self.setAttribute(Qt.WidgetAttribute.WA_NoMouseReplay, True)
        self.setFixedWidth(360)
        self._apply_shell()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(0)

        head = QWidget()
        head_layout = QHBoxLayout(head)
        head_layout.setContentsMargins(8, 8, 10, 10)
        head_layout.setSpacing(8)
        self._head_title = QLabel(tr("mode.popover_scope_title"))
        head_layout.addWidget(self._head_title)
        head_layout.addStretch(1)
        self._legend_local = QLabel()
        self._legend_local.setFixedSize(9, 9)
        head_layout.addWidget(self._legend_local)
        self._legend_local_text = QLabel(tr("mode.popover_legend_local"))
        head_layout.addWidget(self._legend_local_text)
        self._legend_cloud = QLabel()
        self._legend_cloud.setFixedSize(9, 9)
        head_layout.addWidget(self._legend_cloud)
        self._legend_cloud_text = QLabel(tr("mode.popover_legend_cloud"))
        head_layout.addWidget(self._legend_cloud_text)
        layout.addWidget(head)

        self._cards_box = QWidget()
        cards_layout = QVBoxLayout(self._cards_box)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setSpacing(6)
        self.cards: dict[str, _PopoverModeCard] = {}
        for mode in MODES:
            card = _PopoverModeCard(mode, tr, tokens, self._cards_box)
            card.clicked.connect(lambda *_args, m=mode: self.modePicked.emit(m))
            self.cards[mode] = card
            cards_layout.addWidget(card)
        layout.addWidget(self._cards_box)

        self.warning = QLabel(tr("mode.popover_need_labels"))
        self.warning.setWordWrap(True)
        self.warning.setVisible(False)
        layout.addWidget(self.warning)

        self._rule = QFrame()
        self._rule.setFixedHeight(1)
        layout.addSpacing(8)
        layout.addWidget(self._rule)

        util = QWidget()
        util_layout = QHBoxLayout(util)
        util_layout.setContentsMargins(4, 4, 4, 2)
        util_layout.setSpacing(2)
        self.tags_link = _PopLink(
            "tag", tr("mode.my_tags"), tokens, with_chevron=True, parent=self
        )
        self.tags_link.clicked.connect(self._pick_tags)
        util_layout.addWidget(self.tags_link, 1)
        self.settings_link = _PopLink(
            "settings", tr("mode.settings"), tokens, with_chevron=True, parent=self
        )
        self.settings_link.clicked.connect(self._pick_settings)
        util_layout.addWidget(self.settings_link, 1)
        layout.addWidget(util)

        self._tags_count = tags_count
        self._mode = "local"
        self._apply_tokens()
        self._set_tags_count(tags_count)

    def _apply_shell(self) -> None:
        self.setStyleSheet(
            "QFrame#ModePopover { background: %s; border: 1px solid %s; "
            "border-radius: 10px; }"
            % (self._tokens["surface"], self._tokens["line_strong"])
        )

    def _apply_tokens(self) -> None:
        t = self._tokens
        self._apply_shell()
        self._head_title.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {t['ink']}; "
            "background: transparent;"
        )
        for label in (
            self._legend_local_text, self._legend_cloud_text,
        ):
            label.setStyleSheet(
                f"font-size: 10px; color: {t['ink_3']}; background: transparent;"
            )
        self._legend_local.setStyleSheet(
            f"background: {t['sunken']}; border: 1px solid {t['line_strong']}; "
            "border-radius: 2px;"
        )
        self._legend_cloud.setStyleSheet(
            f"background: {t['accent']}; border: none; border-radius: 2px;"
        )
        self.warning.setStyleSheet(
            f"padding: 8px 14px 0 14px; color: {t['red']}; font-size: 11px; "
            "background: transparent;"
        )
        self._rule.setStyleSheet(f"background: {t['line']}; border: none;")
        for card in self.cards.values():
            card.set_tokens(t)
        self.tags_link.set_tokens(t)
        self.settings_link.set_tokens(t)

    def _set_tags_count(self, count: int) -> None:
        self._tags_count = count
        self.tags_link.count.setText(self._tr("mode.tags_count", n=count, max=10))
        self._sync_warning()

    def _sync_warning(self) -> None:
        show = self._mode == "hybrid" and self._tags_count == 0
        self.warning.setVisible(show)
        if self.isVisible():
            layout = self.layout()
            if layout is not None:
                layout.activate()
            self.adjustSize()

    def hideEvent(self, event) -> None:
        # Fires for a picked row, a click outside and Esc alike: the caret
        # only points up while the menu is actually on screen.
        super().hideEvent(event)
        self.closed.emit()

    def set_tags_count(self, count: int) -> None:
        self._set_tags_count(count)

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        card = self.cards.get(mode)
        if card is not None:
            card.setChecked(True)
        self._sync_warning()

    def set_tokens(self, tokens: dict[str, str]) -> None:
        self._tokens = tokens
        self._apply_tokens()

    def retranslate(self, tr) -> None:
        self._tr = tr
        self._head_title.setText(tr("mode.popover_scope_title"))
        self._legend_local_text.setText(tr("mode.popover_legend_local"))
        self._legend_cloud_text.setText(tr("mode.popover_legend_cloud"))
        self.warning.setText(tr("mode.popover_need_labels"))
        for card in self.cards.values():
            card.retranslate(tr)
        self.tags_link.set_text(tr("mode.my_tags"))
        self.settings_link.set_text(tr("mode.settings"))
        self._sync_warning()

    def _pick_tags(self) -> None:
        self.close()
        self.tagsRequested.emit()

    def _pick_settings(self) -> None:
        self.close()
        self.settingsRequested.emit()


class _ChipFlow(QWidget):
    """Flow-layout holder with an honest height sizeHint.

    Qt's default QWidget size hint for a height-for-width layout can end up as
    the sum of the chip heights, which made the target row reserve a tall blank
    column. Ask the flow for its height at the width it actually has.
    """

    def __init__(self, fallback_width: int = 384) -> None:
        super().__init__()
        self.flow = FlowLayout(self, h_spacing=5, v_spacing=5)
        self._fallback_width = max(1, fallback_width)

    def set_fallback_width(self, width: int) -> None:
        self._fallback_width = max(1, width)

    def _measure_width(self) -> int:
        return self.width() if self.width() > 1 else self._fallback_width

    def sizeHint(self) -> QSize:
        return QSize(
            self.flow.minimumSize().width(),
            self.flow.heightForWidth(self._measure_width()),
        )

    def minimumSizeHint(self) -> QSize:
        return QSize(
            self.flow.minimumSize().width(),
            self.flow.minimumSize().height(),
        )


class _LayoutValue(QWidget):
    """A value column whose size hint is the layout's, not Qt's total hint."""

    def sizeHint(self) -> QSize:
        layout = self.layout()
        return layout.sizeHint() if layout is not None else super().sizeHint()

    def minimumSizeHint(self) -> QSize:
        layout = self.layout()
        if layout is not None:
            return layout.minimumSize()
        return super().minimumSizeHint()


class UploadConfirmDialog(AppDialog):
    """520px shot-log manifest shown before hybrid/cloud uploads.

    ``labels`` are the enabled built-in labels; ``custom_labels`` is the
    editable "My labels" set, rendered first and persisted through
    ``on_labels_saved``. Hybrid can never continue with that set empty.
    """

    def __init__(self, videos: int, frames: int, mode: str, base_url: str,
                 model: str, labels: list[str], tr, parent=None,
                 tokens: dict[str, str] | None = None,
                 custom_labels: list[str] | None = None,
                 on_labels_saved: Callable[[list[str]], None] | None = None,
                 frame_counts: list[int] | None = None) -> None:
        super().__init__(tokens, parent)
        self._tr = tr
        tokens = tokens or LIGHT
        self._tokens = tokens
        self._mode = mode
        self._frame_counts = (
            [max(1, int(count)) for count in frame_counts]
            if frame_counts else []
        )
        # ``labels`` are the enabled built-ins; custom labels are kept apart so
        # the editor can rewrite them without touching the built-in palette.
        self._builtin_labels = list(labels)
        self._custom_labels = list(custom_labels or [])
        self._on_labels_saved = on_labels_saved
        self._require_custom = mode == "hybrid"
        self._shown_labels: list[str] = []
        self._add_chip: QPushButton | None = None
        # Chips created a moment ago have not been polished yet, so their
        # sizeHint (and therefore FlowLayout.heightForWidth) is still stale.
        # Fit after the event loop has laid the new row out.
        self._fit_timer = QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.setInterval(0)
        self._fit_timer.timeout.connect(self._fit_to_content)
        self.setWindowTitle(tr("confirm.title"))
        self.resize(520, 430)
        self.setMinimumWidth(520)

        # The 76px rail is the Chinese measure; English labels ("Leaves this
        # machine") need a wider column, so measure the real strings.
        label_font = QFont(self.font())
        label_font.setPixelSize(11)
        label_font.setWeight(QFont.Weight.DemiBold)
        metrics = QFontMetrics(label_font)
        self._label_width = max(
            76,
            max(
                metrics.horizontalAdvance(tr(key))
                for key in (
                    "confirm.manifest_leave",
                    "confirm.manifest_stay",
                    "confirm.manifest_target",
                )
            ) + 4,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(0)

        # The native caption already says "开始识别"; a repeated in-body title
        # would just double it. Use a small section label + the mode chip.
        head = QWidget()
        self._head = head
        head_layout = QVBoxLayout(head)
        head_layout.setContentsMargins(0, 0, 0, 0)
        head_layout.setSpacing(0)

        eyebrow_row = QHBoxLayout()
        eyebrow_row.setSpacing(10)
        eyebrow = QLabel(tr("confirm.eyebrow"))
        eyebrow.setStyleSheet(
            f"font-size: 11px; font-weight: 600; color: {tokens['ink_3']}; "
            "background: transparent;"
        )
        eyebrow_row.addWidget(eyebrow, 1)
        self._mode_chip = QLabel(mode_text(tr, mode))
        self._mode_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._mode_chip.setFixedHeight(20)
        self._mode_chip.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        cloud = mode == "cloud"
        self._mode_chip.setStyleSheet(
            "font-size: 11px; font-weight: 600; padding: 0 8px; "
            "border-radius: 10px; color: %s; background: %s; border: 1px solid %s;"
            % (
                tokens["accent"] if cloud else tokens["ink_2"],
                tokens["accent_soft"] if cloud else tokens["surface"],
                _mix(tokens["surface"], tokens["accent"], 0.34)
                if cloud else tokens["line_strong"],
            )
        )
        eyebrow_row.addWidget(
            self._mode_chip, 0, Qt.AlignmentFlag.AlignVCenter
        )
        head_layout.addLayout(eyebrow_row)
        head_layout.addSpacing(12)

        self._lead = QLabel()
        self._lead.setTextFormat(Qt.TextFormat.RichText)
        self._lead.setWordWrap(True)
        self._lead.setStyleSheet(
            f"font-size: 19px; font-weight: 600; color: {tokens['ink']}; "
            "background: transparent;"
        )
        lead_key = (
            "confirm.lead_hybrid" if mode == "hybrid" else "confirm.lead_cloud"
        )
        highlighted = f'<span style="color:{tokens["accent"]};">{frames}</span>'
        self._lead.setText(tr(lead_key, frames=highlighted))
        head_layout.addWidget(self._lead)
        head_layout.addSpacing(3)

        per_video = max(1, frames // videos) if videos > 0 else frames
        if self._frame_counts and len(set(self._frame_counts)) > 1:
            low, high = min(self._frame_counts), max(self._frame_counts)
            scope_text = tr(
                "confirm.scope_range", videos=videos, low=low, high=high
            )
        else:
            if self._frame_counts:
                per_video = self._frame_counts[0]
            scope_key = "confirm.scope_one" if videos == 1 else "confirm.scope"
            scope_text = tr(scope_key, videos=videos, per_video=per_video)
        self._scope = QLabel(scope_text)
        self._scope.setStyleSheet(
            f"font-size: 12px; color: {tokens['ink_3']}; background: transparent;"
        )
        head_layout.addWidget(self._scope)
        layout.addWidget(head)
        layout.addSpacing(16)

        manifest = QWidget()
        self._manifest = manifest
        manifest_layout = QVBoxLayout(manifest)
        manifest_layout.setContentsMargins(0, 0, 0, 0)
        manifest_layout.setSpacing(0)
        manifest_layout.addWidget(self._hairline(tokens))

        domain = urlparse(base_url).hostname or base_url or "—"
        meta = f"{domain} · {model or tr('settings.model_none')}"
        leave_key = (
            "confirm.leave_hybrid" if mode == "hybrid" else "confirm.leave_cloud"
        )
        stay_key = (
            "confirm.stay_hybrid" if mode == "hybrid" else "confirm.stay_cloud"
        )
        leave_row = self._manifest_row(
            tr("confirm.manifest_leave"), tr(leave_key, frames=frames), meta
        )
        manifest_layout.addWidget(leave_row)
        stay_row = self._manifest_row(
            tr("confirm.manifest_stay"), tr(stay_key)
        )
        manifest_layout.addWidget(stay_row)
        self._manifest_rows = [leave_row, stay_row]

        target_row = QWidget()
        self._target_row = target_row
        target_layout = QHBoxLayout(target_row)
        target_layout.setContentsMargins(0, 10, 0, 10)
        target_layout.setSpacing(12)
        target_label = QLabel(tr("confirm.manifest_target"))
        target_label.setFixedWidth(self._label_width)
        target_label.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        target_label.setContentsMargins(0, 2, 0, 0)
        target_label.setStyleSheet(
            f"font-size: 11px; font-weight: 600; color: {tokens['ink_3']}; "
            "background: transparent;"
        )
        target_layout.addWidget(target_label)

        target_value = _LayoutValue()
        self._target_value = target_value
        target_value_layout = QVBoxLayout(target_value)
        target_value_layout.setContentsMargins(0, 0, 0, 0)
        target_value_layout.setSpacing(8)
        self._chip_holder = _ChipFlow(
            max(1, 520 - 48 - self._label_width - 12)
        )
        self._flow = self._chip_holder.flow
        target_value_layout.addWidget(self._chip_holder)

        self._empty_add = QPushButton(tr("confirm.add_custom_empty"))
        self._empty_add.setObjectName("AddLabelRow")
        self._empty_add.setAutoDefault(False)
        self._empty_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self._empty_add.setFixedHeight(30)
        self._empty_add.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._empty_add.setToolTip(tr("confirm.edit_custom_tip"))
        self._empty_add.setStyleSheet(
            "QPushButton#AddLabelRow { font-size: 11px; color: %s; "
            "background: transparent; border: 1px dashed %s; border-radius: 6px; "
            "min-width: 0px; min-height: 30px; max-height: 30px; "
            "padding: 0 10px; text-align: left; }"
            "QPushButton#AddLabelRow:hover { color: %s; border-color: %s; "
            "background: %s; }"
            % (tokens["ink_3"], tokens["line_strong"], tokens["accent"],
               tokens["accent"], tokens["accent_soft"])
        )
        # The stylesheet's min-height: 0 wins over an earlier setFixedHeight;
        # apply the size constraint after the style so the row keeps 30px.
        self._empty_add.setFixedHeight(30)
        self._empty_add.setMinimumHeight(30)
        self._empty_add.setMaximumHeight(30)
        self._empty_add.clicked.connect(self._edit_labels)
        target_value_layout.addWidget(self._empty_add)

        self._cloud_empty_note = QLabel(tr("confirm.cloud_empty_note"))
        self._cloud_empty_note.setWordWrap(True)
        self._cloud_empty_note.setStyleSheet(
            f"font-size: 11px; color: {tokens['ink_3']}; background: transparent;"
        )
        target_value_layout.addWidget(self._cloud_empty_note)

        self._need_custom = QLabel(tr("confirm.need_custom"))
        self._need_custom.setWordWrap(True)
        self._need_custom.setStyleSheet(
            f"font-size: 11px; color: {tokens['red']}; background: transparent;"
        )
        target_value_layout.addWidget(self._need_custom)
        target_layout.addWidget(target_value, 1)
        manifest_layout.addWidget(target_row)
        self._manifest_rows.append(target_row)
        manifest_layout.addWidget(self._hairline(tokens))
        layout.addWidget(manifest)
        layout.addSpacing(14)

        foot_key = "confirm.note_hybrid" if mode == "hybrid" else "confirm.note"
        self._foot_note = QLabel(tr(foot_key))
        self._foot_note.setWordWrap(True)
        self._foot_note.setStyleSheet(
            f"font-size: 11px; color: {tokens['ink_3']}; background: transparent;"
        )
        layout.addWidget(self._foot_note)
        layout.addSpacing(14)

        rule = QFrame()
        self._rule = rule
        rule.setObjectName("DialogRule")
        rule.setFixedHeight(1)
        layout.addWidget(rule)
        layout.addSpacing(12)
        footer = QHBoxLayout()
        footer.setSpacing(10)
        footer.addStretch(1)
        self._cancel = dialog_button(tr("dialog.cancel"))
        self._run = dialog_button(tr("confirm.run"), "primary")
        footer.addWidget(self._cancel)
        footer.addWidget(self._run)
        layout.addLayout(footer)
        self._cancel.clicked.connect(self.reject)
        self._run.clicked.connect(self.accept)
        self._rebuild_labels()

    def _hairline(self, tokens: dict[str, str]) -> QFrame:
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background: {tokens['line']}; border: none;")
        return line

    def _manifest_row(
        self, label_text: str, value_text: str, meta: str | None = None
    ) -> QWidget:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 10, 0, 10)
        row_layout.setSpacing(12)
        label = QLabel(label_text)
        label.setFixedWidth(self._label_width)
        label.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        label.setContentsMargins(0, 2, 0, 0)
        label.setStyleSheet(
            f"font-size: 11px; font-weight: 600; "
            f"color: {self._tokens['ink_3']}; background: transparent;"
        )
        row_layout.addWidget(label)

        value = _LayoutValue()
        value_layout = QVBoxLayout(value)
        value_layout.setContentsMargins(0, 0, 0, 0)
        value_layout.setSpacing(2)
        main = QLabel(value_text)
        main.setWordWrap(True)
        main.setStyleSheet(
            f"font-size: 13px; font-weight: 500; color: {self._tokens['ink']}; "
            "background: transparent;"
        )
        value_layout.addWidget(main)
        if meta:
            meta_label = QLabel(meta)
            meta_label.setWordWrap(True)
            meta_label.setStyleSheet(
                f"font-size: 11px; color: {self._tokens['ink_3']}; "
                "background: transparent;"
            )
            value_layout.addWidget(meta_label)
        row_layout.addWidget(value, 1)
        return row

    def _clear_chips(self) -> None:
        while self._flow.count():
            item = self._flow.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                # Remove now, not on the next event-loop pass: the editor is
                # modal, so a deferred delete could leave the old chips painted
                # underneath the refreshed row when the dialog repaints.
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def _rebuild_labels(self) -> None:
        """Re-render the chip row after My labels changes.

        Custom labels lead the list: the default palette enables 26 built-ins,
        so otherwise every custom label would be hidden behind "+n more" and
        adding one from this dialog would look like a no-op.
        """
        t = self._tokens
        self._clear_chips()
        all_labels = self._custom_labels + self._builtin_labels
        shown = all_labels[:8]
        self._shown_labels = list(shown)
        custom_count = len(self._custom_labels)
        for index, label in enumerate(shown):
            chip = QLabel(label)
            if index < custom_count:
                chip.setStyleSheet(
                    "font-size: 11px; color: %s; background: %s; border: 1px solid %s; "
                    "border-radius: 6px; padding: 2px 6px;"
                    % (
                        t["accent"],
                        t["accent_soft"],
                        _mix(t["surface"], t["accent"], 0.34),
                    )
                )
            else:
                chip.setStyleSheet(
                    "font-size: 11px; color: %s; background: %s; border: 1px solid %s; "
                    "border-radius: 6px; padding: 2px 6px;"
                    % (t["ink_2"], t["surface"], t["line_strong"])
                )
            self._flow.addWidget(chip)
        if len(all_labels) > len(shown):
            more = QLabel(self._tr("confirm.more", n=len(all_labels) - len(shown)))
            more.setStyleSheet(f"font-size: 11px; color: {t['ink_3']};")
            self._flow.addWidget(more)

        has_custom = bool(self._custom_labels)
        self._empty_add.setVisible(not has_custom)
        if has_custom:
            chip = QPushButton(self._tr("confirm.add_custom"))
            chip.setObjectName("AddLabelChip")
            chip.setAutoDefault(False)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setToolTip(self._tr("confirm.edit_custom_tip"))
            font = QFont(chip.font())
            font.setPixelSize(11)
            chip.setFont(font)
            chip.setFixedHeight(22)
            chip.setMinimumWidth(
                chip.fontMetrics().horizontalAdvance(chip.text()) + 22
            )
            chip.setSizePolicy(
                QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
            )
            chip.setStyleSheet(
                "QPushButton#AddLabelChip { font-size: 11px; color: %s; "
                "background: transparent; border: 1px dashed %s; border-radius: 6px; "
                "min-width: 0px; min-height: 0px; padding: 1px 7px; }"
                "QPushButton#AddLabelChip:hover { color: %s; border-color: %s; "
                "background: %s; }"
                % (t["ink_3"], t["line_strong"], t["accent"], t["accent"],
                   t["accent_soft"])
            )
            chip.clicked.connect(self._edit_labels)
            self._flow.addWidget(chip)
            self._add_chip = chip
        else:
            self._add_chip = None

        self._chip_holder.updateGeometry()
        self._flow.update()
        self._render_target_extras()
        self._sync_run_state()
        self._target_value.updateGeometry()
        self.updateGeometry()
        self._fit_timer.start()

    def _render_target_extras(self) -> None:
        """Rebuild the target value column instead of hiding items.

        Hidden widgets still contribute to a layout's sizeHint, which made the
        target row reserve space for the empty add and both notes at once. Take
        them out of the layout unless this state actually shows them.
        """
        layout = self._target_value.layout()
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.hide()
                if widget is not self._chip_holder:
                    # Keep these out of the widget tree too: a hidden child
                    # that is still parented can keep the parent's cached
                    # sizeHint at its old, taller value.
                    widget.setParent(None)
        layout.addWidget(self._chip_holder)
        self._chip_holder.show()
        if not self._custom_labels:
            layout.addWidget(self._empty_add)
            self._empty_add.show()
            if self._require_custom:
                layout.addWidget(self._need_custom)
                self._need_custom.show()
            else:
                layout.addWidget(self._cloud_empty_note)
                self._cloud_empty_note.show()
        layout.invalidate()
        layout.activate()
        for parent in (self._target_row, self._manifest):
            parent_layout = parent.layout()
            if parent_layout is not None:
                parent_layout.invalidate()
                parent_layout.activate()
            parent.updateGeometry()
        # Left/right rows have inflated preferred hints; pin them to their real
        # content so the target row (which owns the add row and notes) keeps
        # the height it needs.
        for row in self._manifest_rows[:2]:
            row.setFixedHeight(row.minimumSizeHint().height())
        self._sync_target_row_height()

    def _sync_target_row_height(self) -> None:
        value_layout = self._target_value.layout()
        if value_layout is not None:
            value_layout.invalidate()
            value_layout.activate()
            value_height = value_layout.sizeHint().height()
        else:
            value_height = 0
        self._target_row.setFixedHeight(max(16, value_height) + 20)

    def _manifest_preferred_height(self) -> int:
        """Manifest height from the rows' real preferred sizes.

        The manifest's own sizeHint is cached against a narrow hint width and
        can stay at the old, taller value after the target row changes. Sum the
        rows instead: the two text rows use their minimum (their labels are
        single-line) and the target row uses its value layout's current hint.
        """
        if len(self._manifest_rows) < 3:
            return 0
        total = 2  # top and bottom hairlines
        for row in self._manifest_rows[:2]:
            row_layout = row.layout()
            total += (
                row_layout.minimumSize().height()
                if row_layout is not None
                else row.sizeHint().height()
            )
        value_layout = self._target_value.layout()
        value_height = (
            value_layout.sizeHint().height() if value_layout is not None else 0
        )
        total += max(16, value_height) + 20
        return total

    def _fit_to_content(self) -> None:
        self._sync_chip_height()
        self._sync_target_row_height()
        layout = self.layout()
        if layout is None:
            return
        layout.invalidate()
        layout.activate()
        width = max(1, self.width())
        foot_height = self._foot_note.heightForWidth(max(1, width - 48))
        if foot_height > 0:
            # QLabel's wrapped minimum is often one line too tall; pin the
            # actual one-line height so the manifest keeps its full space.
            self._foot_note.setFixedHeight(foot_height)
        head_height = self._head.minimumSizeHint().height()
        if head_height > 0:
            # The rich-text lead inflates the head's sizeHint; its minimum is
            # the height the content actually uses at this width.
            self._head.setFixedHeight(head_height)
        margins = layout.contentsMargins()
        total = margins.top() + margins.bottom()
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item is None:
                continue
            widget = item.widget()
            if widget is self._manifest:
                total += self._manifest_preferred_height()
            elif widget is self._foot_note:
                foot_height = self._foot_note.heightForWidth(max(1, width - 48))
                total += (
                    foot_height
                    if foot_height > 0
                    else self._foot_note.sizeHint().height()
                )
            elif widget is self._head:
                total += self._head.minimumSizeHint().height()
            elif widget is self._rule:
                total += 1
            elif widget is not None:
                widget_height = widget.heightForWidth(width)
                total += (
                    widget_height
                    if widget_height > 0
                    else max(0, widget.sizeHint().height())
                )
            else:
                total += item.sizeHint().height()
        self.resize(width, total)
        layout.activate()

    def _sync_chip_height(self) -> None:
        """FlowLayout wraps, so ask it for the height at this dialog width.

        The holder's sizeHint only reports its tallest chip; without this the
        second wrapped line is clipped when My labels pushes the row over.
        """
        width = self._chip_holder.width()
        if width <= 1:
            width = max(1, self.width() - 48 - self._label_width - 12)
        self._chip_holder.set_fallback_width(width)
        self._chip_holder.setMinimumHeight(self._flow.heightForWidth(width))
        self._chip_holder.updateGeometry()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_flow") and hasattr(self, "_chip_holder"):
            self._sync_chip_height()

    def _sync_run_state(self) -> None:
        blocked = self._require_custom and not self._custom_labels
        self._run.setEnabled(not blocked)
        self._need_custom.setVisible(blocked)
        # Cloud may continue without targets; hybrid cannot. Keep the same
        # empty row but swap the red requirement for a quiet explanation.
        self._cloud_empty_note.setVisible(not blocked and not self._custom_labels)
        self._run.setToolTip(self._tr("confirm.need_custom") if blocked else "")

    def _edit_labels(self) -> None:
        dialog = MyTagsDialog(
            self._custom_labels, self._tr, self, tokens=self._tokens
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        labels = list(dialog.labels())
        self._custom_labels = labels
        if self._on_labels_saved is not None:
            self._on_labels_saved(list(labels))
        self._rebuild_labels()