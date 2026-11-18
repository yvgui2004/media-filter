"""Shared chrome for secondary dialogs.

Native Windows frame (drag / resize / Esc for free) tinted to the active
palette through DWM so the caption melts into the Light Table canvas.
Form controls below reuse the toolbar tokens: 11px section labels, 34px
outlined fields, hairline rules, ghost + accent buttons.
"""

from __future__ import annotations

import ctypes
import sys
from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QVBoxLayout, QWidget,
)

from .motion import FAST, fade_in_window
from .tokens import LIGHT, parse_color

_DWMWA_BORDER_COLOR = 34
_DWMWA_CAPTION_COLOR = 35
_DWMWA_TEXT_COLOR = 36
_DWMWA_USE_IMMERSIVE_DARK_MODE = 20

_dialog_tokens: dict[str, str] = LIGHT
_dialog_tr: Callable[[str], str] | None = None


def set_dialog_tokens(tokens: dict[str, str]) -> None:
    """Keep app-level dialogs (message boxes) in step with the theme."""
    global _dialog_tokens
    _dialog_tokens = tokens


def set_dialog_translator(tr: Callable[[str], str] | None) -> None:
    """Localise standard message-box buttons with the app's own strings."""
    global _dialog_tr
    _dialog_tr = tr


def _colorref(color: QColor) -> int:
    return color.red() | (color.green() << 8) | (color.blue() << 16)


def tint_native_titlebar(widget: QWidget, tokens: dict[str, str]) -> None:
    """Paint the native caption with canvas/ink so dialogs join the theme."""
    if sys.platform != "win32":
        return
    try:
        hwnd = int(widget.winId())
        dwm = ctypes.windll.dwmapi
        dark = ctypes.c_int(
            1 if parse_color(tokens["surface"]).lightness() < 128 else 0
        )
        dwm.DwmSetWindowAttribute(
            hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(dark), ctypes.sizeof(dark),
        )
        for attribute, token in (
            (_DWMWA_CAPTION_COLOR, "canvas"),
            (_DWMWA_BORDER_COLOR, "canvas"),
            (_DWMWA_TEXT_COLOR, "ink"),
        ):
            value = ctypes.c_int(_colorref(parse_color(tokens[token])))
            dwm.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
            )
    except Exception:
        pass


class AppDialog(QDialog):
    """Themed modal dialog with a tinted native caption."""

    def __init__(
        self,
        tokens: dict[str, str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._tokens = tokens or LIGHT
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        self.setModal(True)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        tint_native_titlebar(self, self._tokens)
        # A 120 ms fade instead of a hard pop; the native caption is included
        # because the whole top-level window is blended.
        fade_in_window(self, FAST)


def section_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("SectionLabel")
    return label


def lede_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("DialogLede")
    label.setWordWrap(True)
    return label


def note_label(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setObjectName("DialogNote")
    label.setWordWrap(True)
    return label


def hint_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("Hint")
    return label


def count_label(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setObjectName("DialogCount")
    return label


def dialog_button(text: str, variant: str = "ghost") -> QPushButton:
    button = QPushButton(text)
    button.setProperty("variant", variant)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setMinimumHeight(34)
    return button


def add_footer(layout: QVBoxLayout, buttons: list[QPushButton]) -> None:
    layout.addSpacing(2)
    rule = QFrame()
    rule.setObjectName("DialogRule")
    rule.setFixedHeight(1)
    layout.addWidget(rule)
    row = QHBoxLayout()
    row.setSpacing(10)
    row.addStretch(1)
    for button in buttons:
        row.addWidget(button)
    layout.addLayout(row)


def mono_font(pixel_size: int = 12) -> QFont:
    font = QFont()
    font.setFamilies(
        ["Cascadia Mono", "Consolas", "Microsoft YaHei UI", "Courier New"]
    )
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPixelSize(pixel_size)
    return font


class DialogChromeFilter(QObject):
    """Tint every Qt dialog caption (message boxes included) on show."""

    def eventFilter(self, watched, event) -> bool:
        if (
            event.type() == QEvent.Type.Show
            and isinstance(watched, QDialog)
            and watched.isVisible()
        ):
            tint_native_titlebar(watched, _dialog_tokens)
        return super().eventFilter(watched, event)


_INFO_GLYPHS = {"info": "i", "question": "?", "warning": "!", "critical": "!"}

_STANDARD_BUTTONS = (
    (QMessageBox.StandardButton.Ok, "dialog.ok", "OK"),
    (QMessageBox.StandardButton.Cancel, "dialog.cancel", "Cancel"),
    (QMessageBox.StandardButton.Yes, "dialog.yes", "Yes"),
    (QMessageBox.StandardButton.No, "dialog.no", "No"),
)


def message_icon(level: str, tokens: dict[str, str], size: int = 40) -> QPixmap:
    """Accent/red soft-disc icon so message boxes stay in the palette."""
    scale = 2
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.scale(scale, scale)
    dangerous = level in ("warning", "critical")
    foreground = parse_color(tokens["red" if dangerous else "accent"])
    background = QColor(foreground)
    background.setAlpha(32)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(background)
    painter.drawEllipse(QRectF(1, 1, size - 2, size - 2))
    font = QFont()
    font.setPixelSize(18)
    font.setWeight(QFont.Weight.DemiBold)
    painter.setFont(font)
    painter.setPen(foreground)
    painter.drawText(
        QRectF(0, 0, size, size),
        int(Qt.AlignmentFlag.AlignCenter),
        _INFO_GLYPHS.get(level, "i"),
    )
    painter.end()
    pixmap.setDevicePixelRatio(scale)
    return pixmap


def message_box(
    parent: QWidget | None,
    level: str,
    title: str,
    text: str,
    buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
    default: QMessageBox.StandardButton | None = None,
) -> int:
    """QMessageBox with a themed icon, caption and ghost/accent buttons."""
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIconPixmap(message_icon(level, _dialog_tokens))
    box.setStandardButtons(buttons)
    if _dialog_tr is not None:
        for standard, key, fallback in _STANDARD_BUTTONS:
            button = box.button(standard)
            if button is not None:
                text = _dialog_tr(key)
                button.setText(fallback if text == key else text)
    if default is not None:
        box.setDefaultButton(default)
    return box.exec()