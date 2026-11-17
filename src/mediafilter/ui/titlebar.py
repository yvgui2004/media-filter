"""Frameless window chrome: brand row, draggable area, window buttons."""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QFont, QFontMetrics, QIcon, QPainter
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QHBoxLayout,
    QToolButton,
    QWidget,
)

from .icons import line_icon


class FolderChip(QAbstractButton):
    """Rounded chip showing the current folder name and its parent path."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(32)
        self.setMaximumWidth(300)
        self.setMinimumWidth(120)
        self._name = ""
        self._path = ""
        self._icon = line_icon("folder", "#64757F", 15)
        self._tokens = {
            "surface": "#FFFFFF",
            "canvas": "#F4F8FB",
            "ink": "#14232C",
            "ink_2": "#465A66",
            "ink_3": "#64757F",
            "line": "rgba(20,35,44,0.09)",
            "line_strong": "rgba(20,35,44,0.16)",
        }
        self._hover = False

    def set_folder(self, name: str, path: str) -> None:
        self._name = name or ""
        self._path = path or ""
        self.setToolTip(path or name)
        self.updateGeometry()
        self.update()

    def set_tokens(self, tokens: dict[str, str]) -> None:
        self._tokens = tokens
        self._icon = line_icon("folder", tokens["ink_3"], 15)
        self.update()

    def sizeHint(self) -> QSize:
        name_w = QFontMetrics(self._name_font()).horizontalAdvance(self._name)
        path_w = QFontMetrics(self._path_font()).horizontalAdvance(self._path)
        return QSize(min(220, 10 + 15 + 8 + name_w + (8 + path_w if self._path else 0) + 12), 32)

    def _name_font(self) -> QFont:
        f = QFont(self.font())
        f.setPixelSize(12)
        f.setWeight(QFont.DemiBold)
        return f

    def _path_font(self) -> QFont:
        f = QFont(self.font())
        f.setPixelSize(11)
        return f

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        from .tokens import parse_color

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect().adjusted(0, 0, -1, -1)
        p.setPen(parse_color(self._tokens["line_strong"] if self._hover else self._tokens["line"]))
        p.setBrush(parse_color(self._tokens["surface"]))
        p.drawRoundedRect(rect, 8, 8)

        icon_rect = QRect(10, (self.height() - 15) // 2, 15, 15)
        self._icon.paint(p, icon_rect, Qt.AlignCenter)

        x = 33
        fm_name = QFontMetrics(self._name_font())
        fm_path = QFontMetrics(self._path_font())
        right_pad = 12
        avail_total = max(0, self.width() - x - right_pad)

        path_text = ""
        if self._path:
            path_avail = max(0, min(avail_total // 2, fm_path.horizontalAdvance(self._path)))
            path_text = fm_path.elidedText(self._path, Qt.ElideMiddle, path_avail)
        path_w = fm_path.horizontalAdvance(path_text)
        name_avail = max(0, avail_total - (path_w + 8 if path_text else 0))
        name = fm_name.elidedText(self._name, Qt.ElideRight, name_avail)

        p.setFont(self._name_font())
        p.setPen(parse_color(self._tokens["ink"]))
        p.drawText(QRect(x, 0, name_avail, self.height()), Qt.AlignVCenter | Qt.AlignLeft, name)
        x += fm_name.horizontalAdvance(name) + 8

        if path_text:
            p.setFont(self._path_font())
            p.setPen(parse_color(self._tokens["ink_3"]))
            avail = self.width() - x - right_pad
            path = fm_path.elidedText(self._path, Qt.ElideMiddle, max(0, avail))
            p.drawText(QRect(x, 0, avail, self.height()), Qt.AlignVCenter | Qt.AlignLeft, path)
        p.end()


class _WindowButton(QToolButton):
    def __init__(self, normal: QIcon, hover: QIcon | None = None, close: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("CloseButton" if close else "WindowButton")
        self.setCursor(Qt.ArrowCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFixedSize(46, 56)
        self.setIconSize(QSize(16, 16))
        self._normal = normal
        self._hover = hover
        self.setIcon(normal)

    def set_icons(self, normal: QIcon, hover: QIcon | None = None) -> None:
        self._normal = normal
        self._hover = hover
        if not self.underMouse():
            self.setIcon(normal)

    def enterEvent(self, event):
        if self._hover is not None:
            self.setIcon(self._hover)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setIcon(self._normal)
        super().leaveEvent(event)


class TitleBar(QWidget):
    minimizeRequested = Signal()
    maximizeRequested = Signal()
    closeRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TitleBar")
        self.setFixedHeight(56)
        self.setAttribute(Qt.WA_StyledBackground, True)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        content = QWidget()
        content.setObjectName("TitleBarContent")
        self.layout_ = QHBoxLayout(content)
        self.layout_.setContentsMargins(16, 0, 12, 0)
        self.layout_.setSpacing(10)
        outer.addWidget(content, 1)

        controls = QWidget()
        controls.setObjectName("WindowControls")
        c_layout = QHBoxLayout(controls)
        c_layout.setContentsMargins(0, 0, 0, 0)
        c_layout.setSpacing(0)

        self._min_btn = _WindowButton(line_icon("minimize", "#465A66"))
        self._max_btn = _WindowButton(line_icon("maximize", "#465A66"))
        self._close_btn = _WindowButton(
            line_icon("close", "#465A66"),
            line_icon("close", "#FFFFFF"),
            close=True,
        )
        for b in (self._min_btn, self._max_btn, self._close_btn):
            c_layout.addWidget(b)
        outer.addWidget(controls, 0)

        self._min_btn.clicked.connect(self.minimizeRequested)
        self._max_btn.clicked.connect(self.maximizeRequested)
        self._close_btn.clicked.connect(self.closeRequested)

        self._drag_origin = None
        self._maximized = False
        self._min_text = ""
        self._max_text = ""
        self._restore_text = ""
        self._close_text = ""
        self._tokens = {
            "ink_2": "#465A66",
        }

    # -- content ---------------------------------------------------------

    def add_widget(self, widget) -> None:
        self.layout_.addWidget(widget)

    def add_stretch(self) -> None:
        self.layout_.addStretch(1)

    # -- theme -----------------------------------------------------------

    def set_tokens(self, tokens: dict[str, str]) -> None:
        self._tokens = tokens
        color = tokens["ink_2"]
        self._min_btn.set_icons(line_icon("minimize", color))
        self._refresh_max_icon()
        self._close_btn.set_icons(
            line_icon("close", color), line_icon("close", "#FFFFFF")
        )

    def set_maximized(self, maximized: bool) -> None:
        self._maximized = maximized
        self._refresh_max_icon()

    def set_button_texts(self, minimize: str, maximize: str,
                         restore: str, close: str) -> None:
        self._min_text = minimize
        self._max_text = maximize
        self._restore_text = restore
        self._close_text = close
        self._min_btn.setToolTip(minimize)
        self._min_btn.setAccessibleName(minimize)
        self._close_btn.setToolTip(close)
        self._close_btn.setAccessibleName(close)
        self._refresh_max_icon()

    def _refresh_max_icon(self) -> None:
        name = "restore" if self._maximized else "maximize"
        self._max_btn.set_icons(line_icon(name, self._tokens["ink_2"]))
        label = self._restore_text if self._maximized else self._max_text
        self._max_btn.setToolTip(label)
        self._max_btn.setAccessibleName(label)

    # -- window behaviour ------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_origin = event.globalPosition().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_origin is None or not (event.buttons() & Qt.LeftButton):
            return
        if (event.globalPosition().toPoint() - self._drag_origin).manhattanLength() < QApplication.startDragDistance():
            return
        self._drag_origin = None
        handle = self.window().windowHandle()
        if handle is not None:
            handle.startSystemMove()
        event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_origin = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.maximizeRequested.emit()
        super().mouseDoubleClickEvent(event)