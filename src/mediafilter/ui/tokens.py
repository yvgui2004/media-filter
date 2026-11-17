"""Design tokens for the Light Table interface.

One palette per mode; every color in the UI must trace back to a token here.
Values mirror `.interface-design/system.md`.
"""

from __future__ import annotations

import re

from PySide6.QtGui import QColor

LIGHT = {
    "canvas": "#F4F8FB",
    "surface": "#FFFFFF",
    "sunken": "#E8F1F8",
    "header": "#FBFDFE",
    "ink": "#14232C",
    "ink_2": "#465A66",
    "ink_3": "#64757F",
    "line": "rgba(20, 35, 44, 0.09)",
    "line_strong": "rgba(20, 35, 44, 0.16)",
    "accent": "#2B7CA6",
    "accent_strong": "#226584",
    "accent_soft": "rgba(43, 124, 166, 0.08)",
    "selection": "rgba(43, 124, 166, 0.13)",
    "row_hover": "rgba(20, 35, 44, 0.03)",
    "row_line": "rgba(20, 35, 44, 0.06)",
    "hover_strong": "rgba(20, 35, 44, 0.06)",
    "scroll": "rgba(20, 35, 44, 0.22)",
    "green": "#3F7A4E",
    "red": "#B3261E",
    "on_accent": "#FFFFFF",
}

DARK = {
    "canvas": "#0F161B",
    "surface": "#162027",
    "sunken": "#0B1115",
    "header": "#111A20",
    "ink": "#E6EEF3",
    "ink_2": "#A9BBC6",
    "ink_3": "#7E929E",
    "line": "rgba(230, 238, 243, 0.10)",
    "line_strong": "rgba(230, 238, 243, 0.18)",
    "accent": "#6FB3D1",
    "accent_strong": "#8CC6DF",
    "accent_soft": "rgba(111, 179, 209, 0.12)",
    "selection": "rgba(111, 179, 209, 0.18)",
    "row_hover": "rgba(230, 238, 243, 0.04)",
    "row_line": "rgba(230, 238, 243, 0.07)",
    "hover_strong": "rgba(230, 238, 243, 0.08)",
    "scroll": "rgba(230, 238, 243, 0.24)",
    "green": "#9BC46B",
    "red": "#E57373",
    "on_accent": "#0F161B",
}

_RGBA = re.compile(
    r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)",
    re.IGNORECASE,
)


def parse_color(value: str) -> QColor:
    """Parse ``#RRGGBB`` or ``rgba(r, g, b, a)`` into a QColor."""
    text = value.strip()
    m = _RGBA.match(text)
    if m:
        r, g, b = (int(m.group(i)) for i in (1, 2, 3))
        a = float(m.group(4)) if m.group(4) is not None else 1.0
        return QColor(r, g, b, int(round(a * 255)))
    return QColor(text)