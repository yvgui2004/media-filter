"""Main-window AI split button, mode popover and upload confirmation card."""

from __future__ import annotations

from urllib.parse import urlparse

from PySide6.QtCore import (
    QEasingCurve, QPoint, QPropertyAnimation, QRectF, QSize, Qt, Signal,
)
from PySide6.QtGui import QFont, QGuiApplication, QPainter
from PySide6.QtWidgets import (
    QAbstractButton, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel,
    QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from ..dialog_base import AppDialog, dialog_button, note_label
from ..icons import line_icon
from ..motion import FAST, animations_enabled, rise_popup
from ..tokens import LIGHT, parse_color
from .flow_layout import FlowLayout
from .mode_widgets import MODES, RadioDot, mode_text


def _transparent(label: QLabel) -> QLabel:
    label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    label.setStyleSheet("background: transparent;")
    return label


class _AiMain(QPushButton):
    def __init__(self, tokens: dict[str, str], tr, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._tr = tr
        self.setObjectName("AiMain")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(34)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(11, 0, 8, 0)
        layout.setSpacing(6)
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
        chip_font.setPixelSize(10)
        chip_font.setWeight(QFont.Weight.DemiBold)
        self.chip.setFont(chip_font)
        self.chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.chip)
        self.apply_tokens(tokens)

    def apply_tokens(self, tokens: dict[str, str]) -> None:
        self._tokens = tokens
        self.text_label.setStyleSheet(f"background: transparent; color: {tokens['on_accent']};")
        self.icon_label.setPixmap(line_icon("sparkle", tokens["on_accent"], 14).pixmap(14, 14))
        # The mode word is plain text in the label color: a tinted pill read
        # as pale, a tonal pill split the button into two blues, and an
        # outline read as a stray white box.
        self.chip.setStyleSheet(
            "background: transparent; color: %s; padding: 2px 2px;"
            % tokens["on_accent"]
        )

    def sizeHint(self) -> QSize:
        layout = self.layout()
        hint = layout.sizeHint() if layout is not None else super().sizeHint()
        return QSize(max(96, hint.width()), 34)


class _AiCaret(QPushButton):
    def __init__(self, tokens: dict[str, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._open = False
        self.setObjectName("AiCaret")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(25, 34)
        self.apply_tokens(tokens)

    def set_open(self, open_: bool) -> None:
        if self._open == open_:
            return
        self._open = open_
        self.apply_tokens(self._tokens)

    def apply_tokens(self, tokens: dict[str, str]) -> None:
        self._tokens = tokens
        # Heavier than the default line weight: a 1.7 stroke dissolves into
        # the accent fill at fractional DPI and reads as a pale blue glyph.
        name = "chevron-up" if self._open else "chevron-down"
        self.setIcon(
            line_icon(name, tokens["on_accent"], 13, weight=2.6)
        )
        self.setIconSize(QSize(13, 13))


class AiModeSwitch(QWidget):
    """``[✦ AI 识别 (混合) | ⌄]`` — click runs, caret opens the mode menu."""

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
        self._popover: ModePopover | None = None
        self._pulse: QPropertyAnimation | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.main = _AiMain(tokens, tr, self)
        self.separator = QFrame(self)
        self.separator.setObjectName("AiSeparator")
        self.separator.setFixedWidth(1)
        self.separator.setFixedHeight(34)
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

    # -- state -----------------------------------------------------------

    def _separator_color(self) -> str:
        color = parse_color(self._tokens["on_accent"])
        return f"rgba({color.red()}, {color.green()}, {color.blue()}, 0.22)"

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
        self.main.icon_label.setPixmap(
            line_icon("stop" if busy else "sparkle", self._tokens["on_accent"], 14)
            .pixmap(14, 14)
        )
        self.main.chip.setVisible(not busy)
        self.caret.setEnabled(not busy)
        self.separator.setVisible(not busy)
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
        self.caret.set_open(True)
        pop.show()
        rise_popup(pop, pos)

    def _on_popover_closed(self) -> None:
        self.caret.set_open(False)

    def _forget_popover(self, pop) -> None:
        if self._popover is pop:
            self._popover = None

    def _on_mode_picked(self, mode: str) -> None:
        self.set_mode(mode)
        self.modeChanged.emit(mode)
        if self._popover is not None:
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


class _PopoverModeRow(QAbstractButton):
    def __init__(self, mode: str, tr, tokens: dict[str, str],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mode = mode
        self._tokens = tokens
        self._hover = False
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(9)
        self.dot = RadioDot(tokens)
        layout.addWidget(self.dot, 0, Qt.AlignmentFlag.AlignTop)

        copy = QVBoxLayout()
        copy.setContentsMargins(0, 0, 0, 0)
        copy.setSpacing(2)
        name_row = QHBoxLayout()
        name_row.setSpacing(6)
        title = _transparent(QLabel(mode_text(tr, mode)))
        title_font = QFont(title.font())
        title_font.setPixelSize(12)
        title_font.setWeight(QFont.Weight.DemiBold)
        title.setFont(title_font)
        title.setObjectName("ModeTitle")
        title.setStyleSheet(f"background: transparent; color: {tokens['ink']};")
        name_row.addWidget(title)
        if mode == "hybrid":
            badge = _transparent(QLabel(tr("mode.recommended")))
            badge.setObjectName("ModeBadge")
            name_row.addWidget(badge)
        name_row.addStretch(1)
        copy.addLayout(name_row)

        desc = _transparent(QLabel(mode_text(tr, mode, "desc")))
        desc.setWordWrap(True)
        desc.setStyleSheet(f"background: transparent; color: {tokens['ink_2']}; font-size: 11px;")
        copy.addWidget(desc)
        foot = _transparent(QLabel(mode_text(tr, mode, "foot")))
        foot.setStyleSheet(f"background: transparent; color: {tokens['ink_3']}; font-size: 10px;")
        copy.addWidget(foot)
        layout.addLayout(copy, 1)

        self._sync()

    def mode(self) -> str:
        return self._mode

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def _sync(self) -> None:
        self.dot.set_checked(self.isChecked())
        self.update()

    def checkStateSet(self) -> None:  # noqa: N802
        self._sync()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self.isChecked():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(parse_color(self._tokens["accent_soft"]))
            painter.drawRoundedRect(QRectF(self.rect()), 7, 7)
        elif self._hover:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(parse_color(self._tokens["hover_strong"]))
            painter.drawRoundedRect(QRectF(self.rect()), 7, 7)
        painter.end()


class _PopLink(QAbstractButton):
    def __init__(self, icon: str, text: str, tokens: dict[str, str],
                 with_chevron: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._hover = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(34)

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 0, 8, 0)
        row.setSpacing(8)
        self._icon = _transparent(QLabel())
        self._icon.setFixedSize(15, 15)
        self._icon.setPixmap(line_icon(icon, tokens["ink_3"], 15).pixmap(15, 15))
        row.addWidget(self._icon)
        self._text = _transparent(QLabel(text))
        self._text.setStyleSheet(f"background: transparent; color: {tokens['ink_2']}; font-size: 11px;")
        row.addWidget(self._text)
        row.addStretch(1)
        self.count = _transparent(QLabel(""))
        self.count.setStyleSheet(f"background: transparent; color: {tokens['ink_3']}; font-size: 10px;")
        row.addWidget(self.count)
        self.chev = _transparent(QLabel())
        self.chev.setFixedSize(14, 14)
        if with_chevron:
            self.chev.setPixmap(line_icon("chevron-right", tokens["ink_3"], 14).pixmap(14, 14))
            row.addWidget(self.chev)

    def set_text(self, text: str) -> None:
        self._text.setText(text)

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
            painter.drawRoundedRect(QRectF(self.rect()), 7, 7)
        painter.end()


class ModePopover(QFrame):
    """330px menu: three modes, then "我的标签" and "识别设置"."""

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
        self.setFixedWidth(330)
        self.setStyleSheet(
            "QFrame#ModePopover { background: %s; border: 1px solid %s; "
            "border-radius: 10px; }" % (tokens["surface"], tokens["line_strong"])
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(0)

        head = QLabel(tr("mode.popover_title"))
        head.setStyleSheet(
            f"padding: 6px 8px 5px; color: {tokens['ink_3']}; font-size: 10px; font-weight: 600;"
        )
        layout.addWidget(head)

        self.rows: dict[str, _PopoverModeRow] = {}
        for mode in MODES:
            row = _PopoverModeRow(mode, tr, tokens, self)
            row.clicked.connect(lambda *_args, m=mode: self.modePicked.emit(m))
            self.rows[mode] = row
            layout.addWidget(row)

        rule = QFrame()
        rule.setFixedHeight(1)
        rule.setStyleSheet(f"background: {tokens['line']}; margin: 5px 4px;")
        layout.addWidget(rule)

        self.tags_link = _PopLink("cube", tr("mode.my_tags"), tokens, parent=self)
        self.tags_link.clicked.connect(self._pick_tags)
        layout.addWidget(self.tags_link)

        self.settings_link = _PopLink(
            "settings", tr("mode.settings"), tokens, with_chevron=True, parent=self
        )
        self.settings_link.clicked.connect(self._pick_settings)
        layout.addWidget(self.settings_link)

        self.note = QLabel(tr("mode.popover_note"))
        self.note.setWordWrap(True)
        self.note.setStyleSheet(
            f"padding: 6px 8px 4px; color: {tokens['ink_3']}; font-size: 10px;"
        )
        layout.addWidget(self.note)

        self._tags_count = tags_count
        self._set_tags_count(tags_count)

    def _set_tags_count(self, count: int) -> None:
        self._tags_count = count
        self.tags_link.count.setText(self._tr("mode.tags_count", n=count, max=10))

    def hideEvent(self, event) -> None:
        # Fires for a picked row, a click outside and Esc alike: the caret
        # only points up while the menu is actually on screen.
        super().hideEvent(event)
        self.closed.emit()

    def set_tags_count(self, count: int) -> None:
        self._set_tags_count(count)

    def set_mode(self, mode: str) -> None:
        row = self.rows.get(mode)
        if row is not None:
            row.setChecked(True)

    def set_tokens(self, tokens: dict[str, str]) -> None:
        self._tokens = tokens
        self.setStyleSheet(
            "QFrame#ModePopover { background: %s; border: 1px solid %s; "
            "border-radius: 10px; }" % (tokens["surface"], tokens["line_strong"])
        )

    def retranslate(self, tr) -> None:
        self._tr = tr
        self.tags_link.set_text(tr("mode.my_tags"))
        self.settings_link.set_text(tr("mode.settings"))
        self.note.setText(tr("mode.popover_note"))

    def _pick_tags(self) -> None:
        self.close()
        self.tagsRequested.emit()

    def _pick_settings(self) -> None:
        self.close()
        self.settingsRequested.emit()


class UploadConfirmDialog(AppDialog):
    """470px card shown before hybrid/cloud uploads."""

    def __init__(self, videos: int, frames: int, mode: str, base_url: str,
                 model: str, labels: list[str], tr, parent=None,
                 tokens: dict[str, str] | None = None) -> None:
        super().__init__(tokens, parent)
        self._tr = tr
        tokens = tokens or LIGHT
        self.setWindowTitle(tr("confirm.title"))
        self.resize(470, 430)
        self.setMinimumWidth(470)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)

        stats = QHBoxLayout()
        stats.setSpacing(8)
        for value, key in (
            (str(videos), "confirm.stat_videos"),
            (str(frames), "confirm.stat_frames"),
            (mode_text(tr, mode), "confirm.stat_mode"),
        ):
            box = QFrame()
            box.setObjectName("StatBox")
            box.setStyleSheet(
                "QFrame#StatBox { background: %s; border: 1px solid %s; border-radius: 8px; }"
                % (tokens["surface"], tokens["line"])
            )
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(12, 10, 12, 10)
            box_layout.setSpacing(2)
            number = QLabel(value)
            number.setStyleSheet(
                f"font-size: 19px; font-weight: 600; color: {tokens['ink']}; background: transparent;"
            )
            caption = QLabel(tr(key))
            caption.setStyleSheet(
                f"font-size: 10px; color: {tokens['ink_3']}; background: transparent;"
            )
            box_layout.addWidget(number)
            box_layout.addWidget(caption)
            stats.addWidget(box, 1)
        layout.addLayout(stats)

        domain = urlparse(base_url).hostname or base_url or "—"
        target = QFrame()
        target.setObjectName("TargetBox")
        target.setStyleSheet(
            "QFrame#TargetBox { background: %s; border: 1px solid %s; border-radius: 8px; }"
            % (tokens["surface"], tokens["line"])
        )
        target_row = QHBoxLayout(target)
        target_row.setContentsMargins(10, 8, 10, 8)
        target_row.setSpacing(7)
        dot = QLabel()
        dot.setFixedSize(6, 6)
        dot.setStyleSheet(f"background: {tokens['accent']}; border-radius: 3px;")
        target_row.addWidget(dot)
        target_text = QLabel(f"{domain} · {model or tr('settings.model_none')}")
        target_text.setStyleSheet(
            f"font-size: 11px; color: {tokens['ink_2']}; background: transparent;"
        )
        target_row.addWidget(target_text, 1)
        layout.addWidget(target)

        lede = note_label(mode_text(tr, mode, "target"))
        lede.setStyleSheet("")
        layout.addWidget(lede)

        for key in ("confirm.line_images", "confirm.line_scope", "confirm.line_people"):
            line = QLabel("•  " + tr(key))
            line.setWordWrap(True)
            line.setStyleSheet(f"font-size: 11px; color: {tokens['ink_2']};")
            layout.addWidget(line)

        label_head = QLabel(tr("confirm.labels_title"))
        label_head.setStyleSheet(
            f"font-size: 10px; font-weight: 600; color: {tokens['ink_3']};"
        )
        layout.addWidget(label_head)

        chip_holder = QWidget()
        flow = FlowLayout(chip_holder, h_spacing=5, v_spacing=5)
        shown = labels[:8]
        for label in shown:
            chip = QLabel(label)
            chip.setStyleSheet(
                "font-size: 10px; color: %s; background: %s; border: 1px solid %s; "
                "border-radius: 6px; padding: 2px 6px;"
                % (tokens["ink_2"], tokens["surface"], tokens["line_strong"])
            )
            flow.addWidget(chip)
        if len(labels) > len(shown):
            more = QLabel(tr("confirm.more", n=len(labels) - len(shown)))
            more.setStyleSheet(f"font-size: 10px; color: {tokens['ink_3']};")
            flow.addWidget(more)
        layout.addWidget(chip_holder)

        layout.addWidget(note_label(tr("confirm.note")))

        rule = QFrame()
        rule.setObjectName("DialogRule")
        rule.setFixedHeight(1)
        layout.addWidget(rule)
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