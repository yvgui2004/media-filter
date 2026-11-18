"""Filter-strip dropdown: painted 34px field + rounded menu card.

Closed form (option 1C): white surface, 1px hairline border, 8px radius,
muted prefix label, value, chevron. The popup is a soft-shadowed card with
36px rows, an accent-soft current row and a check. Thread counts use the
4x8 number grid (option 2C) so 1-32 stays a single click away.

Keyboard: Up/Down/Enter/Space opens; arrows move; Enter/Space commits;
Esc closes. Clicking outside closes without replaying the click.
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEvent, QModelIndex, QPersistentModelIndex, QPoint, QPointF, QRectF,
    QSize, Qt, QTimer, Signal,
)
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QGuiApplication, QMouseEvent, QPainter,
    QPainterPath, QPen,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QListWidget, QListWidgetItem, QSizePolicy,
    QStyle, QStyledItemDelegate, QStyleOptionViewItem, QVBoxLayout, QWidget,
)

from .tokens import LIGHT, parse_color

FIELD_HEIGHT = 34
FIELD_RADIUS = 8
ROW_HEIGHT = 36
CARD_RADIUS = 10
SHADOW = 12
VISIBLE_ROWS = 8
MIN_POPUP_WIDTH = 196
GRID_COLS = 4
CELL_W, CELL_H, CELL_GAP = 46, 30, 4


class _MenuDelegate(QStyledItemDelegate):
    """Paints a 36px option row: hover tint, accent-soft current row, check."""

    def __init__(self, tokens: dict[str, str], parent: QWidget) -> None:
        super().__init__(parent)
        self._tokens = tokens

    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QSize:
        return QSize(option.rect.width(), ROW_HEIGHT)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        tokens = self._tokens
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = getattr(self.parent(), "hover_row", -1) == index.row()
        rect = QRectF(option.rect)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if selected or hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            key = "accent_soft" if selected else "row_hover"
            painter.setBrush(parse_color(tokens[key]))
            painter.drawRoundedRect(rect.adjusted(0, 1, 0, -1), 8, 8)

        font = QFont(option.font)
        font.setPixelSize(13)
        font.setWeight(QFont.Weight.Medium if selected else QFont.Weight.Normal)
        painter.setFont(font)
        painter.setPen(parse_color(tokens["accent"] if selected else tokens["ink"]))
        metrics = QFontMetrics(font)
        text_rect = rect.adjusted(10, 0, -34, 0)
        label = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        text = metrics.elidedText(
            label, Qt.TextElideMode.ElideRight, max(0, int(text_rect.width()))
        )
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            text,
        )

        if selected:
            cx, cy = rect.right() - 16, rect.center().y()
            painter.setPen(
                QPen(
                    parse_color(tokens["accent"]),
                    1.8,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin,
                )
            )
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawLine(QPointF(cx - 5, cy + 1), QPointF(cx - 1, cy + 5))
            painter.drawLine(QPointF(cx - 1, cy + 5), QPointF(cx + 6, cy - 4))
        painter.restore()


class _MenuList(QListWidget):
    """Option list inside the popup card; tracks hover for the delegate."""

    chosen = Signal(int)

    def __init__(
        self, items: list[str], current: int, tokens: dict[str, str]
    ) -> None:
        super().__init__()
        self.hover_row = -1
        self.setObjectName("MenuList")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setUniformItemSizes(True)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setItemDelegate(_MenuDelegate(tokens, self))
        self.setStyleSheet(
            "QListWidget { background: transparent; border: none; outline: none; }"
            "QListWidget::item { background: transparent; border: none; }"
            "QScrollBar:vertical { background: transparent; width: 6px;"
            " margin: 2px 1px; }"
            "QScrollBar::handle:vertical { background: "
            f"{tokens['scroll']}; border-radius: 3px; min-height: 24px; }}"
            "QScrollBar::add-line, QScrollBar::sub-line { height: 0; }"
            "QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }"
        )
        for text in items:
            item = QListWidgetItem(text)
            item.setSizeHint(QSize(10, ROW_HEIGHT))
            self.addItem(item)
        if 0 <= current < self.count():
            self.setCurrentRow(current)
        self.itemClicked.connect(self._pick)

    def _pick(self, item: QListWidgetItem) -> None:
        self.chosen.emit(self.row(item))

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        row = self.indexAt(event.position().toPoint()).row()
        if row != self.hover_row:
            self.hover_row = row
            self.viewport().update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        if self.hover_row != -1:
            self.hover_row = -1
            self.viewport().update()
        super().leaveEvent(event)

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            if self.currentRow() >= 0:
                self.chosen.emit(self.currentRow())
            event.accept()
            return
        if key == Qt.Key.Key_Escape:
            self.window().close()
            event.accept()
            return
        super().keyPressEvent(event)


class _NumberGrid(QWidget):
    """4x8 grid of 1..32 for the thread-count field."""

    chosen = Signal(int)

    def __init__(self, count: int, current: int, tokens: dict[str, str]) -> None:
        super().__init__()
        self._count = count
        self._tokens = tokens
        self._selected = current
        self._cursor = current if current >= 0 else 0
        self._hover = -1
        rows = (count + GRID_COLS - 1) // GRID_COLS
        self.setFixedSize(
            GRID_COLS * CELL_W + (GRID_COLS - 1) * CELL_GAP,
            rows * CELL_H + (rows - 1) * CELL_GAP,
        )
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _cell_rect(self, index: int) -> QRectF:
        row, col = divmod(index, GRID_COLS)
        return QRectF(
            col * (CELL_W + CELL_GAP),
            row * (CELL_H + CELL_GAP),
            CELL_W,
            CELL_H,
        )

    def _index_at(self, pos: QPoint) -> int:
        point = QPointF(pos)
        for i in range(self._count):
            if self._cell_rect(i).contains(point):
                return i
        return -1

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        tokens = self._tokens
        for i in range(self._count):
            rect = self._cell_rect(i)
            selected = i == self._selected
            if selected or i == self._hover:
                painter.setPen(Qt.PenStyle.NoPen)
                key = "accent_soft" if selected else "row_hover"
                painter.setBrush(parse_color(tokens[key]))
                painter.drawRoundedRect(rect, 6, 6)
            font = QFont(self.font())
            font.setPixelSize(13)
            font.setWeight(
                QFont.Weight.DemiBold if selected else QFont.Weight.Normal
            )
            painter.setFont(font)
            painter.setPen(
                parse_color(tokens["accent"] if selected else tokens["ink"])
            )
            painter.drawText(
                rect, int(Qt.AlignmentFlag.AlignCenter), str(i + 1)
            )
            if self.hasFocus() and i == self._cursor and not selected:
                painter.setPen(QPen(parse_color(tokens["accent"]), 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(
                    rect.adjusted(0.5, 0.5, -0.5, -0.5), 6, 6
                )
        painter.end()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        index = self._index_at(event.position().toPoint())
        if index != self._hover:
            self._hover = index
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        if self._hover != -1:
            self._hover = -1
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            index = self._index_at(event.position().toPoint())
            if index >= 0:
                self.chosen.emit(index)
                event.accept()
                return
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.chosen.emit(self._cursor)
            event.accept()
            return
        if key == Qt.Key.Key_Escape:
            self.window().close()
            event.accept()
            return
        if key == Qt.Key.Key_Left:
            cursor = max(0, self._cursor - 1)
        elif key == Qt.Key.Key_Right:
            cursor = min(self._count - 1, self._cursor + 1)
        elif key == Qt.Key.Key_Up:
            cursor = max(0, self._cursor - GRID_COLS)
        elif key == Qt.Key.Key_Down:
            cursor = min(self._count - 1, self._cursor + GRID_COLS)
        elif key == Qt.Key.Key_Home:
            cursor = 0
        elif key == Qt.Key.Key_End:
            cursor = self._count - 1
        else:
            super().keyPressEvent(event)
            return
        if cursor != self._cursor:
            self._cursor = cursor
            self.update()
        event.accept()


class _MenuPopup(QWidget):
    """Frameless popup card; owns either a list or the number grid."""

    selected = Signal(int)
    closed = Signal()

    def __init__(
        self,
        items: list[str],
        current: int,
        tokens: dict[str, str],
        anchor_width: int,
        grid: bool = False,
        min_width: int = MIN_POPUP_WIDTH,
        width_override: int | None = None,
    ) -> None:
        super().__init__(
            None,
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoMouseReplay, True)
        self._tokens = tokens
        self._dark = parse_color(tokens["surface"]).lightness() < 128
        self._list: _MenuList | None = None
        self._grid: _NumberGrid | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(SHADOW, SHADOW, SHADOW, SHADOW)
        outer.setSpacing(0)

        card = QFrame(self)
        card.setObjectName("MenuCard")
        card.setStyleSheet(
            f"QFrame#MenuCard {{ background: {tokens['surface']}; "
            f"border: 1px solid {tokens['line_strong']}; "
            f"border-radius: {CARD_RADIUS}px; }}"
        )
        outer.addWidget(card)

        inner = QVBoxLayout(card)
        if grid:
            inner.setContentsMargins(8, 8, 8, 8)
            self._grid = _NumberGrid(len(items), current, tokens)
            self._grid.chosen.connect(self._pick)
            inner.addWidget(self._grid)
            card_w = self._grid.width() + 16
            card_h = self._grid.height() + 16
        else:
            inner.setContentsMargins(6, 6, 6, 6)
            card_w = width_override or max(anchor_width, min_width)
            rows = min(len(items), VISIBLE_ROWS)
            self._list = _MenuList(items, current, tokens)
            self._list.setFixedSize(card_w - 12, rows * ROW_HEIGHT)
            self._list.chosen.connect(self._pick)
            inner.addWidget(self._list)
            card_h = self._list.height() + 12

        self._card_w = card_w
        self._card_h = card_h
        self.setFixedSize(card_w + SHADOW * 2, card_h + SHADOW * 2)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        layers = ((10, 25), (6, 35), (3, 45)) if self._dark else (
            (10, 9), (6, 14), (3, 20)
        )
        base = QColor(0, 0, 0) if self._dark else QColor(20, 35, 44)
        for spread, alpha in layers:
            color = QColor(base)
            color.setAlpha(alpha)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(
                QRectF(
                    SHADOW - spread / 2,
                    SHADOW - spread / 3 + 3,
                    self._card_w + spread,
                    self._card_h + spread,
                ),
                CARD_RADIUS + spread / 3,
                CARD_RADIUS + spread / 3,
            )
        painter.end()

    def show_at(self, anchor: QWidget) -> None:
        origin = anchor.mapToGlobal(QPoint(0, 0))
        screen = QGuiApplication.screenAt(
            anchor.mapToGlobal(QPoint(anchor.width() // 2, anchor.height() // 2))
        ) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        below = origin.y() + anchor.height() + 6
        above = origin.y() - 6 - self._card_h
        card_y = below if below + self._card_h <= area.bottom() + 1 else above
        card_x = max(
            area.left(), min(origin.x(), area.right() - self._card_w + 1)
        )
        card_y = max(
            area.top(), min(card_y, area.bottom() - self._card_h + 1)
        )
        self.move(card_x - SHADOW, card_y - SHADOW)
        self.show()
        if self._list is not None:
            self._list.setFocus(Qt.FocusReason.PopupFocusReason)
            item = self._list.currentItem()
            if item is not None:
                self._list.scrollToItem(
                    item, QAbstractItemView.ScrollHint.EnsureVisible
                )
        elif self._grid is not None:
            self._grid.setFocus(Qt.FocusReason.PopupFocusReason)

    def _pick(self, index: int) -> None:
        self.selected.emit(index)
        self.close()

    def hideEvent(self, event) -> None:
        self.closed.emit()
        super().hideEvent(event)


class SelectField(QWidget):
    """Painted dropdown with QComboBox-like value API."""

    currentIndexChanged = Signal(int)

    def __init__(self, label: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._label = label
        self._items: list[tuple[str, object]] = []
        self._index = -1
        self._tokens: dict[str, str] = LIGHT
        self._hover = False
        self._open = False
        self._grid = False
        self._opened_by_mouse = False
        self._popup: _MenuPopup | None = None
        self._suppress_open = False
        self._suppress_timer = QTimer(self)
        self._suppress_timer.setSingleShot(True)
        self._suppress_timer.setInterval(220)
        self._suppress_timer.timeout.connect(self._clear_suppress)
        self._min_popup_width = MIN_POPUP_WIDTH
        self._popup_width: int | None = None
        self._a11y_label = ""
        self.setFixedHeight(FIELD_HEIGHT)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._sync_a11y()

    # -- theming ---------------------------------------------------------

    def set_tokens(self, tokens: dict[str, str]) -> None:
        self._tokens = tokens
        self.update()

    def setLabel(self, text: str) -> None:
        self._label = text
        self.update()
        self._sync_a11y()

    def label(self) -> str:
        return self._label

    def set_number_grid(self, enabled: bool) -> None:
        self._grid = enabled

    def set_popup_min_width(self, width: int) -> None:
        self._min_popup_width = width

    def set_popup_width(self, width: int) -> None:
        """Pin the popup card width (used by wide dialog fields)."""
        self._popup_width = width

    def set_accessible_label(self, text: str) -> None:
        self._a11y_label = text
        self._sync_a11y()

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt name)
        """Preferred width for the rendered label + value + chevron.

        The filter strip pins narrow widths for Chinese; longer translations
        (e.g. "Threads") use this hint to widen only when needed.
        """
        label_width = 12.0
        if self._label:
            label_font = QFont(self.font())
            label_font.setPixelSize(11)
            label_font.setWeight(QFont.Weight.Medium)
            label_width = (
                11 + QFontMetrics(label_font).horizontalAdvance(self._label) + 12
            )
        value_font = QFont(self.font())
        value_font.setPixelSize(13)
        value_font.setWeight(QFont.Weight.Medium)
        value_width = QFontMetrics(value_font).horizontalAdvance(self.currentText())
        return QSize(int(label_width + value_width + 36), FIELD_HEIGHT)

    # -- value API (QComboBox subset) ------------------------------------

    def addItem(self, text: str, data: object = None) -> None:
        self._items.append((text, data))
        if self._index < 0:
            self._index = 0
        self.update()
        self._sync_a11y()

    def addItems(self, texts) -> None:
        for text in texts:
            self._items.append((text, None))
            if self._index < 0:
                self._index = 0
        self.update()
        self._sync_a11y()

    def clear(self) -> None:
        self._items.clear()
        self._index = -1
        self.update()
        self._sync_a11y()

    def count(self) -> int:
        return len(self._items)

    def currentIndex(self) -> int:
        return self._index

    def currentText(self) -> str:
        if 0 <= self._index < len(self._items):
            return self._items[self._index][0]
        return ""

    def currentData(self) -> object:
        if 0 <= self._index < len(self._items):
            return self._items[self._index][1]
        return None

    def findText(self, text: str) -> int:
        for i, (item_text, _data) in enumerate(self._items):
            if item_text == text:
                return i
        return -1

    def findData(self, data: object) -> int:
        for i, (_text, item_data) in enumerate(self._items):
            if item_data == data:
                return i
        return -1

    def setCurrentIndex(self, index: int) -> None:
        if index < 0 or index >= len(self._items):
            index = -1
        if index == self._index:
            self.update()
            return
        self._index = index
        self.update()
        self._sync_a11y()
        if not self.signalsBlocked():
            self.currentIndexChanged.emit(index)

    def setCurrentText(self, text: str) -> None:
        index = self.findText(text)
        if index >= 0:
            self.setCurrentIndex(index)

    def _sync_a11y(self) -> None:
        label = self._a11y_label or self._label
        text = f"{label} {self.currentText()}".strip() or "Select"
        self.setAccessibleName(text)

    # -- painting --------------------------------------------------------

    def paintEvent(self, event) -> None:
        tokens = self._tokens
        enabled = self.isEnabled()
        focused = self.hasFocus()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        if enabled and (self._open or focused):
            border = tokens["accent"]
        elif enabled and self._hover:
            border = tokens["ink_3"]
        elif enabled:
            border = tokens["line_strong"]
        else:
            border = tokens["line"]
        ring = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(parse_color(border), 1))
        painter.setBrush(
            parse_color(tokens["surface"] if enabled else tokens["canvas"])
        )
        painter.drawRoundedRect(ring, FIELD_RADIUS, FIELD_RADIUS)

        text_x = 12.0
        if self._label:
            label_font = QFont(self.font())
            label_font.setPixelSize(11)
            label_font.setWeight(QFont.Weight.Medium)
            painter.setFont(label_font)
            painter.setPen(parse_color(tokens["ink_3"]))
            metrics = QFontMetrics(label_font)
            painter.drawText(
                QRectF(11, 0, metrics.horizontalAdvance(self._label), self.height()),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                self._label,
            )
            text_x = 11 + metrics.horizontalAdvance(self._label) + 12

        value_font = QFont(self.font())
        value_font.setPixelSize(13)
        value_font.setWeight(QFont.Weight.Medium)
        painter.setFont(value_font)
        painter.setPen(parse_color(tokens["ink"] if enabled else tokens["ink_3"]))
        metrics = QFontMetrics(value_font)
        width = self.width() - text_x - 30
        value = metrics.elidedText(
            self.currentText(), Qt.TextElideMode.ElideRight, max(0, int(width))
        )
        painter.drawText(
            QRectF(text_x, 0, width, self.height()),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            value,
        )

        chevron_color = tokens["accent"] if enabled and (self._open or focused) else tokens["ink_3"]
        center = QPointF(self.width() - 16, self.height() / 2 + 0.5)
        path = QPainterPath()
        path.moveTo(center.x() - 4, center.y() - 1.5)
        path.lineTo(center.x(), center.y() + 2)
        path.lineTo(center.x() + 4, center.y() - 1.5)
        painter.setPen(
            QPen(
                parse_color(chevron_color),
                1.5,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.end()

    # -- interaction -----------------------------------------------------

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def focusInEvent(self, event) -> None:
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        self.update()
        super().focusOutEvent(event)

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.Type.EnabledChange:
            self.update()
        super().changeEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            if self._suppress_open:
                # The press that closed the menu is replayed onto the field
                # by Qt; swallow it so the second click only retracts.
                self._suppress_open = False
                event.accept()
                return
            if self._open and self._popup is not None:
                self._popup.close()
                event.accept()
                return
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self._opened_by_mouse = True
            self.open_popup()
            event.accept()
            return
        super().mousePressEvent(event)

    def _clear_suppress(self) -> None:
        self._suppress_open = False

    def keyPressEvent(self, event) -> None:
        if event.key() in (
            Qt.Key.Key_Down,
            Qt.Key.Key_Up,
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
            Qt.Key.Key_Space,
        ):
            self._opened_by_mouse = False
            self.open_popup()
            event.accept()
            return
        super().keyPressEvent(event)

    def open_popup(self) -> None:
        if self._popup is not None or not self._items or not self.isEnabled():
            return
        popup = _MenuPopup(
            [text for text, _data in self._items],
            self._index,
            self._tokens,
            self.width(),
            grid=self._grid,
            min_width=self._min_popup_width,
            width_override=self._popup_width,
        )
        popup.selected.connect(self._choose)
        popup.closed.connect(self._popup_closed)
        self._popup = popup
        self._open = True
        self.update()
        popup.show_at(self)

    def _choose(self, index: int) -> None:
        self.setCurrentIndex(index)
        if self._opened_by_mouse:
            self.clearFocus()
        else:
            self.setFocus(Qt.FocusReason.OtherFocusReason)

    def _popup_closed(self) -> None:
        self._suppress_open = True
        self._suppress_timer.start()
        popup = self._popup
        self._popup = None
        self._open = False
        if self._opened_by_mouse:
            self.clearFocus()
        self.update()
        if popup is not None:
            popup.deleteLater()