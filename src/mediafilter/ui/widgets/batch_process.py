"""Batch processing dialog: one entry for convert, compress and custom ffmpeg.

The layout mirrors the approved 960×760 prototype: a header with live chips,
three task cards, a scrolling form pane, a task/check rail, then either the
command preview, live progress, or the result summary.  The heavy lifting
(command building, output planning, execution) lives in ``core.batch`` and
``core.batch_exec``; this module is presentation and state.
"""

from __future__ import annotations

import html
import os
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from string import Template

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QDesktopServices, QFont, QFontMetrics, QGuiApplication, QPainter,
    QPainterPath, QPen,
)
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QGraphicsOpacityEffect, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea,
    QSizePolicy, QStackedWidget, QTextEdit, QVBoxLayout, QWidget,
)

from ..dialog_base import AppDialog, message_box, mono_font
from ..select_field import SelectField
from ..tokens import parse_color
from ...core import batch
from ...core.batch_exec import (
    BatchExecutor, BatchSummary, BuildSpec, ExecutorHooks, Job, JobResult,
)
from ...core.ffmpeg import Preset
from ...core.formats import format_duration, format_size
from ...core.models import FileRecord
from ...core.probe import find_ffmpeg

# Background probe threads must outlive a dialog that is closed mid-check.
_ACTIVE_PROBES: set["EncoderProbe"] = set()


def _css(value: str) -> str:
    """Token color as a QSS-friendly rgba() with a percentage alpha."""
    color = parse_color(value)
    alpha = round(color.alpha() / 255 * 100)
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha}%)"


_DEFAULT_TEMPLATE = (
    'ffmpeg -hwaccel auto -i "{input}" -c:v libx265 -crf 23 -preset medium '
    '-c:a aac -b:a 96k -movflags +faststart "{output}"'
)

@dataclass
class BatchSettings:
    task: str = "compress"
    encoder: str = "auto"
    encoder_preset: str = ""
    quality: str = "balanced"
    custom_quality: str = ""
    container: str = "mp4"
    audio: str = "smart"
    subtitle: str = "smart"
    output: str = "same"
    folder: str = ""
    suffix: str = "_compressed"
    conflict: str = "number"
    advanced: bool = False
    failure: str = "continue"
    fallback: bool = True
    metadata: bool = True
    preset: str = "x265_crf23"
    template: str = _DEFAULT_TEMPLATE
    target_ext: str = "original"

    @classmethod
    def from_dict(cls, data) -> "BatchSettings":
        settings = cls()
        if isinstance(data, dict):
            allowed = {item.name for item in fields(cls)}
            for key, value in data.items():
                if key in allowed:
                    setattr(settings, key, value)
        if settings.task not in batch.TASKS:
            settings.task = "compress"
        if settings.quality not in batch.QUALITY_TIERS:
            settings.quality = "balanced"
        if settings.conflict not in batch.CONFLICT_MODES:
            settings.conflict = "number"
        if settings.failure not in batch.FAILURE_MODES:
            settings.failure = "continue"
        return settings

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------
# small painted widgets
# --------------------------------------------------------------------------


def _repolish(widget: QWidget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def _set_font(label: QLabel, size: int, weight=QFont.Weight.Normal,
              spacing: float = 0.0) -> None:
    font = QFont(label.font())
    font.setPixelSize(size)
    font.setWeight(weight)
    if spacing:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    label.setFont(font)


class _ElidedLabel(QLabel):
    """Right-aligned rail value that elides instead of widening the card."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._full = text
        self.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def setText(self, text: str) -> None:  # noqa: N802 (Qt name)
        self._full = text
        self.setToolTip(text)
        self._apply()

    def text(self) -> str:
        return self._full

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply()

    def _apply(self) -> None:
        metrics = QFontMetrics(self.font())
        shown = metrics.elidedText(
            self._full, Qt.TextElideMode.ElideRight, max(0, self.width())
        )
        QLabel.setText(self, shown)


class _Dot(QLabel):
    def __init__(self, color: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(6, 6)
        self.setStyleSheet(
            f"background: {_css(color)}; border-radius: 3px; border: none;"
        )


class _HintRow(QWidget):
    """6px status dot + small explanatory line (ok / warn / bad / neutral)."""

    def __init__(self, text: str, tokens: dict[str, str], kind: str = "ok",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        dot_color = {
            "ok": tokens["green"],
            "warn": tokens["amber"],
            "bad": tokens["red"],
            "neutral": tokens["ink_3"],
        }.get(kind, tokens["green"])
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        dot = _Dot(dot_color)
        layout.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        _set_font(label, 10)
        self._label = label
        label.setStyleSheet(
            f"color: {_css(tokens['amber'] if kind == 'warn' else tokens['red'] if kind == 'bad' else tokens['ink_3'])};"
            " font-size: 10px; font-weight: 400; background: transparent; border: none;"
        )
        layout.addWidget(label, 1)

    def _line_height(self) -> int:
        metrics = QFontMetrics(self._label.font())
        return max(metrics.height(), self._label.heightForWidth(620))

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt name)
        return QSize(0, self._line_height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (Qt name)
        # A wrapping label reports the height it needs at zero width, which
        # would force needless scrolling in the form.
        return self.sizeHint()


class _CheckMark(QWidget):
    """15px square checkbox with a hand-drawn tick; themeable and accessible."""

    toggled = Signal(bool)

    def __init__(self, checked: bool, tokens: dict[str, str],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._checked = checked
        self._tokens = tokens
        self._hover = False
        self.setFixedSize(15, 15)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def isChecked(self) -> bool:  # noqa: N802 (Qt name)
        return self._checked

    def setChecked(self, checked: bool) -> None:  # noqa: N802 (Qt name)
        if checked == self._checked:
            return
        self._checked = checked
        self.update()
        self.toggled.emit(checked)

    def paintEvent(self, event) -> None:
        t = self._tokens
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self._checked:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(parse_color(t["accent"]))
            p.drawRoundedRect(rect, 4, 4)
            p.setPen(QPen(parse_color(t["on_accent"]), 1.8,
                          Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                          Qt.PenJoinStyle.RoundJoin))
            p.drawLine(QPointF(3.4, 7.8), QPointF(6.2, 10.6))
            p.drawLine(QPointF(6.2, 10.6), QPointF(11.6, 4.6))
        else:
            border = t["ink_3"] if self._hover else t["line_strong"]
            p.setPen(QPen(parse_color(border), 1))
            p.setBrush(parse_color(t["surface"]))
            p.drawRoundedRect(rect, 4, 4)
        p.end()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.setChecked(not self._checked)
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.setChecked(not self._checked)
            event.accept()
            return
        super().keyPressEvent(event)

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)


class _CheckLine(QWidget):
    def __init__(self, text: str, checked: bool, tokens: dict[str, str],
                 enabled: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.check = _CheckMark(checked, tokens)
        self.check.setEnabled(enabled)
        layout.addWidget(self.check, 0, Qt.AlignmentFlag.AlignTop)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        _set_font(label, 11)
        label.setStyleSheet(
            f"color: {_css(tokens['ink_2'])}; font-size: 11px; background: transparent; border: none;"
        )
        layout.addWidget(label, 1)
        self.setEnabled(enabled)
        if not enabled:
            self.setProperty("dim", True)


class _ClickRow(QWidget):
    """A whole-row click target (used by the advanced-settings disclosure)."""

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def mouseReleaseEvent(self, event) -> None:
        if (event.button() == Qt.MouseButton.LeftButton
                and self.rect().contains(event.position().toPoint())):
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.clicked.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class _AdvChevron(QWidget):
    """Painted 6×6 disclosure chevron: right when closed, down when open."""

    def __init__(self, open_: bool, tokens: dict[str, str],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._open = open_
        self.setFixedSize(10, 10)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(QPen(parse_color(self._tokens["ink_3"]), 1.5,
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                      Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.translate(5, 5)
        if self._open:
            p.rotate(90)
        path = QPainterPath()
        path.moveTo(1.5, -2.4)
        path.lineTo(3.9, 0.0)
        path.lineTo(1.5, 2.4)
        p.drawPath(path)
        p.end()


class _TaskIcon(QWidget):
    """32px rounded square with a stroked 18px glyph."""

    def __init__(self, kind: str, tokens: dict[str, str],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._kind = kind
        self._tokens = tokens
        self._active = False
        self.setFixedSize(32, 32)

    def set_active(self, active: bool) -> None:
        self._active = active
        self.update()

    def paintEvent(self, event) -> None:
        t = self._tokens
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(parse_color(t["accent"] if self._active else t["sunken"]))
        p.drawRoundedRect(QRectF(0, 0, 32, 32), 8, 8)

        color = t["on_accent"] if self._active else t["ink_3"]
        p.setPen(QPen(parse_color(color), 1.7, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.translate(7, 7)
        p.scale(0.75, 0.75)

        path = QPainterPath()
        if self._kind == "remux":
            path.moveTo(4, 8); path.lineTo(18, 8)
            path.moveTo(18, 8); path.lineTo(15, 5)
            path.moveTo(18, 8); path.lineTo(15, 11)
            path.moveTo(20, 16); path.lineTo(6, 16)
            path.moveTo(6, 16); path.lineTo(9, 13)
            path.moveTo(6, 16); path.lineTo(9, 19)
        elif self._kind == "compress":
            path.moveTo(8, 4); path.lineTo(8, 9); path.lineTo(3, 9)
            path.moveTo(3, 9); path.lineTo(6, 6)
            path.moveTo(3, 9); path.lineTo(6, 12)
            path.moveTo(16, 20); path.lineTo(16, 15); path.lineTo(21, 15)
            path.moveTo(21, 15); path.lineTo(18, 18)
            path.moveTo(21, 15); path.lineTo(18, 12)
        else:
            path.moveTo(5, 7); path.lineTo(10, 12); path.lineTo(5, 17)
            path.moveTo(13, 17); path.lineTo(19, 17)
        p.drawPath(path)
        p.end()


class _TaskCard(QWidget):
    clicked = Signal()

    def __init__(self, kind: str, title: str, desc: str, tokens: dict[str, str],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self.setObjectName("BatchTaskCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedHeight(84)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(13, 12, 13, 12)
        layout.setSpacing(11)
        self.icon = _TaskIcon(kind, tokens)
        layout.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignTop)

        copy = QVBoxLayout()
        copy.setContentsMargins(0, 0, 0, 0)
        copy.setSpacing(4)
        self.title = QLabel(title)
        self.title.setObjectName("BatchTaskTitle")
        _set_font(self.title, 13, QFont.Weight.DemiBold)
        self.title.setStyleSheet(
            f"color: {_css(tokens['ink'])}; background: transparent;"
        )
        self.desc = QLabel(desc)
        self.desc.setObjectName("BatchTaskDesc")
        self.desc.setWordWrap(True)
        self.desc.setContentsMargins(0, 0, 8, 0)
        self.desc.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        _set_font(self.desc, 11)
        self.desc.setStyleSheet(
            f"color: {_css(tokens['ink_3'])}; background: transparent;"
        )
        copy.addWidget(self.title)
        copy.addWidget(self.desc, 1)
        layout.addLayout(copy, 1)

        self.check = QLabel("✓", self)
        self.check.setFixedSize(16, 16)
        self.check.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _set_font(self.check, 10, QFont.Weight.Bold)
        self.check.setStyleSheet(
            f"background: {_css(tokens['accent'])}; color: {_css(tokens['on_accent'])};"
            " border-radius: 8px; border: none; font-size: 10px; font-weight: 700;"
        )
        self.check.hide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.check.move(self.width() - 11 - 16, 11)

    def set_on(self, on: bool) -> None:
        self.setProperty("on", on)
        _repolish(self)
        self.icon.set_active(on)
        self.check.setVisible(on)
        color = self._tokens["ink_3"]
        if on:
            # color-mix(accent 72%, ink-3) — the prototype's active description.
            accent = parse_color(self._tokens["accent"])
            muted = parse_color(self._tokens["ink_3"])
            color = "#{:02X}{:02X}{:02X}".format(
                round(accent.red() * 0.72 + muted.red() * 0.28),
                round(accent.green() * 0.72 + muted.green() * 0.28),
                round(accent.blue() * 0.72 + muted.blue() * 0.28),
            )
        self.desc.setStyleSheet(
            f"color: {_css(color)}; background: transparent;"
        )

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.clicked.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class _QualitySegment(QWidget):
    """34px three-way quality control with an accent ring on the picked cell."""

    changed = Signal(str)

    def __init__(self, value: str, tokens: dict[str, str],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._options = (
            ("high", "batch.quality_high"),
            ("balanced", "batch.quality_balanced"),
            ("small", "batch.quality_small"),
        )
        self._labels = {"high": "", "balanced": "", "small": ""}
        self._value = value
        self.setFixedHeight(34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_labels(self, labels: dict[str, str]) -> None:
        self._labels = labels
        self.update()

    def value(self) -> str:
        return self._value

    def set_value(self, value: str) -> None:
        if value != self._value:
            self._value = value
            self.update()

    def paintEvent(self, event) -> None:
        t = self._tokens
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(parse_color(t["line_strong"]), 1))
        p.setBrush(parse_color(t["surface"]))
        p.drawRoundedRect(rect, 8, 8)

        width = rect.width() / 3
        for index, (key, _tr_key) in enumerate(self._options):
            cell = QRectF(rect.left() + index * width, rect.top(), width, rect.height())
            if index:
                p.setPen(QPen(parse_color(t["line"]), 1))
                p.drawLine(QPointF(cell.left(), rect.top() + 1),
                           QPointF(cell.left(), rect.bottom() - 1))
            selected = key == self._value
            if selected:
                inner = cell.adjusted(1.5, 1.5, -1.5, -1.5)
                p.setPen(QPen(parse_color(t["accent"]), 1))
                p.setBrush(parse_color(t["accent_soft"]))
                p.drawRoundedRect(inner, 6.5, 6.5)
            font = QFont(self.font())
            font.setPixelSize(11)
            font.setWeight(QFont.Weight.DemiBold)
            p.setFont(font)
            p.setPen(parse_color(t["accent"] if selected else t["ink_3"]))
            p.drawText(cell, int(Qt.AlignmentFlag.AlignCenter),
                       self._labels.get(key) or key)
        p.end()

    def _index_at(self, x: float) -> int:
        return max(0, min(2, int(x / max(1, self.width() / 3))))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            key = self._options[self._index_at(event.position().x())][0]
            if key != self._value:
                self._value = key
                self.update()
                self.changed.emit(key)
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        keys = [item[0] for item in self._options]
        index = keys.index(self._value) if self._value in keys else 1
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            index = max(0, index - 1)
        elif event.key() in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            index = min(2, index + 1)
        else:
            super().keyPressEvent(event)
            return
        if keys[index] != self._value:
            self._value = keys[index]
            self.update()
            self.changed.emit(self._value)
        event.accept()


class _ProgressBar(QWidget):
    def __init__(self, height: int = 6, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._value = 0.0
        self._tokens: dict[str, str] = {}
        self.setFixedHeight(height)

    def set_tokens(self, tokens: dict[str, str]) -> None:
        self._tokens = tokens
        self.update()

    def set_value(self, value: float) -> None:
        value = max(0.0, min(100.0, float(value)))
        if abs(value - self._value) > 0.01:
            self._value = value
            self.update()

    def value(self) -> float:
        return self._value

    def paintEvent(self, event) -> None:
        t = self._tokens
        if not t:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        radius = self.height() / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(parse_color(t["sunken"]))
        p.drawRoundedRect(QRectF(self.rect()), radius, radius)
        if self._value > 0:
            width = max(self.height(), self.width() * self._value / 100.0)
            p.setBrush(parse_color(t["accent"]))
            p.drawRoundedRect(QRectF(0, 0, width, self.height()), radius, radius)
        p.end()


# --------------------------------------------------------------------------
# background workers
# --------------------------------------------------------------------------


class EncoderProbe(QThread):
    done = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._closing = False

    def stop(self) -> None:
        self._closing = True

    def run(self) -> None:
        report = batch.probe_encoders()
        if not self._closing:
            self.done.emit(report)


class BatchWorker(QThread):
    job_started = Signal(int, object)
    progressed = Signal(int, float, float, float)
    job_result = Signal(int, object)
    logged = Signal(str)
    completed = Signal(object)

    def __init__(self, executor: BatchExecutor, parent=None) -> None:
        super().__init__(parent)
        self._executor = executor

    def cancel(self) -> None:
        self._executor.cancel()

    def run(self) -> None:
        hooks = ExecutorHooks(
            on_start=lambda index, job: self.job_started.emit(index, job),
            on_progress=lambda index, overall, current, speed: self.progressed.emit(
                index, overall, current, speed if speed is not None else 0.0
            ),
            on_result=lambda index, result: self.job_result.emit(index, result),
            on_log=lambda text: self.logged.emit(text),
        )
        summary = self._executor.run(hooks)
        self.completed.emit(summary)


# --------------------------------------------------------------------------
# dialog
# --------------------------------------------------------------------------

_STYLE = Template("""
#BatchDialog { background: $canvas; }

#BatchTitle { color: $ink; font-size: 22px; font-weight: 650; }
#BatchLede { color: $ink_3; font-size: 12px; }

#BatchPill {
    height: 25px; padding: 0 10px; border-radius: 12px;
    border: 1px solid $line_strong; color: $ink_3;
    font-size: 10px; font-weight: 600;
}
#BatchPill[tone="accent"] {
    color: $accent; border-color: alpha_accent; background: $accent_soft;
}
#BatchPill[tone="warn"] {
    color: $amber; border-color: alpha_amber; background: $amber_soft;
}

