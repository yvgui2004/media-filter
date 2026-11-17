"""Small line-icon set drawn with QPainter.

Qt ships no cross-platform icon theme on Windows, so the interface gets a
consistent 24x24 line set instead of native-style pixmaps.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QGuiApplication,
    QIcon,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)


def _pen(color: QColor, width: float = 1.7) -> QPen:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def _draw(p: QPainter, name: str, color: QColor, weight: float = 1.7) -> None:
    p.setPen(_pen(color, weight))
    p.setBrush(Qt.NoBrush)

    if name == "folder":
        path = QPainterPath()
        path.moveTo(3, 7)
        path.lineTo(9, 7)
        path.lineTo(11, 9)
        path.lineTo(21, 9)
        path.lineTo(21, 19)
        path.lineTo(3, 19)
        path.closeSubpath()
        p.drawPath(path)

    elif name == "refresh":
        p.drawArc(QRectF(4, 4, 16, 16), 30 * 16, 300 * 16)
        p.drawLine(QPointF(19.4, 3.2), QPointF(19.4, 8.4))
        p.drawLine(QPointF(19.4, 3.2), QPointF(14.2, 3.2))

    elif name == "sparkle":
        star = QPainterPath()
        star.moveTo(12, 3)
        star.lineTo(13.9, 10.1)
        star.lineTo(21, 12)
        star.lineTo(13.9, 13.9)
        star.lineTo(12, 21)
        star.lineTo(10.1, 13.9)
        star.lineTo(3, 12)
        star.lineTo(10.1, 10.1)
        star.closeSubpath()
        p.fillPath(star, color)
        p.setBrush(color)
        p.drawEllipse(QRectF(17, 3, 3, 3))

    elif name == "sun":
        p.drawEllipse(QRectF(8, 8, 8, 8))
        for x1, y1, x2, y2 in (
            (12, 2.5, 12, 4.5), (12, 19.5, 12, 21.5),
            (2.5, 12, 4.5, 12), (19.5, 12, 21.5, 12),
            (5.2, 5.2, 6.6, 6.6), (17.4, 17.4, 18.8, 18.8),
            (18.8, 5.2, 17.4, 6.6), (6.6, 17.4, 5.2, 18.8),
        ):
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    elif name == "moon":
        outer = QPainterPath()
        outer.addEllipse(QRectF(3.5, 2.5, 17, 19))
        inner = QPainterPath()
        inner.addEllipse(QRectF(9.5, 0.5, 15, 16))
        p.fillPath(outer.subtracted(inner), color)

    elif name == "chevron-down":
        p.drawPolyline([QPointF(6, 9), QPointF(12, 15), QPointF(18, 9)])

    elif name == "chevron-right":
        p.drawPolyline([QPointF(9, 6), QPointF(15, 12), QPointF(9, 18)])

    elif name == "grip":
        p.setBrush(color)
        p.setPen(Qt.NoPen)
        for x in (9, 15):
            for y in (7, 12, 17):
                p.drawEllipse(QRectF(x - 1.2, y - 1.2, 2.4, 2.4))

    elif name == "arrow-up":
        p.drawLine(QPointF(12, 19), QPointF(12, 5))
        p.drawPolyline([QPointF(6, 11), QPointF(12, 5), QPointF(18, 11)])

    elif name == "arrow-down":
        p.drawLine(QPointF(12, 5), QPointF(12, 19))
        p.drawPolyline([QPointF(6, 13), QPointF(12, 19), QPointF(18, 13)])

    elif name == "search":
        p.drawEllipse(QRectF(4, 4, 12, 12))
        p.drawLine(QPointF(15.4, 15.4), QPointF(20.5, 20.5))

    elif name == "stop":
        p.setBrush(color)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(6, 6, 12, 12), 2.5, 2.5)

    elif name == "minimize":
        p.drawLine(QPointF(6, 12), QPointF(18, 12))

    elif name == "maximize":
        p.drawRect(QRectF(6, 6, 12, 12))

    elif name == "restore":
        p.drawRect(QRectF(5, 8, 11, 11))
        p.drawPolyline([QPointF(8, 8), QPointF(8, 5), QPointF(19, 5), QPointF(19, 16), QPointF(16, 16)])

    elif name == "close":
        p.drawLine(QPointF(6.5, 6.5), QPointF(17.5, 17.5))
        p.drawLine(QPointF(17.5, 6.5), QPointF(6.5, 17.5))

    elif name == "check":
        p.setPen(_pen(color, 2.6))
        p.drawPolyline([QPointF(5, 13), QPointF(10, 18), QPointF(19, 6)])

    elif name == "clock":
        p.drawEllipse(QRectF(3.5, 3.5, 17, 17))
        p.drawLine(QPointF(12, 7), QPointF(12, 12))
        p.drawLine(QPointF(12, 12), QPointF(15.5, 14))

    elif name == "film":
        p.drawRoundedRect(QRectF(3, 5, 13, 14), 2, 2)
        p.drawLine(QPointF(19, 8), QPointF(19, 16))
        p.drawLine(QPointF(16, 8), QPointF(16, 16))

    elif name == "dot":
        p.setBrush(color)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(9, 9, 6, 6))

    elif name == "settings":
        p.drawEllipse(QRectF(6.5, 6.5, 11, 11))
        p.drawEllipse(QRectF(10, 10, 4, 4))
        p.setPen(_pen(color, 2.6))
        for index in range(8):
            angle = math.radians(index * 45)
            inner = (math.cos(angle) * 5.3, math.sin(angle) * 5.3)
            outer = (math.cos(angle) * 9.3, math.sin(angle) * 9.3)
            p.drawLine(
                QPointF(12 + inner[0], 12 + inner[1]),
                QPointF(12 + outer[0], 12 + outer[1]),
            )

    elif name == "eye":
        path = QPainterPath()
        path.moveTo(3, 12)
        path.cubicTo(6, 6, 18, 6, 21, 12)
        path.cubicTo(18, 18, 6, 18, 3, 12)
        p.drawPath(path)
        p.drawEllipse(QRectF(9.5, 9.5, 5, 5))

    elif name == "eye-off":
        path = QPainterPath()
        path.moveTo(3, 12)
        path.cubicTo(6, 6, 18, 6, 21, 12)
        path.cubicTo(18, 18, 6, 18, 3, 12)
        p.drawPath(path)
        p.drawEllipse(QRectF(9.5, 9.5, 5, 5))
        p.drawLine(QPointF(4.5, 4.5), QPointF(19.5, 19.5))

    elif name == "cube":
        p.drawPolygon([
            QPointF(12, 3), QPointF(20, 7.5), QPointF(20, 16.5),
            QPointF(12, 21), QPointF(4, 16.5), QPointF(4, 7.5),
        ])
        p.drawLine(QPointF(4, 7.5), QPointF(12, 12))
        p.drawLine(QPointF(20, 7.5), QPointF(12, 12))
        p.drawLine(QPointF(12, 12), QPointF(12, 21))


def line_icon(
    name: str, color: str, size: int = 18, weight: float = 1.7
) -> QIcon:
    """Return a crisply rendered icon at the screen's actual pixel ratio.

    A fixed 2x asset is downscaled on 150%/175% Windows screens, which
    softens thin strokes (the AI caret chevron read as a pale blue tint on
    the accent button). Paint at the real ratio instead. ``weight`` is the
    stroke width on the 24-unit grid; icons drawn alone on an accent fill
    pass a heavier pen so their core stays white after subpixel placement.
    """
    screen = QGuiApplication.primaryScreen()
    dpr = max(1.0, float(screen.devicePixelRatio())) if screen is not None else 2.0
    pm = QPixmap(round(size * dpr), round(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.scale(size / 24.0, size / 24.0)
    _draw(p, name, QColor(color), weight)
    p.end()
    return QIcon(pm)


def _paint_brand(p: QPainter, extent: float, accent: str, on_accent: str) -> None:
    """Paint the app mark on a 24-unit grid, scaled to `extent` pixels."""
    p.setRenderHint(QPainter.Antialiasing, True)
    p.scale(extent / 24.0, extent / 24.0)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(accent))
    p.drawRoundedRect(QRectF(1, 1, 22, 22), 6, 6)
    p.setPen(_pen(QColor(on_accent), 1.8))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(5.5, 6.5, 10, 11), 2, 2)
    p.drawLine(QPointF(19.2, 8.8), QPointF(19.2, 15.8))


def brand_image(
    size: int,
    accent: str = "#2B7CA6",
    on_accent: str = "#FFFFFF",
) -> QImage:
    """The app mark at an exact pixel size (used for the window icon)."""
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    _paint_brand(p, size, accent, on_accent)
    p.end()
    return image


def brand_icon(
    accent: str = "#2B7CA6",
    on_accent: str = "#FFFFFF",
) -> QIcon:
    """Multi-size window icon so captions, taskbar and Alt-Tab all match
    the titlebar mark instead of an unrelated legacy asset."""
    icon = QIcon()
    for size in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        icon.addPixmap(QPixmap.fromImage(brand_image(size, accent, on_accent)))
    return icon


def brand_pixmap(
    size: int = 22,
    accent: str = "#2B7CA6",
    on_accent: str = "#FFFFFF",
) -> QPixmap:
    """The app mark: a rounded accent tile with a white film frame."""
    dpr = 2
    image = brand_image(size * dpr, accent, on_accent)
    image.setDevicePixelRatio(dpr)
    return QPixmap.fromImage(image)