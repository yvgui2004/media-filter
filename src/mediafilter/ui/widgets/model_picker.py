"""Searchable model picker for the recognition settings dialog.

The collapsed field mirrors ``SelectField`` (44px, surface, hairline border,
accent focus).  The popup is a rounded card with a search row, grouped model
list (image / unknown / text), capability badges and a manual-ID fallback.
All colours come from the active Light Table tokens.
"""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import (
    QEvent, QModelIndex, QPersistentModelIndex, QPoint, QPointF, QRect,
    QRectF, QSize, Qt, QTimer, Signal,
)
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QGuiApplication, QMouseEvent,
    QPainter, QPainterPath, QPen,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QSizePolicy, QStyledItemDelegate,
    QStyleOptionViewItem, QToolButton, QVBoxLayout, QWidget,
)

from ...core.cloud_models import (
    IMAGE, TEXT, UNKNOWN, VERIFIED_IMAGE, ModelInfo,
)
from ..icons import line_icon
from ..tokens import LIGHT, parse_color

FIELD_HEIGHT = 44
FIELD_RADIUS = 8
ROW_HEIGHT = 52
GROUP_HEIGHT = 28
CARD_RADIUS = 10
SHADOW = 14
MIN_POPUP_WIDTH = 520
LIST_HEIGHT = 280

# The tabbed settings page enlarges the model field and its popup by 1.15x.
_COMPACT_SCALE = 1.15


def _px(value: float, compact: bool) -> int:
    return int(round(value * _COMPACT_SCALE)) if compact else int(round(value))


def _t(tr, key: str, fallback: str) -> str:
    text = tr(key)
    return fallback if text == key else text


def _with_alpha(value: str, alpha: int) -> QColor:
    color = parse_color(value)
    color.setAlpha(alpha)
    return color


def _badge_spec(
    tokens: dict[str, str], tr, model: ModelInfo
) -> tuple[str, QColor, QColor]:
    if model.capability in (IMAGE, VERIFIED_IMAGE):
        return (
            _t(tr, "settings.badge_image", "图像"),
            parse_color(tokens["green"]),
            _with_alpha(tokens["green"], 24),
        )
    if model.capability == TEXT:
        return (
            _t(tr, "settings.badge_text", "仅文本"),
            parse_color(tokens["red"]),
            _with_alpha(tokens["red"], 22),
        )
    if model.is_custom:
        return (
            _t(tr, "settings.badge_custom", "自定义"),
            parse_color(tokens["accent"]),
            _with_alpha(tokens["accent"], 24),
        )
    return (
        _t(tr, "settings.badge_unknown", "未验证"),
        parse_color(tokens["ink_3"]),
        _with_alpha(tokens["ink_3"], 20),
    )


def _badge_width(font: QFont, text: str, compact: bool = False) -> int:
    return max(
        _px(34, compact),
        QFontMetrics(font).horizontalAdvance(text) + _px(14, compact),
    )


def _draw_badge(
    painter: QPainter,
    rect: QRectF,
    text: str,
    foreground: QColor,
    background: QColor,
    font: QFont,
    compact: bool = False,
) -> None:
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(background)
    painter.drawRoundedRect(rect, _px(5, compact), _px(5, compact))
    painter.setFont(font)
    painter.setPen(foreground)
    painter.drawText(
        rect, int(Qt.AlignmentFlag.AlignCenter), text
    )