#BatchTaskCard {
    background: $surface; border: 1px solid $line;
    border-radius: 11px;
}
#BatchTaskCard:hover { border-color: $line_strong; background: $surface; }
#BatchTaskCard[on="true"] { background: $accent_soft; border-color: $accent; }
#BatchTaskTitle { color: $ink; font-size: 13px; font-weight: 600; }
#BatchTaskDesc { color: $ink_3; font-size: 11px; font-weight: 400; }

#BatchFormScroll, #BatchFormScroll > QWidget > QWidget { background: transparent; border: none; }
#BatchFormCard {
    background: $surface; border: 1px solid $line; border-radius: 12px;
}
#BatchPaneTitle { color: $ink; font-size: 14px; font-weight: 650; }
#BatchPaneLede { color: $ink_3; font-size: 11px; }
#BatchFieldLabel {
    color: $ink_3; font-size: 10px; font-weight: 650;
}
#BatchHint { color: $ink_3; font-size: 10px; }
#BatchHint.warn { color: $amber; }

#BatchRailCard {
    background: $surface; border: 1px solid $line; border-radius: 12px;
}
#BatchRailTitle {
    color: $ink_3; font-size: 10px; font-weight: 700;
}
#BatchRailKey { color: $ink_3; font-size: 11px; }
#BatchRailValue { color: $ink_2; font-size: 11px; font-weight: 600; }

#BatchStreamStrip {
    background: $header; border: 1px solid $line; border-radius: 10px;
}
#BatchStreamKey { color: $ink_3; font-size: 9px; font-weight: 650; }
#BatchStreamValue { color: $ink_2; font-size: 11px; font-weight: 600; }

#BatchAdvToggle { background: transparent; border: none; }
#BatchAdvSummary { color: $ink_3; font-size: 10px; }
#BatchAdvNote { color: $ink_3; font-size: 10px; }

#BatchPreview {
    background: $surface; border: 1px solid $line; border-radius: 11px;
}
#BatchPreviewTitle { color: $ink_2; font-size: 11px; font-weight: 650; }
#BatchPreviewCount { color: $ink_3; font-size: 10px; }
#BatchPreviewNote { color: $ink_3; font-size: 9px; }
#BatchPreviewBody {
    background: $header; border: none; border-top: 1px solid $line;
    border-bottom: 1px solid $line; color: $ink_2;
    padding: 6px 12px;
    selection-background-color: $accent_soft; selection-color: $ink;
}
QPushButton#BatchLink {
    background: transparent; border: none; color: $accent;
    font-size: 10px; font-weight: 600; padding: 0; min-width: 0;
}
QPushButton#BatchLink:hover { color: $accent_strong; }
QPushButton#BatchGhostSmall {
    background: $surface; border: 1px solid $line_strong; color: $ink_2;
    border-radius: 8px; font-size: 11px; font-weight: 600;
    padding: 0 12px; min-width: 0;
}
QPushButton#BatchGhostSmall:hover { border-color: $ink_3; color: $ink; }

#BatchProgress, #BatchSummary {
    background: $surface; border: 1px solid $line; border-radius: 11px;
}
#BatchProgressTitle { color: $ink; font-size: 12px; font-weight: 650; }
#BatchProgressMeta { color: $ink_3; font-size: 10px; }
#BatchFileName { color: $ink_2; font-size: 10px; font-weight: 600; }
#BatchFileMeta { color: $ink_3; font-size: 10px; }
#BatchLog {
    background: transparent; border: none; color: $ink_3;
}

#BatchSummaryTitle { color: $ink; font-size: 13px; font-weight: 650; }
#BatchSummarySub { color: $ink_3; font-size: 11px; }
#BatchStatValue { color: $ink; font-size: 15px; font-weight: 650; }
#BatchStatLabel { color: $ink_3; font-size: 9px; }
#BatchSizeKey { color: $ink_3; font-size: 9px; font-weight: 650; }
#BatchSizeValue { color: $ink; font-size: 14px; font-weight: 650; }
#BatchSizeDelta { color: $ink_3; font-size: 10px; font-weight: 600; }
#BatchFailRow { color: $ink_3; font-size: 10px; }

