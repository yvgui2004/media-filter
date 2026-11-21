"""Theme: light / dark palettes applied through Fusion + QSS.

All literal colors live in ``tokens.py``. This module only maps tokens onto
widget selectors; add new colors there, not here.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from .tokens import DARK, LIGHT, parse_color

_ASSETS = Path(__file__).resolve().parent.parent / "assets"

_QSS = """
* { outline: none; }

QWidget {
    color: @ink@;
    font-size: 13px;
}
QMainWindow, #Root { background: @canvas@; }
#TitleBar { background: @canvas@; border-bottom: 1px solid @line@; }
#TitleBarContent, #WindowControls { background: transparent; }
#FilterBar { background: @canvas@; border-bottom: 1px solid @line@; }
#StatusBar { background: @canvas@; border-top: 1px solid @line@; }
#ContentArea { background: @surface@; }

QTableView {
    background: @surface@;
    alternate-background-color: @surface@;
    border: none;
    gridline-color: transparent;
    selection-background-color: transparent;
    selection-color: @ink@;
}
QTableView::item { border: none; padding: 0; }

QHeaderView { background: @header@; border: none; }
QHeaderView::section {
    background: @header@;
    color: @ink_3@;
    border: none;
    border-bottom: 1px solid @line@;
    padding: 0 10px;
    font-size: 11px;
    font-weight: 600;
}
QHeaderView::section:hover { color: @ink_2@; }

QLineEdit#Search {
    background: @sunken@;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 0 10px;
    color: @ink@;
    font-size: 13px;
    selection-background-color: @accent_soft@;
    selection-color: @ink@;
}
QLineEdit#Search:focus {
    background: @surface@;
    border: 1px solid @accent@;
}

QPushButton {
    border-radius: 8px;
    font-size: 13px;
    padding: 0 14px;
}
QPushButton:focus { border: 1px solid @accent@; }
QPushButton[variant="primary"] {
    background: @accent@;
    border: 1px solid @accent@;
    color: @on_accent@;
    font-weight: 600;
}
QPushButton[variant="primary"]:hover {
    background: @accent_strong@;
    border-color: @accent_strong@;
}
QPushButton[variant="primary"]:pressed { background: @accent_strong@; }
QPushButton[variant="primary"]:disabled {
    background: @line_strong@;
    border-color: transparent;
    color: @ink_3@;
}
QPushButton[variant="ghost"] {
    background: @surface@;
    border: 1px solid @line_strong@;
    color: @ink@;
    font-weight: 500;
}
QPushButton[variant="ghost"]:hover { border-color: @ink_3@; }
QPushButton[variant="ghost"]:pressed { background: @accent_soft@; }
QPushButton[variant="ghost"]:disabled {
    color: @ink_3@;
    border-color: @line@;
    background: transparent;
}

QToolButton { border: none; background: transparent; }
QToolButton:focus { background: @hover_strong@; }
QToolButton[variant="icon"] { border-radius: 8px; }
QToolButton[variant="icon"]:hover { background: @hover_strong@; }
QToolButton[variant="icon"]:pressed { background: @line@; }

#OrderButton {
    background: @surface@;
    border: 1px solid @line_strong@;
    border-radius: 8px;
}
#OrderButton:hover { border-color: @ink_3@; }
#OrderButton:focus { border-color: @accent@; }
#OrderButton:pressed { background: @sunken@; }

#FilterDivider { background: @line_strong@; border: none; }

#WindowButton {
    background: transparent;
    border: none;
    border-radius: 0;
}
#WindowButton:hover { background: @hover_strong@; }
#CloseButton {
    background: transparent;
    border: none;
    border-radius: 0;
}
#CloseButton:hover { background: #C42B1C; }

QComboBox {
    background: transparent;
    border: none;
    border-radius: 6px;
    color: @ink_2@;
    font-size: 12px;
    padding: 0 8px;
}
QComboBox:hover { background: @row_hover@; color: @ink@; }
QComboBox:focus { background: @row_hover@; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox::down-arrow {
    image: url("@chevron@");
    width: 12px;
    height: 12px;
}
QComboBox QAbstractItemView {
    background: @surface@;
    border: 1px solid @line@;
    border-radius: 8px;
    padding: 4px;
    color: @ink@;
    selection-background-color: @accent_soft@;
    selection-color: @ink@;
    outline: none;
}
QComboBox QAbstractItemView::item {
    min-height: 28px;
    padding: 0 10px;
    border-radius: 6px;
}

QPushButton#StopButton {
    background: transparent;
    border: none;
    color: @accent@;
    font-size: 12px;
    padding: 0 8px;
}
QPushButton#StopButton:hover { color: @accent_strong@; }

