"""Row delegate: format badges, bitrate meters, tag chips and checkboxes."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from ..core.formats import format_duration, format_size
from .table_model import RECORD_ROLE, FileRecordModel
from .tokens import parse_color


class RecordDelegate(QStyledItemDelegate):
    ROW_HEIGHT = 40

    def __init__(self, tokens: dict[str, str], parent=None):
        super().__init__(parent)
        self._tokens = tokens
        self._colors = {key: parse_color(value) for key, value in tokens.items()}
        self._fonts = self._build_fonts()
        self._ai_error_text = "识别失败"

    # -- theming ---------------------------------------------------------

    def set_tokens(self, tokens: dict[str, str]) -> None:
        self._tokens = tokens
        self._colors = {key: parse_color(value) for key, value in tokens.items()}

    def set_strings(self, ai_error: str) -> None:
        self._ai_error_text = ai_error

    @staticmethod
    def _build_fonts() -> dict[str, QFont]:
        base = QFont()
        base.setPixelSize(13)
        name = QFont(base)
        name.setWeight(QFont.Medium)
        small = QFont(base)
        small.setPixelSize(12)
        meta = QFont(base)
        meta.setPixelSize(11)
        badge = QFont(base)
        badge.setPixelSize(10)
        badge.setWeight(QFont.DemiBold)
        tag = QFont(base)
        tag.setPixelSize(10)
        for font in (base, name, small, meta, badge, tag):
            try:
                font.setFeature(QFont.Tag("tnum"), 1)
            except Exception:
                pass
        return {"base": base, "name": name, "small": small, "meta": meta,
                "badge": badge, "tag": tag}

    # -- painting --------------------------------------------------------

    def sizeHint(self, option, index) -> QSize:
        return QSize(option.rect.width(), self.ROW_HEIGHT)

    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        rec = index.data(RECORD_ROLE)
        if rec is None:
            painter.restore()
            return

        rect = option.rect
        col = index.column()
        row = index.row()
        view = option.widget
        hovered = getattr(view, "_hover_row", -1) == row
        checked = index.siblingAtColumn(FileRecordModel.COL_CHECK).data(
            Qt.CheckStateRole
        ) == Qt.Checked
        selected = bool(option.state & QStyle.State_Selected)

        c = self._colors
        if checked:
            background = c["accent_soft"]
        elif selected:
            background = c["selection"]
        elif hovered:
            background = c["row_hover"]
        else:
            background = c["surface"]
        painter.fillRect(rect, background)

        if checked and col == FileRecordModel.COL_CHECK:
            painter.fillRect(QRectF(rect.left(), rect.top(), 3, rect.height()), c["accent"])

        painter.fillRect(
            QRectF(rect.left(), rect.bottom(), rect.width(), 1), c["row_line"]
        )

        if col == FileRecordModel.COL_CHECK:
            self._paint_check(painter, rect, checked)
        elif col == FileRecordModel.COL_NAME:
            self._paint_text(
                painter, rect.adjusted(10, 0, -10, 0), rec.name,
                self._fonts["name"], c["ink"], Qt.AlignLeft | Qt.AlignVCenter,
            )
        elif col == FileRecordModel.COL_SIZE:
            self._paint_text(
                painter, rect.adjusted(6, 0, -10, 0), format_size(rec.size),
                self._fonts["small"], c["ink_2"], Qt.AlignRight | Qt.AlignVCenter,
            )
        elif col == FileRecordModel.COL_DURATION:
            color = c["red"] if rec.error else c["ink_2"]
            self._paint_text(
                painter, rect.adjusted(6, 0, -10, 0), format_duration(rec.duration),
                self._fonts["small"], color, Qt.AlignRight | Qt.AlignVCenter,
            )
        elif col == FileRecordModel.COL_BITRATE:
            self._paint_bitrate(painter, rect, rec)
        elif col == FileRecordModel.COL_FORMAT:
            self._paint_badge(painter, rect, rec.extension)
        elif col == FileRecordModel.COL_MTIME:
            self._paint_text(
                painter, rect.adjusted(6, 0, -10, 0), self._short_mtime(rec.mtime),
                self._fonts["meta"], c["ink_3"], Qt.AlignLeft | Qt.AlignVCenter,
            )
        elif col == FileRecordModel.COL_TAGS:
            self._paint_tags(painter, rect, rec)

        painter.restore()

    # -- pieces ----------------------------------------------------------

    def _paint_text(self, painter, rect, text, font, color, align) -> None:
        painter.setFont(font)
        painter.setPen(color)
        fm = QFontMetrics(font)
        text = fm.elidedText(text or "—", Qt.ElideRight, max(0, rect.width()))
        painter.drawText(rect, align, text)

    def _paint_check(self, painter: QPainter, rect, checked: bool) -> None:
        c = self._colors
        box = QRectF(rect.left() + 12, rect.center().y() - 8, 16, 16)
        if checked:
            painter.setPen(QPen(c["accent"], 1.5))
            painter.setBrush(c["accent"])
            painter.drawRoundedRect(box, 4, 4)
            painter.setPen(QPen(QColor("#FFFFFF"), 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPolyline(QPolygonF([
                QPointF(box.left() + 4, box.center().y()),
                QPointF(box.left() + 7, box.center().y() + 3),
                QPointF(box.left() + 12, box.center().y() - 3.5),
            ]))
        else:
            painter.setPen(QPen(c["line_strong"], 1.5))
            painter.setBrush(c["surface"])
            painter.drawRoundedRect(box, 4, 4)

    def _paint_bitrate(self, painter: QPainter, rect, rec) -> None:
        c = self._colors
        color = c["red"] if rec.error else c["ink_2"]
        text = f"{rec.bitrate / 1_000_000:.1f}" if rec.bitrate > 0 else "—"
        self._paint_text(
            painter, rect.adjusted(6, 0, -10, 0), text, self._fonts["small"], color,
            Qt.AlignRight | Qt.AlignVCenter,
        )

    def _paint_badge(self, painter: QPainter, rect, extension: str) -> None:
        c = self._colors
        text = (extension or "").upper() or "—"
        fm = QFontMetrics(self._fonts["badge"])
        width = max(28, fm.horizontalAdvance(text) + 12)
        box = QRectF(rect.left() + 10, rect.center().y() - 9.5, width, 19)
        painter.setPen(QPen(c["line"], 1))
        painter.setBrush(c["canvas"])
        painter.drawRoundedRect(box, 4, 4)
        painter.setFont(self._fonts["badge"])
        painter.setPen(c["ink_2"])
        painter.drawText(box, Qt.AlignCenter, text)

    def _paint_tags(self, painter: QPainter, rect, rec) -> None:
        c = self._colors
        if not rec.tags:
            if rec.ai_error:
                self._paint_text(
                    painter, rect.adjusted(10, 0, -8, 0), self._ai_error_text,
                    self._fonts["tag"], c["red"], Qt.AlignLeft | Qt.AlignVCenter,
                )
            else:
                self._paint_text(
                    painter, rect.adjusted(10, 0, -8, 0), "—",
                    self._fonts["small"], c["ink_3"], Qt.AlignLeft | Qt.AlignVCenter,
                )
            return

        fm = QFontMetrics(self._fonts["tag"])
        x = rect.left() + 10
        right = rect.right() - 8
        for tag in rec.tags:
            width = fm.horizontalAdvance(tag) + 14
            if x + width > right:
                break
            box = QRectF(x, rect.center().y() - 9.5, width, 19)
            painter.setPen(Qt.NoPen)
            painter.setBrush(c["sunken"])
            painter.drawRoundedRect(box, 4, 4)
            painter.setFont(self._fonts["tag"])
            painter.setPen(c["ink_2"])
            painter.drawText(box, Qt.AlignCenter, tag)
            x += width + 5

    @staticmethod
    def _short_mtime(timestamp: float) -> str:
        if timestamp <= 0:
            return "—"
        dt = datetime.fromtimestamp(timestamp)
        if dt.year == datetime.now().year:
            return dt.strftime("%m-%d %H:%M")
        return dt.strftime("%Y-%m-%d")