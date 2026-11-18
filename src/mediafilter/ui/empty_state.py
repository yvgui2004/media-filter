"""First-run / empty-result state with a film-strip mark."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPointF, QPropertyAnimation, QRectF, Qt, Signal
from PySide6.QtGui import QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .icons import line_icon
from .tokens import parse_color


class FilmStrip(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(190, 46)
        self._tokens = {"line_strong": "rgba(20,35,44,.16)", "canvas": "#F4F8FB",
                        "accent": "#2B7CA6", "accent_soft": "rgba(43,124,166,.08)"}

    def set_tokens(self, tokens: dict[str, str]) -> None:
        self._tokens = tokens
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        c = {key: parse_color(value) for key, value in self._tokens.items()}
        frame_w, frame_h, gap = 34, 46, 5
        for i in range(5):
            x = i * (frame_w + gap)
            rect = QRectF(x, 0, frame_w, frame_h)
            active = i == 2
            p.setPen(QPen(c["accent"] if active else c["line_strong"], 1))
            p.setBrush(c["accent_soft"] if active else c["canvas"])
            p.drawRoundedRect(rect, 5, 5)
            if active:
                cx, cy = rect.center().x(), rect.center().y()
                triangle = QPolygonF([
                    QPointF(cx - 3, cy - 6),
                    QPointF(cx - 3, cy + 6),
                    QPointF(cx + 7, cy),
                ])
                p.setPen(Qt.NoPen)
                p.setBrush(c["accent"])
                p.drawPolygon(triangle)
        p.end()


class EmptyState(QWidget):
    primaryClicked = Signal()
    linkClicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tokens = {
            "accent": "#2B7CA6",
            "on_accent": "#FFFFFF",
        }
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(0)
        layout.addStretch(1)

        strip_row = QHBoxLayout()
        strip_row.addStretch(1)
        self._film = FilmStrip()
        strip_row.addWidget(self._film)
        strip_row.addStretch(1)
        layout.addLayout(strip_row)
        layout.addSpacing(24)

        self._title = QLabel()
        self._title.setObjectName("EmptyTitle")
        self._title.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._title)
        layout.addSpacing(8)

        self._body = QLabel()
        self._body.setObjectName("EmptyBody")
        self._body.setAlignment(Qt.AlignCenter)
        self._body.setWordWrap(True)
        self._body.setFixedWidth(400)
        body_row = QHBoxLayout()
        body_row.addStretch(1)
        body_row.addWidget(self._body)
        body_row.addStretch(1)
        layout.addLayout(body_row)
        layout.addSpacing(22)

        actions = QHBoxLayout()
        actions.setSpacing(14)
        actions.addStretch(1)
        self._primary = QPushButton()
        self._primary.setProperty("variant", "primary")
        self._primary.setFixedHeight(36)
        self._primary.setCursor(Qt.PointingHandCursor)
        self._primary.clicked.connect(self.primaryClicked)
        actions.addWidget(self._primary)

        self._link = QPushButton()
        self._link.setObjectName("LinkButton")
        self._link.setCursor(Qt.PointingHandCursor)
        self._link.clicked.connect(self.linkClicked)
        actions.addWidget(self._link)
        actions.addStretch(1)
        layout.addLayout(actions)
        layout.addStretch(1)

        self._faded = False
        self._primary_icon = "folder"
        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(1.0)
        self.setGraphicsEffect(self._effect)

    def set_tokens(self, tokens: dict[str, str]) -> None:
        self._tokens = tokens
        self._film.set_tokens(tokens)
        self._primary.setIcon(line_icon(self._primary_icon, tokens["on_accent"], 15))

    def set_content(self, title: str, body: str, primary: str,
                    link: str = "", link_tip: str = "",
                    primary_icon: str = "folder") -> None:
        self._title.setText(title)
        self._body.setText(body)
        self._primary.setText(primary)
        self._primary_icon = primary_icon
        self._primary.setIcon(
            line_icon(primary_icon, self._tokens["on_accent"], 15)
        )
        self._link.setVisible(bool(link))
        if link:
            metrics = self._link.fontMetrics()
            self._link.setText(metrics.elidedText(link, Qt.ElideMiddle, 340))
            self._link.setToolTip(link_tip or link)

    def showEvent(self, event):
        super().showEvent(event)
        if self._faded:
            return
        self._faded = True
        self._effect.setOpacity(0.0)
        anim = QPropertyAnimation(self._effect, b"opacity", self)
        anim.setDuration(180)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start(QPropertyAnimation.DeleteWhenStopped)