QPushButton#LinkButton {
    background: transparent;
    border: none;
    color: @ink_3@;
    font-size: 12px;
    padding: 0;
}
QPushButton#LinkButton:hover { color: @accent@; }

QLabel#BrandName { font-size: 13px; font-weight: 600; color: @ink@; }
QLabel#StatKey { font-size: 11px; color: @ink_3@; }
QLabel#StatValue { font-size: 12px; font-weight: 600; color: @ink@; }
QLabel#StatValueAccent { font-size: 12px; font-weight: 600; color: @accent@; }
QLabel#StatusMessage { font-size: 11px; color: @ink_3@; }
QPushButton#SelectionLink {
    background: transparent;
    border: none;
    padding: 0;
    font-size: 12px;
    font-weight: 500;
    color: @accent@;
    text-align: left;
}
QPushButton#SelectionLink:hover { color: @ink@; }
QPushButton#SelectionLink:disabled { color: @ink_3@; }
QLabel#EmptyTitle { font-size: 19px; font-weight: 600; color: @ink@; }
QLabel#EmptyBody { font-size: 13px; color: @ink_2@; }

QProgressBar#ScanLine {
    background: @sunken@;
    border: none;
    border-radius: 1px;
}
QProgressBar#ScanLine::chunk {
    background: @accent@;
    border-radius: 1px;
}

QMenu {
    background: @surface@;
    border: 1px solid @line@;
    border-radius: 8px;
    padding: 5px;
}
QMenu::item {
    padding: 6px 26px 6px 12px;
    border-radius: 5px;
    color: @ink@;
}
QMenu::item:selected { background: @accent_soft@; }
QMenu::separator { height: 1px; background: @line@; margin: 6px 8px; }

QToolTip {
    background: @surface@;
    color: @ink@;
    border: 1px solid @line@;
    padding: 6px 8px;
}

QDialog, QMessageBox { background: @canvas@; }
QMessageBox QLabel { color: @ink@; font-size: 13px; }
QMessageBox QPushButton {
    min-width: 84px;
    min-height: 34px;
    background: @surface@;
    border: 1px solid @line_strong@;
    border-radius: 8px;
    color: @ink@;
    padding: 0 14px;
}
QMessageBox QPushButton:hover { border-color: @ink_3@; }
QMessageBox QPushButton:default {
    background: @accent@;
    border-color: @accent@;
    color: @on_accent@;
    font-weight: 600;
}

#DialogLede { font-size: 13px; color: @ink_2@; }
#SectionLabel { font-size: 11px; font-weight: 600; color: @ink_3@; }
#FieldLabel { font-size: 11px; font-weight: 600; color: @ink_3@; }
#Hint { font-size: 11px; color: @ink_3@; }
#DialogCount { font-size: 11px; color: @ink_3@; }
#DialogNote {
    font-size: 12px;
    color: @ink_2@;
    background: transparent;
    border: none;
    border-left: 2px solid @accent@;
    padding-left: 10px;
}
#DialogRule { background: @line@; border: none; }

