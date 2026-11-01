"""Theme: light / dark palettes applied through Qt's Fusion style + QSS.

Fusion is used because it respects QSS consistently across platforms (the
native Windows style ignores most stylesheet directives).
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

LIGHT = {
    "bg": "#f4f5f7",
    "surface": "#ffffff",
    "header": "#eceef1",
    "alt": "#f7f8fa",
    "text": "#1f2328",
    "muted": "#6b7280",
    "border": "#d6d9de",
    "accent": "#2563eb",
    "accent_hover": "#1d4ed8",
    "accent_text": "#ffffff",
    "selection": "rgba(37, 99, 235, 0.18)",
    "danger": "#c0392b",
    "scroll": "#c2c7cf",
}

DARK = {
    "bg": "#1b1d20",
    "surface": "#25282d",
    "header": "#2c2f35",
    "alt": "#292c31",
    "text": "#e7e9ec",
    "muted": "#9aa0a8",
    "border": "#3a3f46",
    "accent": "#3b82f6",
    "accent_hover": "#2563eb",
    "accent_text": "#ffffff",
    "selection": "rgba(59, 130, 246, 0.28)",
    "danger": "#ef5350",
    "scroll": "#454a51",
}


_QSS = """
QWidget {
    background-color: @@bg@@;
    color: @@text@@;
    font-size: 13px;
}
QMainWindow, QDialog {
    background-color: @@bg@@;
}
QMenuBar, QMenuBar::item {
    background-color: @@surface@@;
    color: @@text@@;
}
QMenu {
    background-color: @@surface@@;
    border: 1px solid @@border@@;
    padding: 4px;
}
QMenu::item { padding: 5px 24px 5px 12px; border-radius: 4px; }
QMenu::item:selected { background-color: @@selection@@; }

QToolBar { background-color: @@surface@@; border-bottom: 1px solid @@border@@; }
QToolButton, QPushButton {
    background-color: @@surface@@;
    border: 1px solid @@border@@;
    border-radius: 6px;
    padding: 6px 14px;
    color: @@text@@;
}
QToolButton:hover, QPushButton:hover { border-color: @@accent@@; }
QToolButton:pressed, QPushButton:pressed { background-color: @@alt@@; }
QPushButton:disabled, QToolButton:disabled { color: @@muted@@; }
QPushButton#orderButton {
    padding: 2px 0;
    min-width: 30px;
    max-width: 30px;
    font-size: 14px;
}

QLineEdit, QComboBox, QSpinBox, QTextEdit {
    background-color: @@surface@@;
    border: 1px solid @@border@@;
    border-radius: 6px;
    padding: 5px 8px;
    selection-background-color: @@selection@@;
    selection-color: @@text@@;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus {
    border-color: @@accent@@;
}
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView {
    background-color: @@surface@@;
    border: 1px solid @@border@@;
    selection-background-color: @@selection@@;
    selection-color: @@text@@;
}

QTableView {
    background-color: @@surface@@;
    alternate-background-color: @@alt@@;
    gridline-color: @@border@@;
    border: none;
    selection-background-color: @@selection@@;
    selection-color: @@text@@;
}
QTableView::item { padding: 3px 6px; }
QHeaderView::section {
    background-color: @@header@@;
    color: @@text@@;
    border: none;
    border-bottom: 1px solid @@border@@;
    border-right: 1px solid @@border@@;
    padding: 6px 8px;
    font-weight: 600;
}
QStatusBar { background-color: @@surface@@; border-top: 1px solid @@border@@; }
QProgressBar {
    background-color: @@alt@@;
    border: 1px solid @@border@@;
    border-radius: 6px;
    text-align: center;
    height: 14px;
}
QProgressBar::chunk { background-color: @@accent@@; border-radius: 5px; }

QScrollBar:vertical { background: @@bg@@; width: 12px; margin: 0; }
QScrollBar::handle:vertical { background: @@scroll@@; border-radius: 5px; min-height: 24px; }
QScrollBar:horizontal { background: @@bg@@; height: 12px; margin: 0; }
QScrollBar::handle:horizontal { background: @@scroll@@; border-radius: 5px; min-width: 24px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }

QGroupBox {
    border: 1px solid @@border@@;
    border-radius: 6px;
    margin-top: 8px;
}
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
QCheckBox { spacing: 6px; }
QLabel { background: transparent; }
QLabel#presetNote { color: @@muted@@; }
"""


def build_qss(palette: dict[str, str]) -> str:
    qss = _QSS
    for key, value in palette.items():
        qss = qss.replace(f"@@{key}@@", value)
    return qss


def apply_theme(app: QApplication, mode: str) -> None:
    """Apply a light/dark/system theme to *app*."""
    resolved = mode
    if mode == "system":
        from PySide6.QtGui import QGuiApplication
        resolved = _system_scheme(QGuiApplication.styleHints())
    elif mode not in ("light", "dark"):
        resolved = "light"

    palette = DARK if resolved == "dark" else LIGHT
    app.setStyle("Fusion")
    app.setStyleSheet(build_qss(palette))

    qp = QPalette()
    qp.setColor(QPalette.Window, QColor(palette["bg"]))
    qp.setColor(QPalette.Base, QColor(palette["surface"]))
    qp.setColor(QPalette.Text, QColor(palette["text"]))
    qp.setColor(QPalette.WindowText, QColor(palette["text"]))
    qp.setColor(QPalette.ButtonText, QColor(palette["text"]))
    app.setPalette(qp)


def _system_scheme(hints) -> str:
    """Derive light/dark from the OS appearance hint.

    ``colorScheme()`` returns a Qt.ColorScheme enum on some bindings and a
    string on others, so accept both.
    """
    from PySide6.QtCore import Qt

    try:
        scheme = hints.colorScheme()
    except Exception:
        scheme = None
    if isinstance(scheme, str):
        return "dark" if scheme.lower() == "dark" else "light"
    if scheme == Qt.ColorScheme.Dark:
        return "dark"
    return "light"