#BatchFoot {
    background: $surface; border: none; border-top: 1px solid $line;
}
#BatchFootLeft { color: $ink_3; font-size: 10px; }
#BatchFoot QPushButton {
    min-width: 0; min-height: 34px; height: 34px;
    padding: 0 15px; font-size: 12px; font-weight: 600;
    border-radius: 8px;
}
QScrollBar:vertical { background: transparent; width: 6px; margin: 2px 1px; }
QScrollBar::handle:vertical { background: $scroll; border-radius: 3px; min-height: 24px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
""")


def _qss(tokens: dict[str, str]) -> str:
    values = dict(tokens)
    values["alpha_accent"] = _css(tokens["accent"])
    values["alpha_amber"] = _css(tokens["amber"])
    return _STYLE.substitute(values)


class BatchProcessDialog(AppDialog):
    """Merged batch-processing entry (fast convert / compress / custom)."""

    def __init__(
        self,
        records: list[FileRecord],
        tr,
        presets: list[Preset],
        parent: QWidget | None = None,
        tokens: dict[str, str] | None = None,
        config=None,
    ) -> None:
        super().__init__(tokens, parent)
        self._records = list(records)
        self._tr = tr
        self._presets = list(presets)
        self._config = config
        self._tokens = tokens or self._tokens
        saved = getattr(config, "batch_settings", {}) if config is not None else {}
        self._settings = BatchSettings.from_dict(saved)
        self._vendor_ids = batch.detected_vendors()

        self._availability: dict[str, batch.Availability] | None = None
        self._worker: BatchWorker | None = None
        self._probe: EncoderProbe | None = None
        self._view = "config"
        self._plans: list[batch.OutputTarget] = []
        self._jobs: list[Job] = []
        self._summary: BatchSummary | None = None
        self._started_at = 0.0
        self._fallback_count = 0
        self._current_name = ""
        self._last_output_folder: Path | None = None
        self._fields: dict[str, QWidget] = {}
        self._refreshing = False
        self._closing = False
        self._quality_label: QLabel | None = None
        self._current_index = 0
        self._bottom_hook: tuple | None = None
        self._timer: QTimer | None = None
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(160)
        self._preview_timer.timeout.connect(self._refresh_summary)

        self.setObjectName("BatchDialog")
        self.setWindowTitle(self._tr("batch.title"))
        self.setFixedSize(960, 760)
        self.setStyleSheet(_qss(self._tokens))

        self._build_ui()
        self._refresh_all(rebuild=True)
        self._set_view("config")
        self._start_probe()

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())
        root.addWidget(self._build_tasks())
        root.addWidget(self._build_body(), 1)
        root.addWidget(self._build_stack())
        root.addWidget(self._build_footer())

    def _build_header(self) -> QWidget:
        head = QWidget()
        outer = QVBoxLayout(head)
        outer.setContentsMargins(26, 18, 26, 0)
        outer.setSpacing(5)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(14)

        copy = QVBoxLayout()
        copy.setContentsMargins(0, 0, 0, 0)
        copy.setSpacing(5)
        self._title_label = QLabel(self._tr("batch.title"))
        self._title_label.setObjectName("BatchTitle")
        _set_font(self._title_label, 22, QFont.Weight.DemiBold, -0.3)
        self._lede_label = QLabel("")
        self._lede_label.setObjectName("BatchLede")
        self._lede_label.setTextFormat(Qt.TextFormat.PlainText)
        copy.addWidget(self._title_label)
        copy.addWidget(self._lede_label)
        row.addLayout(copy, 1)

        chips = QHBoxLayout()
        chips.setContentsMargins(0, 2, 0, 0)
        chips.setSpacing(7)
        self._chip_encoder = self._make_pill("accent")
        self._chip_files = self._make_pill("")
        self._chip_warn = self._make_pill("")
        chips.addWidget(self._chip_encoder)
        chips.addWidget(self._chip_files)
        chips.addWidget(self._chip_warn)
        chips.addStretch(1)
        row.addLayout(chips)
        outer.addLayout(row)
        return head

    def _make_pill(self, tone: str) -> QLabel:
        pill = QLabel("")
        pill.setObjectName("BatchPill")
        pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pill.setFixedHeight(25)
        pill.setProperty("tone", tone)
        _set_font(pill, 10, QFont.Weight.DemiBold)
        return pill

    def _build_tasks(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(26, 14, 26, 0)
        layout.setSpacing(10)
        specs = (
            ("remux", "batch.task_remux_title", "batch.task_remux_desc"),
            ("compress", "batch.task_compress_title", "batch.task_compress_desc"),
            ("custom", "batch.task_custom_title", "batch.task_custom_desc"),
        )
        self._cards: dict[str, _TaskCard] = {}
        for kind, title_key, desc_key in specs:
            card = _TaskCard(
                kind, self._tr(title_key), self._tr(desc_key), self._tokens,
            )
            card.clicked.connect(lambda k=kind: self._on_task(k))
            layout.addWidget(card, 1)
            self._cards[kind] = card
        self._task_row = row
        self._task_effect = QGraphicsOpacityEffect(row)
        self._task_effect.setOpacity(1.0)
        row.setGraphicsEffect(self._task_effect)
        return row

    def _build_body(self) -> QWidget:
        body = QWidget()
        layout = QHBoxLayout(body)
        layout.setContentsMargins(26, 14, 26, 0)
        layout.setSpacing(14)

        self._form_scroll = QScrollArea()
        self._form_scroll.setObjectName("BatchFormScroll")
        self._form_scroll.setWidgetResizable(True)
        self._form_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._form_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        card = QFrame()
        card.setObjectName("BatchFormCard")
        self._form_card = card
        self._form_effect = QGraphicsOpacityEffect(card)
        self._form_effect.setOpacity(1.0)
        card.setGraphicsEffect(self._form_effect)
        self._form_layout = QVBoxLayout(card)
        self._form_layout.setContentsMargins(15, 13, 15, 14)
        self._form_layout.setSpacing(11)
        self._form_scroll.setWidget(card)
        layout.addWidget(self._form_scroll, 1)

        rail = QWidget()
        rail.setFixedWidth(236)
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(0, 0, 0, 0)
        rail_layout.setSpacing(10)
        rail_layout.addWidget(self._build_task_rail())
        rail_layout.addWidget(self._build_check_rail())
        rail_layout.addStretch(1)
        layout.addWidget(rail)
        self._rail = rail
        return body

    def _rail_card(self, title_key: str) -> tuple[QFrame, QVBoxLayout, QLabel]:
        card = QFrame()
        card.setObjectName("BatchRailCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(13, 10, 13, 9)
        layout.setSpacing(0)
        title = QLabel(self._tr(title_key))
        title.setObjectName("BatchRailTitle")
        _set_font(title, 10, QFont.Weight.Bold, 1.0)
        layout.addWidget(title)
        layout.addSpacing(7)
        return card, layout, title

    def _build_task_rail(self) -> QFrame:
        card, layout, _title = self._rail_card("batch.rail_task")
        self._rail_values: dict[str, _ElidedLabel] = {}
        for key in ("mode", "encoder", "quality", "container", "strategy", "output"):
            line = QWidget()
            row = QHBoxLayout(line)
            row.setContentsMargins(0, 4, 0, 4)
            row.setSpacing(8)
            key_label = QLabel(self._tr(f"batch.rail_{key}"))
            key_label.setObjectName("BatchRailKey")
            value = _ElidedLabel("—")
            value.setObjectName("BatchRailValue")
            row.addWidget(key_label, 0)
            row.addWidget(value, 1)
            layout.addWidget(line)
            self._rail_values[key] = value
            if key != "output":
                divider = QFrame()
                divider.setFixedHeight(1)
                divider.setStyleSheet(
                    f"background: {_css(self._tokens['line'])}; border: none;"
                )
                layout.addWidget(divider)
        return card

    def _build_check_rail(self) -> QFrame:
        card, layout, self._rail_check_title = self._rail_card("batch.rail_check")
        self._check_box = QVBoxLayout()
        self._check_box.setContentsMargins(0, 0, 0, 0)
        self._check_box.setSpacing(0)
        layout.addLayout(self._check_box)
        return card

    def _build_stack(self) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(26, 12, 26, 0)
        layout.setSpacing(0)
        self._stack = QStackedWidget()
        self._stack.setFixedHeight(152)
        self._stack.addWidget(self._build_preview())
        self._stack.addWidget(self._build_progress())
        self._stack.addWidget(self._build_summary())
        layout.addWidget(self._stack)
        return wrapper

    def _build_preview(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("BatchPreview")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        head = QWidget()
        head.setFixedHeight(33)
        row = QHBoxLayout(head)
        row.setContentsMargins(12, 0, 12, 0)
        row.setSpacing(8)
        title = QLabel(self._tr("batch.preview_title"))
        title.setObjectName("BatchPreviewTitle")
        row.addWidget(title)
        row.addStretch(1)
        self._preview_count = QLabel("")
        self._preview_count.setObjectName("BatchPreviewCount")
        row.addWidget(self._preview_count)
        copy = QPushButton(self._tr("batch.preview_copy"))
        copy.setObjectName("BatchLink")
        copy.setCursor(Qt.CursorShape.PointingHandCursor)
        copy.clicked.connect(self._copy_commands)
        row.addWidget(copy)
        layout.addWidget(head)

        self._preview_body = QTextEdit()
        self._preview_body.setObjectName("BatchPreviewBody")
        self._preview_body.setReadOnly(True)
        self._preview_body.setFrameShape(QFrame.Shape.NoFrame)
        self._preview_body.setFont(mono_font(10))
        self._preview_body.setAcceptRichText(True)
        self._preview_body.document().setDocumentMargin(0)
        layout.addWidget(self._preview_body, 1)

        note = QLabel(self._tr("batch.preview_note"))
        note.setObjectName("BatchPreviewNote")
        note.setContentsMargins(12, 5, 12, 7)
        _set_font(note, 9)
        layout.addWidget(note)
        return frame

    def _build_progress(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("BatchProgress")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(13, 10, 13, 9)
        layout.setSpacing(6)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(9)
        title = QLabel(self._tr("batch.processing"))
        title.setObjectName("BatchProgressTitle")
        _set_font(title, 12, QFont.Weight.DemiBold)
        self._run_counter = QLabel("")
        self._run_counter.setObjectName("BatchProgressMeta")
        self._run_clock = QLabel("")
        self._run_clock.setObjectName("BatchProgressMeta")
        self._run_clock.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(title)
        top.addWidget(self._run_counter)
        top.addStretch(1)
        top.addWidget(self._run_clock)
        layout.addLayout(top)

        self._run_bar = _ProgressBar(6)
        self._run_bar.set_tokens(self._tokens)
        layout.addWidget(self._run_bar)

        file_row = QHBoxLayout()
        file_row.setContentsMargins(0, 0, 0, 0)
        file_row.setSpacing(8)
        self._run_file = _ElidedLabel("")
        self._run_file.setObjectName("BatchFileName")
        self._run_file.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._run_file.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._run_detail = QLabel("")
        self._run_detail.setObjectName("BatchFileMeta")
        self._run_detail.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        file_row.addWidget(self._run_file, 1)
        file_row.addWidget(self._run_detail, 0)
        layout.addLayout(file_row)

        self._file_bar = _ProgressBar(4)
        self._file_bar.set_tokens(self._tokens)
        layout.addWidget(self._file_bar)

        self._run_log = QTextEdit()
        self._run_log.setObjectName("BatchLog")
        self._run_log.setReadOnly(True)
        self._run_log.setFrameShape(QFrame.Shape.NoFrame)
        self._run_log.setFont(mono_font(10))
        self._run_log.setAcceptRichText(True)
        layout.addWidget(self._run_log, 1)
        return frame

    def _build_summary(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("BatchSummary")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(15, 13, 15, 13)
        layout.setSpacing(13)

        self._summary_icon = QLabel("✓")
        self._summary_icon.setFixedSize(38, 38)
        self._summary_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _set_font(self._summary_icon, 17, QFont.Weight.Bold)
        layout.addWidget(self._summary_icon, 0, Qt.AlignmentFlag.AlignVCenter)

        main = QVBoxLayout()
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(4)
        self._summary_title = QLabel("")
        self._summary_title.setObjectName("BatchSummaryTitle")
        self._summary_sub = QLabel("")
        self._summary_sub.setObjectName("BatchSummarySub")
        main.addWidget(self._summary_title)
        main.addWidget(self._summary_sub)

        stats = QHBoxLayout()
        stats.setContentsMargins(0, 5, 0, 0)
        stats.setSpacing(20)
        self._stat_values: dict[str, QLabel] = {}
        for key in ("ok", "failed", "skipped", "elapsed"):
            box = QVBoxLayout()
            box.setContentsMargins(0, 0, 0, 0)
            box.setSpacing(1)
            value = QLabel("0")
            value.setObjectName("BatchStatValue")
            value.setFont(self._stat_font(15))
            label = QLabel(self._tr(f"batch.stat_{key}"))
            label.setObjectName("BatchStatLabel")
            box.addWidget(value)
            box.addWidget(label)
            stats.addLayout(box)
            self._stat_values[key] = value
        stats.addStretch(1)
        main.addLayout(stats)

        self._fail_row = QWidget()
        fail_layout = QHBoxLayout(self._fail_row)
        fail_layout.setContentsMargins(0, 7, 0, 0)
        fail_layout.setSpacing(7)
        dot = _Dot(self._tokens["red"])
        fail_layout.addWidget(dot, 0, Qt.AlignmentFlag.AlignVCenter)
        self._fail_name = QLabel("")
        self._fail_name.setObjectName("BatchFailRow")
        _set_font(self._fail_name, 10, QFont.Weight.DemiBold)
        self._fail_text = _ElidedLabel("")
        self._fail_text.setObjectName("BatchFailRow")
        self._fail_text.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._fail_text.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        fail_layout.addWidget(self._fail_name)
        fail_layout.addWidget(self._fail_text, 1)
        self._fail_row.hide()
        main.addWidget(self._fail_row)
        layout.addLayout(main, 1)

        size_box = QVBoxLayout()
        size_box.setContentsMargins(20, 0, 0, 0)
        size_box.setSpacing(1)
        self._summary_size = QWidget()
        size_layout = QVBoxLayout(self._summary_size)
        size_layout.setContentsMargins(20, 0, 0, 0)
        size_layout.setSpacing(1)
        key = QLabel(self._tr("batch.size"))
        key.setObjectName("BatchSizeKey")
        _set_font(key, 9, QFont.Weight.DemiBold, 0.6)
        self._size_value = QLabel("")
        self._size_value.setObjectName("BatchSizeValue")
        self._size_delta = QLabel("")
        self._size_delta.setObjectName("BatchSizeDelta")
        for widget in (key, self._size_value, self._size_delta):
            widget.setAlignment(Qt.AlignmentFlag.AlignRight)
            size_layout.addWidget(widget)
        rule = QFrame()
        rule.setFixedWidth(1)
        rule.setStyleSheet(f"background: {_css(self._tokens['line'])}; border: none;")
        holder = QHBoxLayout()
        holder.setContentsMargins(0, 0, 0, 0)
        holder.setSpacing(0)
        holder.addStretch(1)
        holder.addWidget(rule)
        holder.addWidget(self._summary_size)
        layout.addLayout(holder)
        return frame

    def _stat_font(self, size: int) -> QFont:
        font = QFont(self.font())
        font.setPixelSize(size)
        font.setWeight(QFont.Weight.DemiBold)
        return font

    def _build_footer(self) -> QWidget:
        wrapper = QWidget()
        wrapper.setFixedHeight(74)
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(0)
        self._foot = QFrame()
        self._foot.setObjectName("BatchFoot")
        self._foot_layout = QHBoxLayout(self._foot)
        self._foot_layout.setContentsMargins(26, 0, 26, 0)
        self._foot_layout.setSpacing(8)
        layout.addWidget(self._foot)
        return wrapper

    # ------------------------------------------------------------------
    # form construction
    # ------------------------------------------------------------------

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("BatchFieldLabel")
        _set_font(label, 10, QFont.Weight.DemiBold, 0.6)
        return label

    def _hint(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("BatchHint")
        label.setWordWrap(True)
        _set_font(label, 10)
        return label

    def _field_block(self, label: str, control: QWidget, hint: str = "") -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        layout.addWidget(self._field_label(label))
        layout.addWidget(control)
        if hint:
            layout.addWidget(self._hint(hint))
        return box

    def _select(self, key: str, choices: list[tuple], current: str,
                min_width: int = 196) -> SelectField:
        field = SelectField()
        field.set_tokens(self._tokens)
        field.set_accessible_label(key)
        field.set_popup_min_width(min_width)
        field.blockSignals(True)
        for choice in choices:
            if len(choice) == 1:          # ("group",)
                field.addGroup(choice[0])
                continue
            value, label = choice[0], choice[1]
            disabled = choice[2] if len(choice) > 2 else False
            note = choice[3] if len(choice) > 3 else ""
            field.addItem(label, value, disabled=disabled, note=note)
        index = field.findData(current)
        if index >= 0:
            field.setCurrentIndex(index)
        field.blockSignals(False)
        field.currentIndexChanged.connect(
            lambda _i, f=field, k=key: self._on_select(k, f.currentData())
        )
        self._fields[key] = field
        return field

    def _line_edit(self, key: str, value: str, placeholder: str = "") -> QLineEdit:
        edit = QLineEdit(value)
        edit.setObjectName("FieldInput")
        edit.setFixedHeight(34)
        edit.setPlaceholderText(placeholder)
        edit.textChanged.connect(lambda text, k=key: self._on_text(k, text))
        self._fields[key] = edit
        return edit

    def _rebuild_form(self, focus: str | None = None) -> None:
        if self._view != "config":
            return
        scroll_value = self._form_scroll.verticalScrollBar().value()
        self._refreshing = True
        try:
            self._fields = {}
            self._quality_label = None
            self._clear_layout(self._form_layout)
            self._clamp_settings()

            head = QWidget()
            head_row = QHBoxLayout(head)
            head_row.setContentsMargins(0, 0, 0, 0)
            head_row.setSpacing(9)
            pane_title = QLabel(self._tr("batch.pane_title"))
            pane_title.setObjectName("BatchPaneTitle")
            _set_font(pane_title, 14, QFont.Weight.DemiBold)
            pane_lede = QLabel(self._tr("batch.pane_lede"))
            pane_lede.setObjectName("BatchPaneLede")
            head_row.addWidget(pane_title)
            head_row.addWidget(pane_lede)
            head_row.addStretch(1)
            self._form_layout.addWidget(head)

            if self._settings.task == "compress":
                self._build_compress_form()
            elif self._settings.task == "remux":
                self._build_remux_form()
            else:
                self._build_custom_form()
            self._build_advanced()
            self._form_layout.addStretch(1)
        finally:
            self._refreshing = False

        self._form_scroll.verticalScrollBar().setValue(scroll_value)
        if focus and focus in self._fields:
            widget = self._fields[focus]
            QTimer.singleShot(0, widget.setFocus)

    def _build_compress_form(self) -> None:
        choices = self._encoder_choices()
        encoder = self._select("encoder", choices, self._settings.encoder, 300)
        self._form_layout.addWidget(self._field_block(self._tr("batch.encoder"), encoder))
        note_kind, note_text = self._task_note()
        self._form_layout.addWidget(_HintRow(
            note_text, self._tokens, note_kind,
        ))

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(11)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        quality_box = QWidget()
        quality_layout = QVBoxLayout(quality_box)
        quality_layout.setContentsMargins(0, 0, 0, 0)
        quality_layout.setSpacing(5)
        label_row = QHBoxLayout()
        label_row.setContentsMargins(0, 0, 0, 0)
        label_row.setSpacing(8)
        label_row.addWidget(self._field_label(self._tr("batch.quality")))
        self._quality_label = QLabel(self._quality_text())
        _set_font(self._quality_label, 10, QFont.Weight.DemiBold)
        self._quality_label.setStyleSheet(
            f"color: {_css(self._tokens['accent'])}; background: transparent;"
        )
        label_row.addWidget(self._quality_label)
        label_row.addStretch(1)
        quality_layout.addLayout(label_row)
        segment = _QualitySegment(self._settings.quality, self._tokens)
        segment.set_labels({
            key: self._tr(f"batch.quality_{key}")
            for key in batch.QUALITY_TIERS
        })
        segment.changed.connect(self._on_quality)
        quality_layout.addWidget(segment)
        quality_layout.addWidget(self._hint(self._tr("batch.quality_hint")))
        grid.addWidget(quality_box, 0, 0)

        container = self._select(
            "container", self._container_choices(), self._settings.container, 220,
        )
        grid.addWidget(self._field_block(self._tr("batch.container"), container), 0, 1)
        self._form_layout.addLayout(grid)
        self._form_layout.addWidget(self._output_row())
        self._form_layout.addWidget(self._advanced_footer())

    def _build_remux_form(self) -> None:
        container = self._select(
            "container", self._container_choices(), self._settings.container, 220,
        )
        self._form_layout.addWidget(self._field_block(self._tr("batch.container"), container))
        kind, text = self._compat_note()
        self._form_layout.addWidget(_HintRow(text, self._tokens, kind))
        self._form_layout.addWidget(self._stream_strip())
        self._form_layout.addWidget(self._output_row())
        self._form_layout.addWidget(self._advanced_footer())

    def _build_custom_form(self) -> None:
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(11)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        preset_choices = [("__group__",) ] if False else []
        preset_choices = []
        for preset in self._presets:
            preset_choices.append((preset.key, preset.name))
        current = self._settings.preset
        if current not in {p.key for p in self._presets}:
            current = self._presets[0].key if self._presets else ""
        preset = self._select("preset", preset_choices, current, 250)
        grid.addWidget(self._field_block(self._tr("batch.preset"), preset), 0, 0)

        ext = self._select(
            "target_ext", self._ext_choices(), self._settings.target_ext, 220,
        )
        grid.addWidget(self._field_block(self._tr("batch.output_format"), ext), 0, 1)
        self._form_layout.addLayout(grid)

        template = QTextEdit()
        template.setObjectName("CodeInput")
        template.setAcceptRichText(False)
        template.setFixedHeight(82)
        template.setFont(mono_font(11))
        template.setPlainText(self._settings.template)
        template.textChanged.connect(self._on_template_changed)
        self._fields["template"] = template
        block = QWidget()
        block_layout = QVBoxLayout(block)
        block_layout.setContentsMargins(0, 0, 0, 0)
        block_layout.setSpacing(5)
        block_layout.addWidget(self._field_label(self._tr("batch.template")))
        block_layout.addWidget(template)
        block_layout.addWidget(self._hint(self._tr("batch.template_hint")))
        self._form_layout.addWidget(block)
        self._form_layout.addWidget(self._output_row())
        self._form_layout.addWidget(self._advanced_footer())

    def _output_row(self) -> QWidget:
        row = QWidget()
        grid = QGridLayout(row)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(11)
        grid.setColumnStretch(0, 108)
        grid.setColumnStretch(1, 100)
        grid.setColumnStretch(2, 100)

        output = self._select(
            "output",
            [
                ("same", self._tr("batch.output_same")),
                ("custom", self._tr("batch.output_custom")),
            ],
            self._settings.output,
            196,
        )
        grid.addWidget(self._field_block(self._tr("batch.output"), output), 0, 0)

        suffix = self._line_edit("suffix", self._settings.suffix)
        grid.addWidget(self._field_block(self._tr("batch.suffix"), suffix), 0, 1)

        conflict = self._select(
            "conflict",
            [
                ("number", self._tr("batch.conflict_number")),
                ("skip", self._tr("batch.conflict_skip")),
                ("overwrite", self._tr("batch.conflict_overwrite")),
            ],
            self._settings.conflict,
            210,
        )
        grid.addWidget(self._field_block(self._tr("batch.conflicts"), conflict), 0, 2)

        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(11)
        layout.addWidget(row)

        if self._settings.output == "custom":
            folder_row = QWidget()
            folder_layout = QHBoxLayout(folder_row)
            folder_layout.setContentsMargins(0, 0, 0, 0)
            folder_layout.setSpacing(7)
            folder = self._line_edit("folder", self._settings.folder,
                                      self._tr("batch.folder_placeholder"))
            folder_layout.addWidget(folder, 1)
            choose = QPushButton(self._tr("batch.choose"))
            choose.setObjectName("BatchGhostSmall")
            choose.setFixedHeight(34)
            choose.setCursor(Qt.CursorShape.PointingHandCursor)
            choose.clicked.connect(self._choose_folder)
            folder_layout.addWidget(choose)
            block = QWidget()
            block_layout = QVBoxLayout(block)
            block_layout.setContentsMargins(0, 0, 0, 0)
            block_layout.setSpacing(5)
            block_layout.addWidget(self._field_label(self._tr("batch.folder")))
            block_layout.addWidget(folder_row)
            block_layout.addWidget(self._hint(self._tr("batch.folder_hint")))
            layout.addWidget(block)

        if self._settings.conflict == "overwrite":
            layout.addWidget(_HintRow(
                self._tr("batch.overwrite_hint"), self._tokens, "warn",
            ))
        return box

    def _stream_strip(self) -> QWidget:
        strip = QFrame()
        strip.setObjectName("BatchStreamStrip")
        row = QHBoxLayout(strip)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        ext = self._settings.container
        if ext == batch.ORIGINAL:
            ext = "mp4"
        sub = batch.subtitle_effect(self._settings.subtitle, ext)
        sub_text = {
            "remove": self._tr("batch.stream_remove"),
            "mov_text": self._tr("batch.stream_mov_text"),
            "copy": self._tr("batch.stream_copy"),
            "webvtt": self._tr("batch.stream_webvtt"),
            "dropped": self._tr("batch.stream_dropped"),
        }.get(sub, self._tr("batch.stream_copy"))
        sub_kind = "warn" if sub in ("remove", "dropped") else (
            "conv" if sub in ("mov_text", "webvtt") else "keep"
        )
        audio = self._audio_name()
        audio_kind = {
            "smart": "", "copy": "keep", "aac": "conv", "remove": "warn",
        }.get(self._settings.audio, "")

        columns = (
            (self._tr("batch.stream_video"), self._tr("batch.stream_copy"), "keep"),
            (self._tr("batch.stream_audio"), audio, audio_kind),
            (self._tr("batch.stream_subs"), sub_text, sub_kind),
        )
        for index, (key, value, kind) in enumerate(columns):
            if index:
                line = QFrame()
                line.setFixedWidth(1)
                line.setStyleSheet(
                    f"background: {_css(self._tokens['line'])}; border: none;"
                )
                row.addWidget(line)
            cell = QWidget()
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(11, 8, 11, 9)
            cell_layout.setSpacing(2)
            key_label = QLabel(key)
            key_label.setObjectName("BatchStreamKey")
            _set_font(key_label, 9, QFont.Weight.DemiBold, 0.6)
            value_row = QHBoxLayout()
            value_row.setContentsMargins(0, 0, 0, 0)
            value_row.setSpacing(5)
            color = {
                "keep": self._tokens["green"],
                "conv": self._tokens["accent"],
                "warn": self._tokens["amber"],
            }.get(kind, self._tokens["ink_3"])
            value_row.addWidget(_Dot(color), 0, Qt.AlignmentFlag.AlignVCenter)
            value_label = QLabel(value)
            value_label.setObjectName("BatchStreamValue")
            if kind == "warn":
                value_label.setStyleSheet(
                    f"color: {_css(self._tokens['amber'])}; background: transparent;"
                )
            value_row.addWidget(value_label, 1)
            cell_layout.addWidget(key_label)
            cell_layout.addLayout(value_row)
            row.addWidget(cell, 1)
        return strip

    def _advanced_footer(self) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        safety = self._tr(
            "batch.safety_custom" if self._settings.task == "custom" else "batch.safety"
        )
        layout.addWidget(_HintRow(safety, self._tokens, "neutral"))

        toggle = _ClickRow()
        toggle.clicked.connect(self._toggle_advanced)
        toggle_row = QHBoxLayout(toggle)
        toggle_row.setContentsMargins(0, 10, 0, 0)
        toggle_row.setSpacing(9)
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background: {_css(self._tokens['line'])}; border: none;")

        head = QWidget()
        head_row = QHBoxLayout(head)
        head_row.setContentsMargins(0, 0, 0, 0)
        head_row.setSpacing(9)
        self._adv_chevron = _AdvChevron(self._settings.advanced, self._tokens)
        self._adv_chevron.setStyleSheet("background: transparent;")
        text = QLabel(self._tr("batch.advanced"))
        _set_font(text, 11, QFont.Weight.DemiBold)
        text.setStyleSheet(
            f"color: {_css(self._tokens['ink_3'])}; font-size: 11px;"
            " font-weight: 600; background: transparent;"
        )
        head_row.addWidget(self._adv_chevron)
        head_row.addWidget(text)
        summary_key = (
            "batch.adv_summary_custom"
            if self._settings.task == "custom" else "batch.adv_summary"
        )
        self._adv_summary = QLabel(self._tr(summary_key))
        self._adv_summary.setObjectName("BatchAdvSummary")
        self._adv_summary.setVisible(not self._settings.advanced)
        head_row.addStretch(1)
        head_row.addWidget(self._adv_summary)

        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.setSpacing(0)
        wrapper_layout.addWidget(line)
        wrapper_layout.addWidget(head)
        layout.addWidget(wrapper)
        self._adv_toggle = toggle
        return box

    def _build_advanced(self) -> None:
        if not self._settings.advanced:
            return
        panel = QWidget()
        grid = QGridLayout(panel)
        grid.setContentsMargins(0, 2, 0, 1)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(9)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        row = 0
        spec = batch.encoder(self._resolved_encoder())

        if self._settings.task != "custom":
            audio = self._select("audio", self._audio_choices(),
                                 self._settings.audio, 230)
            subs = self._select("subtitle", [
                ("smart", self._tr("batch.sub_smart")),
                ("remove", self._tr("batch.sub_remove")),
            ], self._settings.subtitle, 220)
            grid.addWidget(self._field_block(self._tr("batch.audio"), audio), row, 0)
            grid.addWidget(self._field_block(self._tr("batch.subtitles"), subs), row, 1)
            row += 1

        if self._settings.task == "compress":
            spec = batch.encoder(self._resolved_encoder())
            try:
                value = batch.quality_value(
                    spec.key, self._settings.quality,
                    self._settings.custom_quality or None,
                )
            except ValueError:
                value = spec.tiers[batch.QUALITY_TIERS.index(self._settings.quality)
                                   if self._settings.quality in batch.QUALITY_TIERS else 1]
            quality_value = self._line_edit(
                "quality_value", str(value), self._tr("batch.quality_value"),
            )
            quality_value.setMaximumWidth(120)
            grid.addWidget(self._field_block(self._tr("batch.quality_value"),
                                             quality_value), row, 0)
            presets = [(item, item) for item in spec.presets]
            preset = self._select(
                "encoder_preset", presets,
                self._settings.encoder_preset or spec.preset, 180,
            )
            grid.addWidget(self._field_block(self._tr("batch.encoder_preset"),
                                             preset), row, 1)
            row += 1

        failure = self._select("failure", [
            ("continue", self._tr("batch.failure_continue")),
            ("stop", self._tr("batch.failure_stop")),
        ], self._settings.failure, 220)
        grid.addWidget(self._field_block(self._tr("batch.failure"), failure), row, 0)
        row += 1

        if self._settings.task != "custom":
            fallback_enabled = spec.hardware
            fallback = _CheckLine(self._tr("batch.fallback"),
                                  self._settings.fallback and fallback_enabled,
                                  self._tokens, enabled=fallback_enabled)
            if not fallback_enabled:
                fallback.check.setChecked(False)
            fallback.check.toggled.connect(
                lambda on: self._set_check("fallback", on)
            )
            grid.addWidget(fallback, row, 0, 1, 2)
            row += 1
            metadata = _CheckLine(self._tr("batch.metadata"),
                                  self._settings.metadata, self._tokens)
            metadata.check.toggled.connect(
                lambda on: self._set_check("metadata", on)
            )
            grid.addWidget(metadata, row, 0, 1, 2)
            row += 1
        else:
            note = QLabel(self._tr("batch.custom_adv_note"))
            note.setObjectName("BatchAdvNote")
            note.setWordWrap(True)
            _set_font(note, 10)
            grid.addWidget(note, row, 0, 1, 2)
            row += 1

        self._form_layout.addWidget(panel)

    # ------------------------------------------------------------------
    # choices & labels
    # ------------------------------------------------------------------

    def _available_map(self) -> dict[str, bool] | None:
        if self._availability is None:
            return None
        return batch.available_map(self._availability)

    def _is_available(self, key: str) -> bool:
        if self._availability is None:
            return True
        item = self._availability.get(key)
        return bool(item and item.available)

    def _reason_text(self, key: str) -> str:
        if self._availability is None:
            return ""
        item = self._availability.get(key)
        if item is None or item.available:
            return ""
        return self._tr(f"batch.reason_{item.reason}")

    def _resolved_encoder(self) -> str:
        if self._settings.task != "compress":
            return "x265"
        available = self._available_map()
        if available is not None:
            return batch.resolve_encoder(self._settings.encoder, available)
        if self._settings.encoder != "auto":
            return self._settings.encoder
        if 0x10DE in self._vendor_ids:
            return "nvenc_hevc"
        if 0x1002 in self._vendor_ids:
            return "amf_hevc"
        return "x265"

    def _quality_text(self) -> str:
        """Quality label that survives an in-progress (invalid) override."""
        spec = batch.encoder(self._resolved_encoder())
        try:
            return batch.quality_text(
                spec.key, self._settings.quality,
                self._settings.custom_quality or None,
            )
        except ValueError:
            index = (batch.QUALITY_TIERS.index(self._settings.quality)
                     if self._settings.quality in batch.QUALITY_TIERS else 1)
            return f"{spec.qkind} {spec.tiers[index]}"

    def _encoder_choices(self) -> list[tuple]:
        auto = self._resolved_encoder()
        choices: list[tuple] = [(
            "auto",
            f"{self._tr('batch.auto')} — {batch.encoder(auto).label}",
        )]
        families = []
        if 0x10DE in self._vendor_ids:
            families.append(("nvenc", self._tr("batch.hardware_nvidia")))
        if 0x1002 in self._vendor_ids:
            families.append(("amf", self._tr("batch.hardware_amd")))
        if not families:
            families.append(("nvenc", self._tr("batch.hardware")))
            families.append(("amf", self._tr("batch.hardware")))
        for family, title in families:
            choices.append((title,))
            for key in next(keys for fam, keys in batch.ENCODER_GROUPS if fam == family):
                spec = batch.ENCODERS[key]
                available = self._is_available(key)
                choices.append((
                    key, spec.label, not available,
                    self._reason_text(key) if not available else "",
                ))
        choices.append((self._tr("batch.cpu"),))
        for key in ("x265", "x264"):
            spec = batch.ENCODERS[key]
            available = self._is_available(key)
            choices.append((
                key, spec.label, not available,
                self._reason_text(key) if not available else "",
            ))
        return choices

    def _container_choices(self) -> list[tuple]:
        if self._settings.task == "custom":
            allowed = self._ext_values()
        else:
            allowed = batch.containers_for(self._settings.task, self._resolved_encoder())
        return [(value, self._container_name(value)) for value in allowed]

    def _ext_choices(self) -> list[tuple]:
        return [(value, self._container_name(value)) for value in self._ext_values()]

    def _ext_values(self) -> tuple[str, ...]:
        return (batch.ORIGINAL,) + batch.ALL_CONTAINERS

    def _container_name(self, value: str) -> str:
        if value == batch.ORIGINAL:
            return self._tr("batch.container_original")
        return value.upper()

    def _audio_choices(self) -> list[tuple]:
        ext = self._settings.container
        return [
            ("smart", self._tr("batch.audio_smart")),
            ("copy", self._tr("batch.audio_copy")),
            ("aac", self._tr("batch.audio_opus") if ext == "webm"
             else self._tr("batch.audio_aac")),
            ("remove", self._tr("batch.audio_remove")),
        ]

    def _audio_name(self) -> str:
        mode = self._settings.audio
        if mode == "smart":
            return self._tr("batch.audio_smart_short")
        if mode == "copy":
            return self._tr("batch.stream_copy")
        if mode == "remove":
            return self._tr("batch.stream_remove")
        return (self._tr("batch.audio_opus") if self._settings.container == "webm"
                else self._tr("batch.audio_aac"))

    def _subtitle_name(self) -> str:
        return (self._tr("batch.stream_remove") if self._settings.subtitle == "remove"
                else self._tr("batch.sub_smart_short"))

    def _task_note(self) -> tuple[str, str]:
        if self._settings.task == "remux":
            return "ok", self._tr("batch.note_remux")
        if self._settings.task == "custom":
            return "ok", self._tr("batch.note_custom")
        spec = batch.encoder(self._resolved_encoder())
        if spec.family == "nvenc":
            return "ok", self._tr("batch.note_nvenc")
        if spec.family == "amf":
            return "ok", self._tr("batch.note_amf")
        return "warn", self._tr("batch.note_cpu")

    def _compat_note(self) -> tuple[str, str]:
        container = self._settings.container
        key = f"batch.compat_{container}"
        text = self._tr(key)
        if text == key:
            text = self._tr("batch.compat_other")
        kind = "warn" if container in ("webm", "avi", "flv") else "ok"
        return kind, text

    # ------------------------------------------------------------------
    # state changes
    # ------------------------------------------------------------------

    def _clamp_settings(self) -> None:
        if self._settings.task == "custom":
            if self._settings.target_ext not in self._ext_values():
                self._settings.target_ext = batch.ORIGINAL
        else:
            allowed = batch.containers_for(
                self._settings.task, self._resolved_encoder(),
            )
            if self._settings.container not in allowed:
                self._settings.container = batch.default_container(
                    self._settings.task, self._resolved_encoder(),
                )

    def _clamp_container(self) -> None:
        allowed = batch.containers_for(
            self._settings.task, self._resolved_encoder(),
        )
        if self._settings.container not in allowed:
            self._settings.container = batch.default_container(
                self._settings.task, self._resolved_encoder(),
            )

    def _on_task(self, task: str) -> None:
        if self._view != "config" or task == self._settings.task:
            return
        previous_default = batch.DEFAULT_SUFFIX.get(self._settings.task)
        self._settings.task = task
        if not self._settings.suffix or self._settings.suffix == previous_default:
            self._settings.suffix = batch.DEFAULT_SUFFIX[task]
        self._settings.container = batch.default_container(task, self._resolved_encoder())
        self._refresh_all(rebuild=True)
        QTimer.singleShot(0, self._scroll_to_top)

    def _on_select(self, key: str, value) -> None:
        if value is None:
            return
        if key == "encoder":
            self._settings.encoder = str(value)
            self._settings.encoder_preset = ""
            self._settings.custom_quality = ""
            self._clamp_container()
            self._refresh_all(rebuild=True, focus="encoder")
        elif key == "container":
            self._settings.container = str(value)
            if self._settings.audio == "aac" and self._settings.container != "webm":
                pass
            self._refresh_all(rebuild=True, focus="container")
        elif key == "output":
            self._settings.output = str(value)
            self._refresh_all(rebuild=True, focus="output")
        elif key == "target_ext":
            self._settings.target_ext = str(value)
            self._refresh_summary()
        elif key == "preset":
            self._settings.preset = str(value)
            preset = next((p for p in self._presets if p.key == value), None)
            if preset is not None:
                self._settings.template = preset.template
                editor = self._fields.get("template")
                if isinstance(editor, QTextEdit):
                    editor.blockSignals(True)
                    editor.setPlainText(preset.template)
                    editor.blockSignals(False)
            self._refresh_summary()
        elif key == "audio":
            self._settings.audio = str(value)
            if self._settings.task == "remux":
                self._refresh_all(rebuild=True, focus="audio")
            else:
                self._refresh_summary()
        elif key == "subtitle":
            self._settings.subtitle = str(value)
            if self._settings.task == "remux":
                self._refresh_all(rebuild=True, focus="subtitle")
            else:
                self._refresh_summary()
        elif key == "conflict":
            self._settings.conflict = str(value)
            self._refresh_all(rebuild=True, focus="conflict")
        elif key == "failure":
            self._settings.failure = str(value)
        elif key == "encoder_preset":
            self._settings.encoder_preset = str(value)
            self._refresh_summary()

    def _on_quality(self, value: str) -> None:
        self._settings.quality = value
        self._settings.custom_quality = ""
        spec = batch.encoder(self._resolved_encoder())
        if self._quality_label is not None:
            self._quality_label.setText(
                batch.quality_text(spec.key, value, None)
            )
        editor = self._fields.get("quality_value")
        if isinstance(editor, QLineEdit):
            editor.blockSignals(True)
            editor.setText(str(batch.quality_value(spec.key, value, None)))
            editor.blockSignals(False)
        self._refresh_summary()

    def _on_text(self, key: str, text: str) -> None:
        if self._refreshing:
            return
        if key == "suffix":
            self._settings.suffix = text
        elif key == "folder":
            self._settings.folder = text
        elif key == "quality_value":
            self._settings.custom_quality = text.strip()
            if self._quality_label is not None:
                self._quality_label.setText(self._quality_text())
        self._schedule_refresh()

    def _on_template_changed(self) -> None:
        editor = self._fields.get("template")
        if isinstance(editor, QTextEdit):
            self._settings.template = editor.toPlainText()
            if not self._refreshing:
                self._schedule_refresh()

    def _schedule_refresh(self) -> None:
        """Coalesce keystrokes so planning does not stat the disk per character."""
        self._preview_timer.start()

    def _set_check(self, key: str, on: bool) -> None:
        if key == "fallback":
            self._settings.fallback = on
        elif key == "metadata":
            self._settings.metadata = on
            self._refresh_summary()

    def _toggle_advanced(self) -> None:
        self._settings.advanced = not self._settings.advanced
        self._refresh_all(rebuild=True)
        if self._settings.advanced:
            QTimer.singleShot(0, self._scroll_to_bottom)

    def _scroll_to_top(self) -> None:
        self._cancel_bottom_hook()
        self._form_scroll.verticalScrollBar().setValue(0)

    def _scroll_to_bottom(self) -> None:
        self._cancel_bottom_hook()
        bar = self._form_scroll.verticalScrollBar()
        if bar.maximum() > 0:
            bar.setValue(bar.maximum())
            return

        def on_range(_minimum: int, maximum: int) -> None:
            if maximum > 0:
                bar.setValue(maximum)
                self._cancel_bottom_hook()

        bar.rangeChanged.connect(on_range)
        self._bottom_hook = (bar, on_range)
        QTimer.singleShot(400, lambda: self._cancel_bottom_hook(bar, on_range))

    def _cancel_bottom_hook(self, bar=None, slot=None) -> None:
        hook = self._bottom_hook
        self._bottom_hook = None
        if hook is None:
            return
        hook_bar, hook_slot = hook
        if bar is not None and (bar, slot) != hook:
            self._bottom_hook = hook
            return
        self._disconnect_range(hook_bar, hook_slot)

    @staticmethod
    def _disconnect_range(bar, slot) -> None:
        try:
            bar.rangeChanged.disconnect(slot)
        except (RuntimeError, TypeError):
            pass

    def _choose_folder(self) -> None:
        start = self._settings.folder or str(self._records[0].path.parent)
        path = QFileDialog.getExistingDirectory(
            self, self._tr("batch.folder"), start,
        )
        if path:
            editor = self._fields.get("folder")
            if isinstance(editor, QLineEdit):
                editor.setText(path)

    # ------------------------------------------------------------------
    # planning & preview
    # ------------------------------------------------------------------

    def _extension(self) -> str | None:
        if self._settings.task == "custom":
            return None if self._settings.target_ext == batch.ORIGINAL else self._settings.target_ext
        return None if self._settings.container == batch.ORIGINAL else self._settings.container

    def _target_folder(self) -> Path | None:
        if self._settings.output == "custom" and self._settings.folder.strip():
            return Path(self._settings.folder.strip())
        return None

    def _plan(self) -> list[batch.OutputTarget]:
        return batch.plan_outputs(
            [record.path for record in self._records],
            folder=self._target_folder(),
            suffix=self._settings.suffix,
            extension=self._extension(),
            conflict=self._settings.conflict,
        )

    def _build_spec(self) -> BuildSpec:
        encoder_key = self._resolved_encoder()
        quality: object = self._settings.custom_quality or None
        container = (
            self._settings.target_ext
            if self._settings.task == "custom"
            else self._settings.container
        )
        return BuildSpec(
            ffmpeg=find_ffmpeg() or "ffmpeg",
            task=self._settings.task,
            encoder=encoder_key,
            container=container,
            quality_tier=self._settings.quality,
            quality=quality,
            preset=self._settings.encoder_preset,
            audio=self._settings.audio,
            subtitles=self._settings.subtitle,
            metadata=self._settings.metadata,
            template=self._settings.template,
            fallback=self._settings.fallback,
        )

    def _jobs_from_plans(self, plans: list[batch.OutputTarget]) -> list[Job]:
        jobs: list[Job] = []
        for record, plan in zip(self._records, plans):
            duration = 0.0
            if record.metadata is not None:
                duration = record.metadata.duration
            jobs.append(Job(
                record.path, plan.target, duration=duration,
                skipped=plan.skipped, skip_reason=plan.reason,
            ))
        return jobs

    def _preview_entries(self) -> list[tuple[str, batch.OutputTarget]]:
        plans = self._plan()
        entries: list[tuple[str, batch.OutputTarget]] = []
        try:
            spec = self._build_spec()
            for record, plan in zip(self._records, plans):
                if plan.skipped:
                    continue
                entries.append((spec.preview(record.path, plan.target), plan))
                if len(entries) >= 3:
                    break
        except ValueError:
            pass
        return entries

    def _shorten(self, command: str) -> str:
        """Drop the ffmpeg install path from the preview; the copy keeps it."""
        binary = find_ffmpeg()
        if binary and command.startswith(binary):
            return "ffmpeg" + command[len(binary):]
        return command

    def _update_preview(self) -> None:
        entries = self._preview_entries()
        commands = [self._shorten(text) for text, _plan in entries]
        if self._settings.task == "custom" and not self._settings.template.strip():
            commands = [self._tr("batch.template_empty")]
        if not commands:
            commands = [self._tr("batch.preview_empty")]
        parts = []
        for index, command in enumerate(commands):
            border = "border-top: 1px solid " + _css(self._tokens["line"]) + ";" if index else ""
            parts.append(
                "<div style=\"white-space: pre-wrap; line-height: 155%; "
                f"padding: 1px 0; {border}\">{html.escape(command)}</div>"
            )
        self._preview_body.setHtml("".join(parts))
        total = sum(1 for plan in self._plan() if not plan.skipped)
        self._preview_count.setText(self._tr("batch.command_count", n=total))

    # ------------------------------------------------------------------
    # rail / chips / footer
    # ------------------------------------------------------------------

    def _check_rows(self) -> list[tuple[str, str]]:
        rows: list[tuple[str, str]] = []
        total = len(self._records)
        total_bytes = sum(record.size for record in self._records)
        files = self._tr("batch.rail_files", n=total, size=format_size(total_bytes))

        if self._view == "running":
            rows.append(("ok", self._tr("batch.check_current", i=self._current_index + 1, n=total)))
            rows.append(("neutral", self._tr("batch.check_elapsed",
                                             time=self._elapsed_text())))
            if self._fallback_count:
                rows.append(("warn", self._tr("batch.check_fallback_n",
                                              n=self._fallback_count)))
            else:
                rows.append(("neutral", self._tr("batch.check_fallback_ok")))
            return rows

        if self._view in ("done", "failed") and self._summary is not None:
            rows.append(("ok", self._tr("batch.check_success",
                                        n=self._summary.succeeded)))
            rows.append(("bad" if self._summary.failed else "neutral",
                         self._tr("batch.check_failed", n=self._summary.failed)))
            rows.append(("neutral", self._tr("batch.check_skipped",
                                             n=self._summary.skipped)))
            return rows

        if self._settings.task == "custom":
            rows.append(("ok", files))
            rows.append(("neutral", self._tr("batch.check_custom_run")))
            rows.append(("warn", self._tr("batch.check_custom_precheck")))
            rows.append(("warn" if self._settings.conflict == "overwrite" else "ok",
                         self._tr("batch.check_custom_overwrite")
                         if self._settings.conflict == "overwrite"
                         else self._tr("batch.check_no_overwrite")))
            return rows

        rows.append(("ok", files))
        if self._settings.task == "compress":
            spec = batch.encoder(self._resolved_encoder())
            if spec.family == "cpu":
                rows.append(("warn", self._tr("batch.check_no_hw")))
            else:
                rows.append(("ok", self._tr("batch.check_encoder_ok")))
        elif self._settings.container in ("webm", "avi"):
            rows.append(("warn", self._tr("batch.check_container_incompat")))
        else:
            rows.append(("ok", self._tr("batch.check_encoder_ok")))

        audio = self._settings.audio
        if audio == "copy":
            rows.append(("ok", self._tr("batch.check_audio_copy")))
        elif audio == "remove":
            rows.append(("warn", self._tr("batch.check_audio_remove")))
        elif audio == "aac":
            rows.append(("neutral", self._tr("batch.check_audio_aac")))
        else:
            rows.append(("warn", self._tr("batch.check_audio_smart")))

        if self._settings.subtitle == "remove":
            rows.append(("neutral", self._tr("batch.check_sub_remove")))
        else:
            container = self._settings.container
            if container in ("mp4", "mov", "m4v"):
                rows.append(("warn", self._tr("batch.check_sub_mov_text")))
            elif container == "mkv":
                rows.append(("ok", self._tr("batch.check_sub_keep")))
            else:
                rows.append(("neutral", self._tr("batch.check_sub_container")))
        return rows[:4]

    def _warning_count(self) -> int:
        if self._view != "config":
            return 0
        count = 0
        if self._settings.task == "compress":
            if batch.encoder(self._resolved_encoder()).family == "cpu":
                count += 1
        if (self._settings.task == "remux"
                and self._settings.container in ("webm", "avi")):
            count += 1
        if (self._settings.task != "custom"
                and self._settings.subtitle == "smart"
                and self._settings.container in ("mp4", "mov", "m4v")):
            count += 1
        if self._settings.conflict == "overwrite":
            count += 1
        return count

    def _update_rail(self) -> None:
        task = self._settings.task
        spec = batch.encoder(self._resolved_encoder())
        self._rail_values["mode"].setText(self._tr(f"batch.task_{task}_title"))
        if task == "remux":
            encoder_text = self._tr("batch.stream_copy_long")
        elif task == "custom":
            encoder_text = self._tr("batch.custom_template")
        else:
            encoder_text = spec.short
        self._rail_values["encoder"].setText(encoder_text)
        if task == "compress":
            quality_name = self._tr(f"batch.quality_{self._settings.quality}")
            self._rail_values["quality"].setText(
                f"{quality_name} · {self._quality_text()}"
            )
        else:
            self._rail_values["quality"].setText("—")
        container = (self._settings.target_ext if task == "custom"
                     else self._settings.container)
        self._rail_values["container"].setText(self._container_name(container))
        if task == "custom":
            self._rail_values["strategy"].setText(self._tr("batch.strategy_template"))
        else:
            self._rail_values["strategy"].setText(
                f"{self._audio_name()} / {self._subtitle_name()}"
            )
        output = self._tr("batch.output_same") if self._settings.output == "same" else self._tr("batch.output_custom")
        self._rail_values["output"].setText(f"{output} · {self._settings.suffix or '—'}")

        self._rail_check_title.setText(
            self._tr("batch.rail_running") if self._view == "running"
            else self._tr("batch.rail_result") if self._view in ("done", "failed")
            else self._tr("batch.rail_check")
        )
        while self._check_box.count():
            item = self._check_box.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        for kind, text in self._check_rows():
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 4, 0, 4)
            layout.setSpacing(7)
            color = {
                "ok": self._tokens["green"],
                "warn": self._tokens["amber"],
                "bad": self._tokens["red"],
            }.get(kind, self._tokens["ink_3"])
            layout.addWidget(_Dot(color), 0, Qt.AlignmentFlag.AlignTop)
            label = QLabel(text)
            label.setWordWrap(True)
            label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            _set_font(label, 10)
            label.setStyleSheet(
                f"color: {_css(self._tokens['ink_3'])}; font-size: 10px;"
                " background: transparent;"
            )
            layout.addWidget(label, 1)
            self._check_box.addWidget(row)

    def _update_chips(self) -> None:
        task = self._settings.task
        if task == "remux":
            encoder_text = self._tr("batch.stream_copy_long")
        elif task == "custom":
            encoder_text = self._tr("batch.custom")
        else:
            encoder_text = batch.encoder(self._resolved_encoder()).short
        self._chip_encoder.setText(encoder_text)
        self._chip_files.setText(self._tr("batch.chip_files", n=len(self._records)))
        warnings = self._warning_count()
        self._chip_warn.setText(
            self._tr("batch.chip_warnings", n=warnings) if warnings
            else self._tr("batch.chip_no_conflicts")
        )
        self._chip_warn.setProperty("tone", "warn" if warnings else "")
        _repolish(self._chip_warn)

    def _update_header(self) -> None:
        total = sum(record.size for record in self._records)
        self._lede_label.setText(self._tr(
            "batch.lede", n=len(self._records), size=format_size(total),
        ))

    def _render_footer(self) -> None:
        while self._foot_layout.count():
            item = self._foot_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        left_text = {
            "config": self._tr("batch.footer_files", n=len(self._records)),
            "running": self._tr("batch.processing"),
            "failed": self._tr("batch.footer_failed", ok=self._summary.succeeded,
                               failed=self._summary.failed) if self._summary
            else self._tr("batch.processing"),
            "done": self._tr("batch.footer_written",
                             n=self._summary.succeeded if self._summary
                             else len(self._records)),
        }.get(self._view, "")
        left = QLabel(left_text)
        left.setObjectName("BatchFootLeft")
        _set_font(left, 10)
        self._foot_layout.addWidget(left)
        self._foot_layout.addStretch(1)

        def add(text: str, slot, variant: str = "ghost") -> None:
            button = QPushButton(text)
            button.setProperty("variant", variant)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFixedHeight(34)
            button.clicked.connect(slot)
            self._foot_layout.addWidget(button)

        if self._view == "config":
            add(self._tr("batch.close"), self.reject)
            add(self._tr("batch.save_bat"), self._save_bat)
            add(self._tr("batch.copy"), self._copy_commands)
            add(self._tr("batch.start"), self._start, "primary")
        elif self._view == "running":
            add(self._tr("batch.cancel"), self._cancel)
        elif self._view == "failed":
            add(self._tr("batch.copy_failures"), self._copy_failures)
            add(self._tr("batch.close"), self.reject)
            add(self._tr("batch.open_output"), self._open_output, "primary")
        else:
            add(self._tr("batch.close"), self.reject)
            add(self._tr("batch.open_output"), self._open_output, "primary")

    def _refresh_summary(self) -> None:
        self._update_header()
        self._update_chips()
        self._update_rail()
        self._update_preview()
        if self._view == "config":
            self._render_footer()

    def _refresh_all(self, rebuild: bool = False, focus: str | None = None) -> None:
        for kind, card in self._cards.items():
            card.set_on(kind == self._settings.task)
        if rebuild:
            self._rebuild_form(focus=focus)
        self._refresh_summary()

    # ------------------------------------------------------------------
    # view switching & probing
    # ------------------------------------------------------------------

    def _start_probe(self) -> None:
        probe = EncoderProbe()
        _ACTIVE_PROBES.add(probe)
        probe.done.connect(self._on_probe_done)
        probe.finished.connect(lambda p=probe: _ACTIVE_PROBES.discard(p))
        self._probe = probe
        probe.start()

    def _on_probe_done(self, report: dict) -> None:
        self._availability = report
        if self._closing:
            return
        if (self._settings.encoder != "auto"
                and not self._is_available(self._settings.encoder)):
            self._settings.encoder = "auto"
        focus = QApplication.focusWidget()
        if isinstance(focus, (QLineEdit, QTextEdit)):
            # Do not rebuild under the user's cursor mid-keystroke.
            self._refresh_summary()
        else:
            self._refresh_all(rebuild=True)

    def _set_view(self, view: str) -> None:
        self._view = view
        locked = view != "config"
        for card in self._cards.values():
            card.setEnabled(not locked)
        self._form_scroll.setEnabled(not locked)
        self._task_effect.setOpacity(0.62 if locked else 1.0)
        self._form_effect.setOpacity(0.62 if locked else 1.0)
        if view == "config":
            self._stack.setCurrentIndex(0)
        elif view == "running":
            self._stack.setCurrentIndex(1)
        else:
            self._stack.setCurrentIndex(2)
        self._update_rail()
        self._render_footer()

    # ------------------------------------------------------------------
    # running
    # ------------------------------------------------------------------

    def _validate_start(self) -> bool:
        if find_ffmpeg() is None:
            message_box(self, "warning", self._tr("batch.title"),
                        self._tr("batch.msg_no_ffmpeg"))
            return False
        if self._settings.task == "custom" and not self._settings.template.strip():
            message_box(self, "info", self._tr("batch.title"),
                        self._tr("batch.template_empty"))
            return False
        if self._settings.output == "custom" and not self._settings.folder.strip():
            message_box(self, "info", self._tr("batch.title"),
                        self._tr("batch.msg_no_folder"))
            return False
        return True

    def _start(self) -> None:
        if self._view != "config" or not self._validate_start():
            return
        plans = self._plan()
        runnable = [plan for plan in plans if plan.ok]
        if not runnable:
            message_box(self, "info", self._tr("batch.title"),
                        self._tr("batch.msg_nothing_to_do"))
            return
        if self._settings.conflict == "overwrite":
            existing = sum(1 for plan in runnable if plan.target.exists())
            if existing:
                answer = message_box(
                    self, "warning", self._tr("batch.title"),
                    self._tr("batch.confirm_overwrite", n=existing),
                    buttons=(
                        QMessageBox.StandardButton.Yes
                        | QMessageBox.StandardButton.No
                    ),
                    default=QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return

        self._save_settings()
        self._plans = plans
        self._jobs = self._jobs_from_plans(plans)
        self._summary = None
        self._fallback_count = 0
        self._current_name = ""
        self._last_output_folder = runnable[0].target.parent
        self._started_at = time.monotonic()

        executor = BatchExecutor(
            self._jobs, self._build_spec(), failure=self._settings.failure,
        )
        self._worker = BatchWorker(executor, self)
        self._worker.job_started.connect(self._on_job_started)
        self._worker.progressed.connect(self._on_progress)
        self._worker.job_result.connect(self._on_job_result)
        self._worker.logged.connect(self._on_log)
        self._worker.completed.connect(self._on_finished)
        self._run_counter.setText(self._tr("batch.counter", i=1, n=len(self._jobs)))
        self._run_clock.setText(self._tr("batch.elapsed", time="00:00"))
        self._run_bar.set_value(0)
        self._file_bar.set_value(0)
        self._run_file.setText("")
        self._run_detail.setText("")
        self._run_log.clear()
        self._set_view("running")
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._tick_clock)
        self._timer.start()
        self._worker.start()

    def _tick_clock(self) -> None:
        if self._view != "running":
            return
        self._run_clock.setText(self._tr("batch.elapsed_left",
                                          time=self._elapsed_text()))

    def _elapsed_text(self) -> str:
        seconds = max(0.0, time.monotonic() - self._started_at) if self._started_at else 0.0
        return time.strftime("%M:%S", time.gmtime(seconds))

    def _on_job_started(self, index: int, job: Job) -> None:
        self._current_index = index
        self._current_name = job.source.name
        self._run_counter.setText(self._tr("batch.counter", i=index + 1, n=len(self._jobs)))
        self._run_file.setText(job.source.name)
        self._run_detail.setText(self._tr("batch.file_starting"))
        self._file_bar.set_value(0)
        spec = batch.encoder(self._resolved_encoder())
        quality = (f" · {self._quality_text()}"
                   if self._settings.task == "compress" else "")
        self._append_log(
            f"[{index + 1}/{len(self._jobs)}] {job.source.name} · "
            f"{spec.short if self._settings.task == 'compress' else self._tr(f'batch.task_{self._settings.task}_title')}"
            f"{quality}",
            "neutral",
        )
        self._update_rail()

    def _on_progress(self, index: int, overall: float,
                     current: float, speed: float) -> None:
        self._current_index = index
        self._run_bar.set_value(overall)
        self._file_bar.set_value(current)
        speed_text = f"{speed:.1f}×" if speed else "—"
        self._run_detail.setText(f"{current:.0f}% · {speed_text}")

    def _on_job_result(self, index: int, result: JobResult) -> None:
        if result.fallback:
            self._fallback_count += 1
        if result.status == "ok":
            self._append_log(
                self._tr("batch.log_ok", name=result.source.name,
                         time=format_duration(result.seconds)), "ok")
        elif result.status == "failed":
            self._append_log(
                self._tr("batch.log_failed", name=result.source.name,
                         message=result.message), "bad")
        elif result.status == "skipped":
            self._append_log(
                self._tr("batch.log_skipped", name=result.source.name), "neutral")
        self._update_rail()

    def _on_log(self, text: str) -> None:
        self._append_log(text, "warn")

    def _append_log(self, text: str, kind: str) -> None:
        color = {
            "ok": self._tokens["green"],
            "warn": self._tokens["amber"],
            "bad": self._tokens["red"],
        }.get(kind, self._tokens["ink_3"])
        self._run_log.append(
            f"<div style=\"color: {color}; white-space: pre;\">{html.escape(text)}</div>"
        )
        bar = self._run_log.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _on_finished(self, summary: BatchSummary) -> None:
        self._summary = summary
        if self._timer is not None:
            self._timer.stop()
        self._run_bar.set_value(100 if not summary.cancelled else self._run_bar.value())
        view = "failed" if summary.failed else "done"
        self._set_view(view)
        self._fill_summary(summary)
        self._save_settings()

    def _fill_summary(self, summary: BatchSummary) -> None:
        failed = summary.failed
        cancelled = summary.cancelled
        fallback = summary.results and any(item.fallback for item in summary.results)
        icon_class = "bad" if failed else "warn" if (fallback or cancelled) else "ok"
        glyph = "!" if failed or cancelled else "✓" if not fallback else "!"
        color = {
            "ok": self._tokens["green"],
            "warn": self._tokens["amber"],
            "bad": self._tokens["red"],
        }[icon_class]
        color_q = parse_color(color)
        self._summary_icon.setText(glyph)
        self._summary_icon.setStyleSheet(
            f"background: rgba({color_q.red()}, {color_q.green()}, {color_q.blue()}, 14%);"
            f" color: {_css(color)}; border-radius: 19px; border: none;"
            " font-size: 17px; font-weight: 700;"
        )
        if cancelled:
            title = self._tr("batch.summary_cancelled")
        elif failed:
            title = self._tr("batch.summary_failed_title", n=failed)
        else:
            title = self._tr("batch.summary_done")
        self._summary_title.setText(title)
        if cancelled:
            sub = self._tr("batch.summary_cancelled_sub", ok=summary.succeeded,
                           failed=failed)
        elif failed:
            sub = self._tr("batch.summary_failed_sub", ok=summary.succeeded,
                           failed=failed)
        elif fallback:
            sub = self._tr("batch.summary_fallback_sub", n=summary.succeeded)
        else:
            sub = self._tr("batch.summary_ok_sub", n=summary.succeeded)
        self._summary_sub.setText(sub)

        self._stat_values["ok"].setText(str(summary.succeeded))
        self._stat_values["failed"].setText(str(failed))
        self._stat_values["skipped"].setText(str(summary.skipped))
        self._stat_values["elapsed"].setText(
            format_duration(summary.elapsed)
        )
        self._stat_values["ok"].setStyleSheet(f"color: {_css(self._tokens['green'])};")
        self._stat_values["failed"].setStyleSheet(
            f"color: {_css(self._tokens['red'] if failed else self._tokens['ink'])};"
        )

        before = summary.input_bytes
        after = summary.output_bytes
        if before and after:
            self._size_value.setText(
                f"{format_size(before)}  →  {format_size(after)}"
            )
            saved = summary.saved_ratio * 100
            if saved >= 1:
                self._size_delta.setText(self._tr("batch.size_saved", pct=f"{saved:.0f}"))
                self._size_delta.setStyleSheet(
                    f"color: {_css(self._tokens['green'])};"
                )
            else:
                self._size_delta.setText(self._tr("batch.size_no_change"))
                self._size_delta.setStyleSheet(
                    f"color: {_css(self._tokens['ink_3'])};"
                )
        else:
            self._size_value.setText("—")
            self._size_delta.setText("")

        failures = [item for item in summary.results if item.status == "failed"]
        if failures:
            first = failures[0]
            self._fail_name.setText(first.source.name)
            self._fail_text.setText(first.message or self._tr("batch.failed_generic"))
            self._fail_row.show()
        else:
            self._fail_row.hide()

    def _all_commands(self) -> list[str]:
        """Every command in the batch (copy/save-bat), not just the previewed 3."""
        commands: list[str] = []
        try:
            spec = self._build_spec()
        except ValueError:
            return commands
        for record, plan in zip(self._records, self._plan()):
            if plan.skipped:
                continue
            try:
                commands.append(spec.preview(record.path, plan.target))
            except ValueError:
                break
        return commands

    def _cancel(self) -> None:
        if self._worker is not None:
            self._worker.cancel()

    # ------------------------------------------------------------------
    # actions
    # ------------------------------------------------------------------

    def _copy_commands(self) -> None:
        commands = self._all_commands()
        if not commands:
            message_box(self, "info", self._tr("batch.title"),
                        self._tr("batch.preview_empty"))
            return
        QGuiApplication.clipboard().setText("\n\n".join(commands))
        self._append_toast(self._tr("batch.copied", n=len(commands)))

    def _save_bat(self) -> None:
        commands = self._all_commands()
        if not commands:
            message_box(self, "info", self._tr("batch.title"),
                        self._tr("batch.preview_empty"))
            return
        path, _ = QFileDialog.getSaveFileName(
            self, self._tr("batch.save_bat"), "transcode.bat", "Batch (*.bat)",
        )
        if not path:
            return
        try:
            Path(path).write_text(
                batch.batch_file_text(commands),
                encoding="gbk", errors="replace",
            )
        except OSError as exc:
            message_box(self, "critical", self._tr("batch.title"), str(exc))
            return
        message_box(self, "info", self._tr("batch.save_bat"),
                    self._tr("batch.bat_saved", path=path))

    def _copy_failures(self) -> None:
        if self._summary is None:
            return
        lines = [
            f"{item.source}\t{item.message}"
            for item in self._summary.results if item.status == "failed"
        ]
        QGuiApplication.clipboard().setText("\n".join(lines))
        self._append_toast(self._tr("batch.copied_failures", n=len(lines)))

    def _open_output(self) -> None:
        folder = self._last_output_folder
        if folder is None and self._plans:
            folder = self._plans[0].target.parent
        if folder is None:
            folder = self._records[0].path.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _append_toast(self, text: str) -> None:
        self._run_log.append(
            f"<div style=\"color: {_css(self._tokens['ink_3'])};\">{html.escape(text)}</div>"
        )

    def _save_settings(self) -> None:
        if self._config is None:
            return
        try:
            self._config.batch_settings = self._settings.to_dict()
            self._config.save()
        except OSError:
            pass

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    def done(self, result: int) -> None:
        self._save_settings()
        super().done(result)

    def reject(self) -> None:
        self._closing = True
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            if not self._worker.wait(4000):
                return
        if self._probe is not None:
            self._probe.stop()
            self._probe = None
        self._save_settings()
        super().reject()