/* ---------- settings: B4 tabs + summary rail ---------- */
#SettingsHeading { font-size: 19px; font-weight: 600; color: @ink@; }
#SettingsSub { font-size: 10.5px; color: @ink_3@; }
#SettingsHeader { background: @canvas@; }
#HeaderChip, #HeaderChipAccent {
    font-size: 9.5px;
    font-weight: 600;
    color: @ink_3@;
    background: @surface@;
    border: 1px solid @line_strong@;
    border-radius: 9px;
    padding: 0 8px;
}
#HeaderChipAccent {
    color: @accent@;
    background: @accent_soft@;
    border-color: @accent@;
}
#SettingsPane {
    background: @surface@;
    border: 1px solid @line@;
    border-radius: 10px;
}
#SettingsStack, #SettingsPage { background: transparent; border: none; }
#SettingsRail { background: transparent; }
#PaneTitle { font-size: 13px; font-weight: 600; color: @ink@; }
#PaneLede { font-size: 10px; color: @ink_3@; }
#ScopeNote { background: @canvas@; border: none; border-radius: 7px; }
#ScopeText { font-size: 9.5px; color: @ink_3@; }
#FactCard {
    background: @surface@;
    border: 1px solid @line@;
    border-radius: 7px;
}
#FactLabel {
    font-size: 8px;
    font-weight: 600;
    color: @ink_3@;
}
#FactValue { font-size: 10px; font-weight: 600; color: @ink@; }
#FactDetail { font-size: 8.3px; color: @ink_3@; }
#RailCard {
    background: @surface@;
    border: 1px solid @line@;
    border-radius: 10px;
}
#RailTitle {
    font-size: 9px;
    font-weight: 700;
    color: @ink_3@;
    padding-bottom: 4px;
}
#RailLabel { font-size: 9px; color: @ink_3@; }
#RailValue { font-size: 9px; font-weight: 600; color: @ink_2@; }
#RailNote {
    font-size: 9px;
    color: @ink_3@;
    background: @canvas@;
    border: none;
    border-radius: 8px;
    padding: 8px;
}
#AdvPanel {
    background: @surface@;
    border: 1px solid @line@;
    border-radius: 9px;
}
QLabel#DeviceChip {
    background: @accent_soft@;
    color: @accent@;
    border: none;
    border-radius: 5px;
    padding: 0 6px;
    font-size: 9.5px;
    font-weight: 600;
}
QLabel#DeviceTitle {
    font-size: 11px;
    font-weight: 600;
    color: @ink_2@;
}
QLabel#DeviceHint {
    font-size: 11px;
    color: @ink_3@;
}
#PreviewChip {
    font-size: 9.5px;
    color: @ink_2@;
    background: @sunken@;
    border: none;
    border-radius: 5px;
    padding: 0 7px;
}
#TagsEmpty { font-size: 9.5px; color: @ink_3@; padding: 4px 0; }
#DialogFooter, #SettingsFooter { background: @surface@; }

QDialog QPushButton { min-width: 84px; min-height: 34px; }

QLineEdit#FieldInput {
    background: @surface@;
    border: 1px solid @line_strong@;
    border-radius: 8px;
    padding: 0 11px;
    color: @ink@;
    font-size: 13px;
    selection-background-color: @accent_soft@;
    selection-color: @ink@;
}
QLineEdit#FieldInput:focus { border-color: @accent@; }

QTextEdit#CodeInput {
    background: @surface@;
    border: 1px solid @line_strong@;
    border-radius: 8px;
    padding: 7px;
    color: @ink@;
    selection-background-color: @accent_soft@;
    selection-color: @ink@;
}
QTextEdit#CodeInput:focus { border-color: @accent@; }
QTextEdit#PreviewBox {
    background: @header@;
    border: 1px solid @line@;
    border-radius: 8px;
    padding: 7px;
    color: @ink_2@;
    selection-background-color: @accent_soft@;
    selection-color: @ink@;
}

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: @scroll@;
    border-radius: 3px;
    min-height: 30px;
}
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background: @scroll@;
    border-radius: 3px;
    min-width: 30px;
}
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

/* ---------- AI split button ---------- */
QWidget#AiSwitch {
    background: @surface@;
    border: 1px solid @line_strong@;
    border-radius: 8px;
}
QAbstractButton#AiMain {
    background: transparent;
    border: none;
}
QAbstractButton#AiCaret {
    background: transparent;
    border: none;
    border-top-right-radius: 7px;
    border-bottom-right-radius: 7px;
}
QAbstractButton#AiCaret:hover { background: @accent_soft@; }
QAbstractButton#AiCaret:disabled { background: transparent; }

/* ---------- recognition settings ---------- */
QLabel#ModeTitle { font-size: 13px; font-weight: 600; color: @ink@; background: transparent; }
QLabel#ModeDesc { font-size: 12px; color: @ink_2@; background: transparent; }
QLabel#ModeFoot { font-size: 11px; color: @ink_3@; background: transparent; }
QLabel#ModeBadge {
    font-size: 10px; font-weight: 600;
    color: @accent@; background: @accent_soft@;
    border: 1px solid @accent@;
    border-radius: 8px;
    padding: 1px 5px;
}
QLabel#CurrentBadge {
    font-size: 10px; font-weight: 600;
    color: @ink_3@;
    border: 1px solid @line_strong@;
    border-radius: 8px;
    padding: 1px 5px;
}
QLabel#FieldNote { font-size: 11px; color: @ink_3@; background: transparent; }
QLabel#CheckHint { font-size: 11px; color: @ink_3@; background: transparent; }

