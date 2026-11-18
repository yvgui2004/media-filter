"""Non-blocking confirmation chip that appears above the status bar."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from .motion import BASE, FAST, set_faded_visible
from .tokens import LIGHT

_HOLD_MS = 1600


class Toast(QWidget):
    """One-line message, bottom centre, gone after 1.6 s.

    The toast never takes focus or the mouse: it is feedback for an action
    the user just completed, not another thing to dismiss.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tokens = LIGHT
        self.setObjectName("Toast")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMinimumHeight(34)

        row = QHBoxLayout(self)
        row.setContentsMargins(13, 8, 15, 8)
        row.setSpacing(9)
        self._dot = QFrame(self)
        self._dot.setFixedSize(6, 6)
        row.addWidget(self._dot, 0, Qt.AlignmentFlag.AlignVCenter)
        self._label = QLabel(self)
        self._label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        font = QFont(self._label.font())
        font.setPixelSize(12)
        self._label.setFont(font)
        row.addWidget(self._label)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(_HOLD_MS)
        self._timer.timeout.connect(self._fade_out)

        self.set_tokens(LIGHT)
        self.hide()

    def set_tokens(self, tokens: dict[str, str]) -> None:
        self._tokens = tokens
        self.setStyleSheet(
            "QWidget#Toast { background: %s; border: 1px solid %s; border-radius: 9px; }"
            % (tokens["surface"], tokens["line_strong"])
        )
        self._label.setStyleSheet(
            "background: transparent; color: %s;" % tokens["ink"]
        )
        self._dot.setStyleSheet(
            "background: %s; border-radius: 3px;" % tokens["accent"]
        )

    def show_message(self, text: str, duration_ms: int = _HOLD_MS) -> None:
        if not text:
            return
        self._timer.stop()
        self._label.setText(text)
        self.adjustSize()
        self.raise_()
        set_faded_visible(self, True, FAST)
        self._timer.start(max(400, duration_ms))

    def _fade_out(self) -> None:
        if self.isVisible():
            set_faded_visible(self, False, BASE)

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)