class _ModelDelegate(QStyledItemDelegate):
    """Group headers / 52px model rows with radio, name, id, context, badge."""

    def __init__(
        self,
        tokens: dict[str, str],
        tr,
        parent: QWidget,
        compact: bool = False,
    ) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._tr = tr
        self._compact = compact
        self._k = _COMPACT_SCALE if compact else 1.0

    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QSize:
        data = index.data(Qt.ItemDataRole.UserRole)
        height = GROUP_HEIGHT if isinstance(data, dict) else ROW_HEIGHT
        return QSize(option.rect.width(), _px(height, self._compact))

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        tokens = self._tokens
        data = index.data(Qt.ItemDataRole.UserRole)
        rect = QRectF(option.rect)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        k = self._k

        if isinstance(data, dict):
            font = QFont(option.font)
            font.setPixelSize(_px(11, self._compact))
            font.setWeight(QFont.Weight.DemiBold)
            painter.setFont(font)
            painter.setPen(parse_color(tokens["ink_3"]))
            painter.drawText(
                rect.adjusted(12 * k, 0, -12 * k, 0),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                str(data.get("label") or ""),
            )
            hint = str(data.get("hint") or "")
            if hint:
                painter.drawText(
                    rect.adjusted(12 * k, 0, -12 * k, 0),
                    int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                    hint,
                )
            painter.restore()
            return

        model = data if isinstance(data, ModelInfo) else None
        if model is None:
            painter.restore()
            return

        list_widget = self.parent()
        selected_id = getattr(list_widget, "selected_id", "")
        current_row = getattr(list_widget, "current_row", -1)
        hover_row = getattr(list_widget, "hover_row", -1)
        selected = model.id == selected_id
        current = index.row() == current_row
        hovered = index.row() == hover_row
        row_rect = rect.adjusted(0, 2 * k, 0, -2 * k)
        if selected or current or hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            key = "accent_soft" if selected else "row_hover"
            painter.setBrush(parse_color(tokens[key]))
            painter.drawRoundedRect(row_rect, 8 * k, 8 * k)

        # Radio marker.
        center = QPointF(18 * k, row_rect.center().y())
        if selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(parse_color(tokens["accent"]))
            painter.drawEllipse(center, 5.5 * k, 5.5 * k)
            painter.setBrush(parse_color(tokens["on_accent"]))
            painter.drawEllipse(center, 2.2 * k, 2.2 * k)
        else:
            painter.setPen(QPen(parse_color(tokens["ink_3"]), 1.2 * k))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(center, 5.2 * k, 5.2 * k)

        font = QFont(option.font)
        font.setPixelSize(_px(13, self._compact))
        font.setWeight(QFont.Weight.Medium)
        painter.setFont(font)
        name_metrics = QFontMetrics(font)

        badge_font = QFont(option.font)
        badge_font.setPixelSize(_px(11, self._compact))
        badge_font.setWeight(QFont.Weight.Medium)
        badge_text, badge_fg, badge_bg = _badge_spec(tokens, self._tr, model)
        badge_w = _badge_width(badge_font, badge_text, self._compact)
        badge_rect = QRectF(
            row_rect.right() - 10 * k - badge_w,
            row_rect.center().y() - 9.5 * k,
            badge_w,
            19 * k,
        )

        context_rect = QRectF(
            badge_rect.left() - 52 * k,
            row_rect.center().y() - 9 * k,
            44 * k,
            18 * k,
        )
        if model.context:
            context_font = QFont(option.font)
            context_font.setPixelSize(_px(11, self._compact))
            painter.setFont(context_font)
            painter.setPen(parse_color(tokens["ink_3"]))
            painter.drawText(
                context_rect,
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                model.context,
            )

        text_left = 34.0 * k
        text_right = (
            context_rect.left() if model.context else badge_rect.left()
        ) - 10 * k
        text_width = max(0.0, text_right - text_left)

        painter.setFont(font)
        painter.setPen(parse_color(
            tokens["accent"] if selected else tokens["ink"]
        ))
        name = name_metrics.elidedText(
            model.name, Qt.TextElideMode.ElideRight, int(text_width)
        )
        painter.drawText(
            QRectF(text_left, row_rect.top() + 7 * k, text_width, 19 * k),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            name,
        )

        id_font = QFont(option.font)
        id_font.setFamilies(["Cascadia Mono", "Consolas", "Microsoft YaHei UI"])
        id_font.setPixelSize(_px(11, self._compact))
        painter.setFont(id_font)
        painter.setPen(parse_color(tokens["ink_3"]))
        id_metrics = QFontMetrics(id_font)
        model_id = id_metrics.elidedText(
            model.id, Qt.TextElideMode.ElideRight, int(text_width)
        )
        painter.drawText(
            QRectF(text_left, row_rect.top() + 27 * k, text_width, 16 * k),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            model_id,
        )

        _draw_badge(
            painter, badge_rect, badge_text, badge_fg, badge_bg, badge_font,
            self._compact,
        )
        painter.restore()