QPushButton#TagChip {
    min-width: 0;
    min-height: 0;
    /* Qt's QSS height is the content box: 24 + 1px border top/bottom = 26. */
    height: 24px;
    padding: 0 9px;
    border: 1px solid @line_strong@;
    border-radius: 6px;
    background: @surface@;
    color: @ink_2@;
    font-size: 11px;
}
QPushButton#TagChip:hover { border-color: @ink_3@; }
QPushButton#TagChip:checked {
    background: @accent_soft@;
    border-color: @accent@;
    color: @accent@;
    font-weight: 600;
}
QLabel#TagGroupLabel {
    font-size: 11px; font-weight: 600; color: @ink_3@; background: transparent;
}
QLabel#TagCount { font-size: 11px; color: @ink_3@; background: transparent; }

QToolButton#AdvHead {
    border: none;
    background: transparent;
    color: @ink_2@;
    font-size: 12px;
    font-weight: 500;
    padding: 0 2px;
    text-align: left;
}
QToolButton#AdvHead:hover { color: @ink@; }

QPushButton#Segment {
    min-width: 56px;
    min-height: 0;
    height: 26px;
    padding: 0 10px;
    border: 1px solid transparent;
    border-radius: 6px;
    background: transparent;
    color: @ink_2@;
    font-size: 11px;
}
QPushButton#Segment:hover { color: @ink@; background: @hover_strong@; }
QPushButton#Segment:checked {
    background: @accent_soft@;
    border-color: @accent@;
    color: @accent@;
    font-weight: 600;
}

QFrame#SegmentBox {
    background: @surface@;
    border: 1px solid @line_strong@;
    border-radius: 8px;
}

QScrollArea#SettingsScroll {
    background: transparent;
    border: none;
}
QScrollArea#SettingsScroll > QWidget > QWidget { background: transparent; }

QFrame#CustomTagRow {
    background: @surface@;
    border: 1px solid @line@;
    border-radius: 8px;
}
QFrame#CustomTagRow:hover { border-color: @line_strong@; }
QFrame#CustomTagRow[dropTarget="true"] {
    border: 1px solid @accent@;
    background: @accent_soft@;
}
QLabel#CustomTagName { font-size: 12px; color: @ink@; background: transparent; }
QToolButton#CustomTagRemove {
    border: none; border-radius: 5px; background: transparent;
    color: @ink_3@; font-size: 14px;
}
QToolButton#CustomTagRemove:hover { background: @hover_strong@; color: @red@; }
QListWidget#TagGrid {
    background: transparent;
    border: none;
    outline: none;
}
QListWidget#TagGrid::item { background: transparent; border: none; }
QLabel#TagEmpty {
    border: 1px dashed @line_strong@;
    border-radius: 8px;
    color: @ink_3@;
    font-size: 11px;
    padding: 12px;
}

#GuideBar {
    background: @accent_soft@;
    border-bottom: 1px solid @line@;
}
QLabel#GuideText { font-size: 12px; color: @ink_2@; background: transparent; }
QPushButton#GuideAction {
    min-width: 0;
    min-height: 0;
    border: none;
    background: transparent;
    color: @accent@;
    font-size: 12px;
    font-weight: 600;
    padding: 0;
}
QPushButton#GuideAction:hover { color: @accent_strong@; }
QToolButton#GuideClose {
    border: none;
    border-radius: 6px;
    background: transparent;
    color: @ink_3@;
}
QToolButton#GuideClose:hover { background: @hover_strong@; color: @ink@; }

QToolButton#SettingsButton[attention="true"] {
    border: 1px solid @accent@;
    border-radius: 8px;
    background: @accent_soft@;
}

/* B4 settings at 1.15x: the tabbed page is a 900x570 composition enlarged
   to 1035x656, so every inner control steps up with the dialog. Scope the
   overrides to the B4 shell; first-run keeps its original roomier sizing. */