class _ModelList(QListWidget):
    """Rows are non-selectable; the popup owns keyboard current-row state."""

    picked = Signal(object)

    def __init__(
        self,
        tokens: dict[str, str],
        tr,
        parent: QWidget | None = None,
        compact: bool = False,
    ) -> None:
        super().__init__(parent)
        self.hover_row = -1
        self.current_row = -1
        self.selected_id = ""
        self._compact = compact
        self.setObjectName("ModelList")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setUniformItemSizes(False)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setItemDelegate(_ModelDelegate(tokens, tr, self, compact=compact))
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
        self.itemClicked.connect(self._pick)

    def set_rows(
        self,
        rows: list[tuple[str, object]],
        selected_id: str,
        current_row: int,
    ) -> None:
        self.clear()
        self.selected_id = selected_id
        model_rows: list[int] = []
        for kind, payload in rows:
            item = QListWidgetItem()
            if kind == "group":
                item.setData(Qt.ItemDataRole.UserRole, payload)
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                item.setSizeHint(
                    QSize(10, _px(GROUP_HEIGHT, self._compact))
                )
            else:
                item.setData(Qt.ItemDataRole.UserRole, payload)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                item.setSizeHint(QSize(10, _px(ROW_HEIGHT, self._compact)))
                model_rows.append(self.count())
            self.addItem(item)
        if not model_rows:
            self.current_row = -1
        elif current_row not in model_rows:
            self.current_row = model_rows[0]
        else:
            self.current_row = current_row
        self.viewport().update()
        self._scroll_current()

    def move_current(self, delta: int) -> None:
        rows = [
            row for row in range(self.count())
            if isinstance(
                self.item(row).data(Qt.ItemDataRole.UserRole), ModelInfo
            )
        ]
        if not rows:
            return
        try:
            index = rows.index(self.current_row)
        except ValueError:
            index = 0 if delta > 0 else len(rows) - 1
        else:
            index = max(0, min(len(rows) - 1, index + delta))
        self.current_row = rows[index]
        self.viewport().update()
        self._scroll_current()

    def _scroll_current(self) -> None:
        if 0 <= self.current_row < self.count():
            item = self.item(self.current_row)
            if item is not None:
                self.scrollToItem(
                    item, QAbstractItemView.ScrollHint.EnsureVisible
                )

    def current_model(self) -> ModelInfo | None:
        if 0 <= self.current_row < self.count():
            item = self.item(self.current_row)
            data = item.data(Qt.ItemDataRole.UserRole) if item else None
            if isinstance(data, ModelInfo):
                return data
        return None

    def _pick(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(data, ModelInfo):
            self.picked.emit(data)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        row = self.indexAt(event.position().toPoint()).row()
        item = self.item(row) if row >= 0 else None
        data = item.data(Qt.ItemDataRole.UserRole) if item else None
        row = row if isinstance(data, ModelInfo) else -1
        if row != self.hover_row:
            self.hover_row = row
            self.viewport().update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        if self.hover_row != -1:
            self.hover_row = -1
            self.viewport().update()
        super().leaveEvent(event)


class _ModelPopup(QWidget):
    """Popup card above/below the model field; keeps search focus."""

    picked = Signal(object)
    refreshRequested = Signal()
    closed = Signal()

    def __init__(
        self,
        models: list[ModelInfo],
        selected_id: str,
        tokens: dict[str, str],
        tr,
        anchor_width: int,
        compact: bool = False,
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
        self._tr = tr
        self._compact = compact
        self._k = _COMPACT_SCALE if compact else 1.0
        self._dark = parse_color(tokens["surface"]).lightness() < 128
        self._models = models
        self._selected_id = selected_id
        self._anchor: QWidget | None = None
        self._manual_visible = False
        self._loading = False
        self._error = ""
        self._card_w = max(anchor_width, _px(MIN_POPUP_WIDTH, compact))

        outer = QVBoxLayout(self)
        shadow = _px(SHADOW, compact)
        outer.setContentsMargins(shadow, shadow, shadow, shadow)
        outer.setSpacing(0)
        self._card = QFrame(self)
        self._card.setObjectName("ModelCard")
        self._card.setStyleSheet(
            f"QFrame#ModelCard {{ background: {tokens['surface']}; "
            f"border: 1px solid {tokens['line_strong']}; "
            f"border-radius: {_px(CARD_RADIUS, compact)}px; }}"
        )
        outer.addWidget(self._card)

        body = QVBoxLayout(self._card)
        margin = _px(10, compact)
        body.setContentsMargins(margin, margin, margin, margin)
        body.setSpacing(_px(8, compact))

        search_row = QHBoxLayout()
        search_row.setSpacing(_px(6, compact))
        self._search = QLineEdit()
        self._search.setObjectName("ModelSearch")
        self._search.setFixedHeight(_px(34, compact))
        self._search.setPlaceholderText(
            _t(tr, "settings.model_search", "搜索模型名或 ID")
        )
        self._search.setClearButtonEnabled(True)
        self._search.addAction(
            line_icon("search", tokens["ink_3"], _px(14, compact)),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self._search.setStyleSheet(
            f"QLineEdit#ModelSearch {{ background: {tokens['surface']}; "
            f"border: 1px solid {tokens['line_strong']}; "
            f"border-radius: {_px(8, compact)}px; "
            f"padding: 0 {_px(9, compact)}px; color: {tokens['ink']}; "
            f"font-size: {_px(13, compact)}px; }}"
            f"QLineEdit#ModelSearch:focus {{ border-color: {tokens['accent']}; }}"
            f"QLineEdit#ModelSearch::placeholder {{ color: {tokens['ink_3']}; }}"
        )
        self._search.installEventFilter(self)
        search_row.addWidget(self._search, 1)

        self._refresh = QToolButton()
        self._refresh.setProperty("variant", "icon")
        refresh_size = _px(34, compact)
        self._refresh.setFixedSize(refresh_size, refresh_size)
        self._refresh.setIconSize(QSize(_px(15, compact), _px(15, compact)))
        self._refresh.setIcon(
            line_icon("refresh", tokens["ink_3"], _px(15, compact))
        )
        self._refresh.setToolTip(_t(tr, "settings.model_refresh", "刷新模型列表"))
        self._refresh.clicked.connect(lambda: self.refreshRequested.emit())
        search_row.addWidget(self._refresh)
        body.addLayout(search_row)

        meta_row = QHBoxLayout()
        meta_margin = _px(2, compact)
        meta_row.setContentsMargins(meta_margin, 0, meta_margin, 0)
        meta_row.setSpacing(_px(8, compact))
        self._meta_left = QLabel()
        self._meta_right = QLabel()
        for label in (self._meta_left, self._meta_right):
            label.setStyleSheet(
                f"color: {tokens['ink_3']}; font-size: {_px(11, compact)}px; "
                "border: none;"
            )
        meta_row.addWidget(self._meta_left, 1)
        meta_row.addWidget(self._meta_right, 0, Qt.AlignmentFlag.AlignRight)
        body.addLayout(meta_row)

        self._list = _ModelList(tokens, tr, self._card, compact=compact)
        self._list.setFixedHeight(_px(LIST_HEIGHT, compact))
        self._list.picked.connect(self._pick)
        body.addWidget(self._list)
        self._search.textChanged.connect(self._on_search_changed)
        self._search.returnPressed.connect(self._choose_current)

        footer_row = QHBoxLayout()
        footer_margin = _px(2, compact)
        footer_row.setContentsMargins(footer_margin, 0, footer_margin, 0)
        footer_row.setSpacing(_px(8, compact))
        self._manual_link = QPushButton(
            _t(tr, "settings.model_manual", "手动输入模型 ID")
        )
        self._manual_link.setObjectName("InlineLink")
        self._manual_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self._manual_link.setStyleSheet(
            "QPushButton#InlineLink { background: transparent; border: none; "
            f"color: {tokens['accent']}; font-size: {_px(11, compact)}px; "
            "font-weight: 600; padding: 0; }"
            f"QPushButton#InlineLink:hover {{ color: {tokens['accent_strong']}; }}"
        )
        self._manual_link.clicked.connect(self._toggle_manual)
        footer_row.addWidget(self._manual_link)
        footer_row.addStretch(1)
        self._meta_hint = QLabel(
            _t(tr, "settings.model_meta_hint", "能力来自模型元数据")
        )
        self._meta_hint.setStyleSheet(
            f"color: {tokens['ink_3']}; font-size: {_px(11, compact)}px; "
            "border: none;"
        )
        footer_row.addWidget(self._meta_hint)
        body.addLayout(footer_row)

        manual_row = QHBoxLayout()
        manual_row.setSpacing(_px(6, compact))
        self._manual_input = QLineEdit()
        self._manual_input.setObjectName("FieldInput")
        self._manual_input.setFixedHeight(_px(34, compact))
        self._manual_input.setPlaceholderText(
            _t(tr, "settings.model_manual_placeholder",
               "例如 qwen3-vl-plus 或 my-lab/vision-model")
        )
        self._manual_input.returnPressed.connect(self._use_manual)
        manual_row.addWidget(self._manual_input, 1)
        self._manual_use = QPushButton(_t(tr, "settings.model_use", "使用"))
        self._manual_use.setProperty("variant", "ghost")
        self._manual_use.setFixedSize(_px(72, compact), _px(34, compact))
        self._manual_use.setCursor(Qt.CursorShape.PointingHandCursor)
        self._manual_use.clicked.connect(self._use_manual)
        manual_row.addWidget(self._manual_use)
        self._manual_row = QWidget()
        self._manual_row.setLayout(manual_row)
        self._manual_row.setVisible(False)
        body.addWidget(self._manual_row)

        self._body = body
        self._apply_geometry()
        self._reload_rows("")

    # -- geometry / painting ---------------------------------------------

    def _apply_geometry(self) -> None:
        k = self._k
        manual_extra = 42 * k if self._manual_visible else 0
        self._card_h = int(round(
            (10 + 34 + 8 + 14 + 8 + LIST_HEIGHT + 8 + 22 + 10) * k
            + manual_extra
        ))
        shadow = _px(SHADOW, self._compact)
        self.setFixedSize(
            self._card_w + shadow * 2, self._card_h + shadow * 2
        )
        if self._anchor is not None and self.isVisible():
            self._position(self._anchor)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        k = self._k
        shadow = _px(SHADOW, self._compact)
        radius = _px(CARD_RADIUS, self._compact)
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
                    shadow - spread * k / 2,
                    shadow - spread * k / 3 + 3 * k,
                    self._card_w + spread * k,
                    self._card_h + spread * k,
                ),
                radius + spread * k / 3,
                radius + spread * k / 3,
            )
        painter.end()

    def show_at(self, anchor: QWidget) -> None:
        self._anchor = anchor
        self._position(anchor)
        self.show()
        self._search.setFocus(Qt.FocusReason.PopupFocusReason)
        self._search.selectAll()

    def _position(self, anchor: QWidget) -> None:
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

    # -- data -------------------------------------------------------------

    def set_models(self, models: list[ModelInfo], selected_id: str) -> None:
        self._models = models
        self._selected_id = selected_id
        self._loading = False
        self._error = ""
        self._reload_rows(self._search.text())

    def set_loading(self, loading: bool) -> None:
        self._loading = loading
        self._refresh.setEnabled(not loading)
        if loading:
            self._error = ""
        self._reload_rows(self._search.text())

    def set_error(self, message: str) -> None:
        self._loading = False
        self._refresh.setEnabled(True)
        self._error = message
        self._reload_rows(self._search.text())

    def _reload_rows(self, query: str) -> None:
        text = query.strip().casefold()
        filtered = [
            model for model in self._models
            if not text
            or text in model.name.casefold()
            or text in model.id.casefold()
            or text in model.vendor.casefold()
        ]

        rows: list[tuple[str, object]] = []
        groups = (
            (IMAGE, "settings.group_image", "支持图像"),
            (UNKNOWN, "settings.group_unknown", "未验证"),
            (TEXT, "settings.group_text", "仅文本"),
        )
        image_count = sum(1 for m in filtered if m.capability in (IMAGE, VERIFIED_IMAGE))
        for capability, key, fallback in groups:
            group = [
                m for m in filtered
                if (m.capability in (IMAGE, VERIFIED_IMAGE) if capability == IMAGE
                    else m.capability == capability)
            ]
            if not group:
                continue
            rows.append(("group", {
                "label": _t(self._tr, key, fallback),
                "hint": str(len(group)),
            }))
            for model in group:
                rows.append(("model", model))

        current_row = -1
        if self._selected_id:
            for index, (kind, payload) in enumerate(rows):
                if kind == "model" and isinstance(payload, ModelInfo):
                    if payload.id == self._selected_id:
                        current_row = index
                        break
        self._list.set_rows(rows, self._selected_id, current_row)

        if self._loading:
            self._meta_left.setText(
                _t(self._tr, "settings.model_loading", "正在获取模型列表…")
            )
            self._meta_right.setText("")
        elif self._error:
            self._meta_left.setText(
                _t(self._tr, "settings.model_empty", "未获取到模型列表")
            )
            self._meta_right.setText(
                _t(self._tr, "settings.model_manual_hint", "可手动输入模型 ID")
            )
        elif text:
            self._meta_left.setText(
                _t(self._tr, "settings.model_searching", "搜索结果")
            )
            self._meta_right.setText(
                _t(self._tr, "settings.model_count", "{n} 个模型").format(
                    n=len(filtered)
                )
            )
        else:
            self._meta_left.setText(
                _t(self._tr, "settings.model_from_api", "来自 GET /v1/models")
            )
            self._meta_right.setText(
                _t(self._tr, "settings.model_count_image",
                   "{n} 个模型 · {m} 个支持图像").format(
                    n=len(filtered), m=image_count
                )
            )

        if not rows:
            if self._loading:
                empty = _t(
                    self._tr, "settings.model_loading", "正在获取模型列表…"
                )
            elif text:
                empty = _t(
                    self._tr, "settings.model_no_result", "没有匹配的模型"
                )
            else:
                empty = _t(
                    self._tr, "settings.model_empty", "未获取到模型列表"
                )
            self._list.addItem(self._empty_item(empty))
            self._list.current_row = -1

    def _empty_item(self, text: str) -> QListWidgetItem:
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, {"label": text, "hint": ""})
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        item.setSizeHint(QSize(10, GROUP_HEIGHT))
        return item

    # -- interaction ------------------------------------------------------

    def _pick(self, model: ModelInfo) -> None:
        self.picked.emit(model)
        self.close()

    def _on_search_changed(self, text: str) -> None:
        self._reload_rows(text)

    def _choose_current(self) -> None:
        model = self._list.current_model()
        if model is not None:
            self._pick(model)

    def _toggle_manual(self) -> None:
        self._manual_visible = not self._manual_visible
        self._manual_row.setVisible(self._manual_visible)
        self._manual_link.setText(
            _t(self._tr, "settings.model_manual_hide", "返回模型列表")
            if self._manual_visible else
            _t(self._tr, "settings.model_manual", "手动输入模型 ID")
        )
        self._apply_geometry()
        if self._manual_visible:
            self._manual_input.setFocus(Qt.FocusReason.OtherFocusReason)
        else:
            self._search.setFocus(Qt.FocusReason.OtherFocusReason)

    def _use_manual(self) -> None:
        text = self._manual_input.text().strip()
        if not text:
            self._manual_input.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        for model in self._models:
            if model.id == text or model.id.casefold() == text.casefold():
                self._pick(model)
                return
        self._pick(ModelInfo(
            id=text,
            name=text,
            vendor="custom",
            capability=UNKNOWN,
        ))

    def eventFilter(self, watched, event) -> bool:
        if watched is self._search and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Down:
                self._list.move_current(1)
                return True
            if key == Qt.Key.Key_Up:
                self._list.move_current(-1)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                model = self._list.current_model()
                if model is not None:
                    self._pick(model)
                return True
            if key == Qt.Key.Key_Escape:
                self.close()
                return True
        return super().eventFilter(watched, event)

    def hideEvent(self, event) -> None:
        self.closed.emit()
        super().hideEvent(event)