#SettingsHeader QLabel#SettingsHeading { font-size: 22px; }
#SettingsHeader QLabel#SettingsSub { font-size: 12px; }
#SettingsHeader QLabel#HeaderChip, #SettingsHeader QLabel#HeaderChipAccent {
    font-size: 11px;
    padding: 0 9px;
    border-radius: 10px;
}
#SettingsPane { border-radius: 12px; }
#SettingsPane QLabel#PaneTitle { font-size: 15px; }
#SettingsPane QLabel#PaneLede { font-size: 12px; }
#SettingsPane QLabel#ScopeText { font-size: 11px; }
#SettingsPane #ScopeNote { border-radius: 8px; }
#SettingsPane #FactCard { border-radius: 8px; }
#SettingsPane QLabel#FactLabel { font-size: 9px; }
#SettingsPane QLabel#FactValue { font-size: 12px; }
#SettingsPane QLabel#FactDetail { font-size: 10px; }
#SettingsPane #AdvPanel { border-radius: 10px; }
#SettingsPane QLabel#DeviceChip {
    font-size: 9.5px;
    border-radius: 5px;
    padding: 0 6px;
}
#SettingsPane QLabel#DeviceTitle { font-size: 12px; }
#SettingsPane QLabel#DeviceHint { font-size: 11px; }
#SettingsPane QLabel#ModeTitle { font-size: 14px; }
#SettingsPane QLabel#ModeDesc { font-size: 12px; }
#SettingsPane QLabel#ModeFoot { font-size: 12px; }
#SettingsPane #FieldLabel { font-size: 12px; }
#SettingsPane #SectionLabel { font-size: 12px; }
#SettingsPane #Hint { font-size: 12px; }
#SettingsPane #DialogCount { font-size: 12px; }
#SettingsPane #DialogNote { font-size: 12px; padding-left: 10px; }
#SettingsPane QLabel#FieldNote { font-size: 12px; }
#SettingsPane QLabel#CheckHint { font-size: 12px; }
#SettingsPane QLineEdit#FieldInput {
    min-height: 35px;
    font-size: 14px;
    padding: 0 12px;
    border-radius: 9px;
}
#SettingsPane QPushButton#TagChip {
    height: 23px;
    padding: 0 12px;
    font-size: 12px;
    border-radius: 6px;
}
#SettingsPane QLabel#TagGroupLabel { font-size: 10px; }
#SettingsPane QLabel#TagCount { font-size: 12px; }
#SettingsPane QPushButton#Segment {
    height: 25px;
    padding: 0 12px;
    font-size: 12px;
}
#SettingsPane QPushButton[variant="ghost"] {
    min-height: 35px;
    font-size: 13px;
}
#SettingsRail QLabel#RailTitle {
    font-size: 10px;
    padding-bottom: 5px;
}
#SettingsRail QLabel#RailLabel { font-size: 10px; }
#SettingsRail QLabel#RailValue { font-size: 10px; }
#SettingsRail QLabel#RailNote {
    font-size: 10px;
    padding: 9px;
    border-radius: 9px;
}
#SettingsRail #RailCard { border-radius: 12px; }
#SettingsFooter QPushButton { min-height: 35px; font-size: 14px; }
#SettingsFooter QPushButton#LinkButton { font-size: 13px; }
"""


def build_qss(palette: dict[str, str]) -> str:
    qss = _QSS
    chevron = _ASSETS / (
        "chevron-dark.svg" if palette is DARK else "chevron-light.svg"
    )
    for key, value in palette.items():
        qss = qss.replace(f"@{key}@", value)
    return qss.replace("@chevron@", chevron.as_posix())


def resolve_mode(mode: str) -> str:
    if mode in ("light", "dark"):
        return mode
    from PySide6.QtGui import QGuiApplication

    return _system_scheme(QGuiApplication.styleHints())


def palette_for(mode: str) -> dict[str, str]:
    return DARK if resolve_mode(mode) == "dark" else LIGHT


def apply_theme(app: QApplication, mode: str) -> dict[str, str]:
    """Apply a light/dark/system theme; returns the resolved palette."""
    palette = palette_for(mode)
    app.setStyle("Fusion")
    app.setStyleSheet(build_qss(palette))

    qp = QPalette()
    qp.setColor(QPalette.Window, parse_color(palette["canvas"]))
    qp.setColor(QPalette.Base, parse_color(palette["surface"]))
    qp.setColor(QPalette.AlternateBase, parse_color(palette["surface"]))
    qp.setColor(QPalette.Text, parse_color(palette["ink"]))
    qp.setColor(QPalette.WindowText, parse_color(palette["ink"]))
    qp.setColor(QPalette.ButtonText, parse_color(palette["ink"]))
    qp.setColor(QPalette.Button, parse_color(palette["canvas"]))
    qp.setColor(QPalette.PlaceholderText, parse_color(palette["ink_3"]))
    qp.setColor(QPalette.Highlight, parse_color(palette["accent_soft"]))
    qp.setColor(QPalette.HighlightedText, parse_color(palette["ink"]))
    qp.setColor(QPalette.ToolTipBase, parse_color(palette["surface"]))
    qp.setColor(QPalette.ToolTipText, parse_color(palette["ink"]))
    qp.setColor(QPalette.Link, parse_color(palette["accent"]))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        qp.setColor(QPalette.Disabled, role, parse_color(palette["ink_3"]))
    app.setPalette(qp)
    return palette


def _system_scheme(hints) -> str:
    """Derive light/dark from the OS appearance hint."""
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