class ModelPicker(QWidget):
    """Painted model field; emits ``selected`` with a ModelInfo."""

    selected = Signal(object)
    refreshRequested = Signal()

    def __init__(
        self,
        tr,
        tokens: dict[str, str] | None = None,
        parent: QWidget | None = None,
        compact: bool = False,
    ) -> None:
        super().__init__(parent)
        self._tr = tr
        self._tokens = tokens or LIGHT
        self._compact = compact
        self._models: list[ModelInfo] = []
        self._model: ModelInfo | None = None
        self._capability_override: str | None = None
        self._loading = False
        self._error = ""
        self._hover = False
        self._open = False
        self._opened_by_mouse = False
        self._popup: _ModelPopup | None = None
        self._suppress_open = False
        self._suppress_timer = QTimer(self)
        self._suppress_timer.setSingleShot(True)
        self._suppress_timer.setInterval(220)
        self._suppress_timer.timeout.connect(self._clear_suppress)
        self.setFixedHeight(_px(FIELD_HEIGHT, compact))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._sync_a11y()

    # -- theming / data ---------------------------------------------------

    def set_tokens(self, tokens: dict[str, str]) -> None:
        self._tokens = tokens
        self.update()

    def set_tr(self, tr) -> None:
        self._tr = tr
        self._sync_a11y()

    def set_models(self, models: list[ModelInfo]) -> None:
        self._models = models
        self._loading = False
        self._error = ""
        if self._model is not None:
            current_id = self._model.id
            for model in models:
                if model.id == current_id:
                    self._model = self._apply_override(model)
                    break
            self._models = [
                self._apply_override(model)
                if model.id == current_id else model
                for model in models
            ]
        if self._popup is not None:
            self._popup.set_models(models, self._model.id if self._model else "")
        self.update()
        self._sync_a11y()

    def set_model(self, model: ModelInfo | None) -> None:
        self._model = model
        self._capability_override = None
        if self._popup is not None:
            self._popup.set_models(
                self._models, model.id if model is not None else ""
            )
        self.update()
        self._sync_a11y()

    def model(self) -> ModelInfo | None:
        return self._model

    def set_selected_capability(self, capability: str) -> None:
        self._capability_override = capability
        if self._model is not None:
            current = replace(self._model, capability=capability)
            self._model = current
            self._models = [
                replace(model, capability=capability)
                if model.id == current.id else model
                for model in self._models
            ]
        self.update()
        self._sync_a11y()

    def set_loading(self, loading: bool) -> None:
        self._loading = loading
        if loading:
            self._error = ""
        if self._popup is not None:
            self._popup.set_loading(loading)
        self.update()

    def set_error(self, message: str) -> None:
        self._loading = False
        self._error = message
        if self._popup is not None:
            self._popup.set_error(message)
        self.update()

    def _apply_override(self, model: ModelInfo) -> ModelInfo:
        if self._capability_override:
            return replace(model, capability=self._capability_override)
        return model

    def _sync_a11y(self) -> None:
        name = self._model.name if self._model else _t(
            self._tr, "settings.model_none", "选择模型"
        )
        self.setAccessibleName(
            f"{_t(self._tr, 'settings.model', '模型')} {name}"
        )

    # -- painting ---------------------------------------------------------

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
        painter.drawRoundedRect(
            ring, _px(FIELD_RADIUS, self._compact),
            _px(FIELD_RADIUS, self._compact),
        )

        k = _COMPACT_SCALE if self._compact else 1.0
        icon_size = 28 * k
        icon_rect = QRectF(
            10 * k, (self.height() - icon_size) / 2, icon_size, icon_size
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_with_alpha(tokens["accent"], 18))
        painter.drawRoundedRect(icon_rect, 7 * k, 7 * k)
        cube_size = _px(15, self._compact)
        line_icon("cube", tokens["accent"], cube_size).paint(
            painter,
            QRect(
                int(16 * k),
                int(icon_rect.center().y() - 8 * k),
                int(16 * k), int(16 * k),
            ),
        )

        model = self._model
        name_font = QFont(self.font())
        name_font.setPixelSize(
            _px(12 if self._compact else 13, self._compact)
        )
        name_font.setWeight(QFont.Weight.Medium)
        painter.setFont(name_font)
        name_metrics = QFontMetrics(name_font)

        if model is not None:
            name = model.name
            model_id = model.id
        elif self._loading:
            name = _t(self._tr, "settings.model_loading", "正在获取模型列表…")
            model_id = ""
        elif self._error:
            name = _t(self._tr, "settings.model_none", "选择模型")
            model_id = _t(
                self._tr, "settings.model_manual_hint", "可手动输入模型 ID"
            )
        else:
            name = _t(self._tr, "settings.model_none", "选择模型")
            model_id = _t(
                self._tr, "settings.model_none_hint", "从接口列表选择，或手动输入"
            )

        badge_font = QFont(self.font())
        badge_font.setPixelSize(
            _px(10 if self._compact else 11, self._compact)
        )
        badge_font.setWeight(QFont.Weight.Medium)
        badge_text = ""
        badge_fg = parse_color(tokens["ink_3"])
        badge_bg = _with_alpha(tokens["ink_3"], 20)
        badge_w = 0
        if model is not None:
            badge_text, badge_fg, badge_bg = _badge_spec(tokens, self._tr, model)
            badge_w = _badge_width(badge_font, badge_text, self._compact)

        text_left = 48.0 * k
        text_right = self.width() - 42.0 * k - (
            badge_w + 10 * k if badge_text else 0
        )
        text_width = max(0.0, text_right - text_left)
        painter.setPen(parse_color(tokens["ink"] if enabled else tokens["ink_3"]))
        name = name_metrics.elidedText(
            name, Qt.TextElideMode.ElideRight, int(text_width)
        )
        painter.drawText(
            QRectF(text_left, 6 * k, text_width, 19 * k),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            name,
        )

        id_font = QFont(self.font())
        id_font.setFamilies(["Cascadia Mono", "Consolas", "Microsoft YaHei UI"])
        id_font.setPixelSize(
            _px(10 if self._compact else 11, self._compact)
        )
        painter.setFont(id_font)
        painter.setPen(parse_color(tokens["ink_3"]))
        id_metrics = QFontMetrics(id_font)
        model_id = id_metrics.elidedText(
            model_id, Qt.TextElideMode.ElideRight, int(text_width)
        )
        painter.drawText(
            QRectF(text_left, 24 * k, text_width, 16 * k),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            model_id,
        )

        if badge_text:
            badge_rect = QRectF(
                self.width() - 38 * k - badge_w,
                (self.height() - 19 * k) / 2,
                badge_w,
                19 * k,
            )
            _draw_badge(
                painter, badge_rect, badge_text, badge_fg, badge_bg, badge_font,
                self._compact,
            )

        chevron_color = (
            tokens["accent"] if enabled and (self._open or focused)
            else tokens["ink_3"]
        )
        center = QPointF(self.width() - 17 * k, self.height() / 2 + 0.5)
        path = QPainterPath()
        if self._open:
            path.moveTo(center.x() - 4 * k, center.y() + 1.5 * k)
            path.lineTo(center.x(), center.y() - 2 * k)
            path.lineTo(center.x() + 4 * k, center.y() + 1.5 * k)
        else:
            path.moveTo(center.x() - 4 * k, center.y() - 1.5 * k)
            path.lineTo(center.x(), center.y() + 2 * k)
            path.lineTo(center.x() + 4 * k, center.y() - 1.5 * k)
        painter.setPen(
            QPen(
                parse_color(chevron_color),
                1.5 * k,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.end()

    # -- interaction ------------------------------------------------------

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
                # Replayed press from the click that closed the list; it must
                # only retract, not immediately reopen.
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
        if self._popup is not None or not self.isEnabled():
            return
        popup = _ModelPopup(
            self._models,
            self._model.id if self._model else "",
            self._tokens,
            self._tr,
            self.width(),
            compact=self._compact,
        )
        popup.picked.connect(self._choose)
        popup.refreshRequested.connect(self.refreshRequested)
        popup.closed.connect(self._popup_closed)
        if self._loading:
            popup.set_loading(True)
        elif self._error:
            popup.set_error(self._error)
        self._popup = popup
        self._open = True
        self.update()
        popup.show_at(self)

    def _choose(self, model: ModelInfo) -> None:
        self.set_model(model)
        if self._opened_by_mouse:
            self.clearFocus()
        else:
            self.setFocus(Qt.FocusReason.OtherFocusReason)
        self.selected.emit(model)

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