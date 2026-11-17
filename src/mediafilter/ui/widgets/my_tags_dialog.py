"""「我的标签」— the user's closed set of target labels.

Generic on purpose: ``踢足球``, ``露营``, ``王者荣耀`` all work. Entries are
sent to the model verbatim (no stemming or merging), capped at ten, and can
be reordered by dragging the grip.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMimeData, QPoint, Qt, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QSizePolicy, QSpacerItem, QToolButton, QVBoxLayout,
    QWidget,
)

from ...core.vocabulary import (
    MAX_CUSTOM_LABELS, MAX_LABEL_LENGTH, merge_custom_labels, parse_custom_labels,
)
from ..dialog_base import AppDialog, dialog_button, note_label, section_label
from ..icons import line_icon
from ..tokens import LIGHT

_MIME = "application/x-mediafilter-tag-index"


class _Grip(QLabel):
    """Drag handle; the parent chip starts a QDrag when the mouse moves."""

    def __init__(self, chip: "CustomTagChip") -> None:
        super().__init__()
        self._chip = chip
        self._press: QPoint | None = None

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._press is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if (event.position().toPoint() - self._press).manhattanLength() < (
            QApplication.startDragDistance()
        ):
            return
        self._press = None
        self._chip.start_drag()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._press = None
        super().mouseReleaseEvent(event)


class CustomTagChip(QFrame):
    removeRequested = Signal(int)
    moved = Signal(int, int)

    def __init__(self, index: int, text: str, tokens: dict[str, str],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._index = index
        self._tokens = tokens
        self.setObjectName("CustomTagRow")
        self.setFixedHeight(38)
        self.setAcceptDrops(True)

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 0, 6, 0)
        row.setSpacing(7)

        self.grip = _Grip(self)
        self.grip.setPixmap(line_icon("grip", tokens["ink_3"], 14).pixmap(14, 14))
        self.grip.setCursor(Qt.CursorShape.OpenHandCursor)
        row.addWidget(self.grip)

        self.name = QLabel(text)
        self.name.setObjectName("CustomTagName")
        self.name.setToolTip(text)
        self.name.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        row.addWidget(self.name, 1)

        self.remove = QToolButton()
        self.remove.setObjectName("CustomTagRemove")
        self.remove.setText("×")
        self.remove.setFixedSize(22, 22)
        self.remove.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remove.clicked.connect(lambda: self.removeRequested.emit(self._index))
        row.addWidget(self.remove)

    def start_drag(self) -> None:
        mime = QMimeData()
        mime.setData(_MIME, str(self._index).encode("ascii"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        pixmap = self.grab()
        drag.setPixmap(pixmap)
        drag.setHotSpot(QPoint(pixmap.width() // 2, pixmap.height() // 2))
        drag.exec(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(_MIME):
            event.acceptProposedAction()
            self._set_drop_target(True)

    def dragLeaveEvent(self, event) -> None:
        self._set_drop_target(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:
        self._set_drop_target(False)
        try:
            source = int(bytes(event.mimeData().data(_MIME)).decode("ascii"))
        except (ValueError, UnicodeDecodeError):
            return
        event.acceptProposedAction()
        if source != self._index:
            self.moved.emit(source, self._index)

    def _set_drop_target(self, active: bool) -> None:
        self.setProperty("dropTarget", active)
        style = self.style()
        style.unpolish(self)
        style.polish(self)


class _TagGrid(QWidget):
    """Two-column grid; rebuilds itself whenever the label list changes."""

    changed = Signal()
    removeRequested = Signal(int)
    moveRequested = Signal(int, int)

    def __init__(self, tr, tokens: dict[str, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tr = tr
        self._tokens = tokens
        self._labels: list[str] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._body = QWidget()
        self._grid = QGridLayout(self._body)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(6)
        self._grid.setVerticalSpacing(6)
        layout.addWidget(self._body)
        self._empty = QLabel()
        self._empty.setObjectName("TagEmpty")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setWordWrap(True)
        self._empty.setMinimumHeight(74)
        layout.addWidget(self._empty)

    def set_labels(self, labels: list[str]) -> None:
        self._labels = list(labels)
        self._rebuild()

    def labels(self) -> list[str]:
        return list(self._labels)

    def _rebuild(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item is None:
                break
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not self._labels:
            self._body.setVisible(False)
            self._empty.setVisible(True)
            self._empty.setText(
                f"<b>{self._tr('my_tags.empty_title')}</b><br>"
                f"{self._tr('my_tags.empty_body')}"
            )
            return
        self._body.setVisible(True)
        self._empty.setVisible(False)
        for index, label in enumerate(self._labels):
            chip = CustomTagChip(index, label, self._tokens, self._body)
            chip.removeRequested.connect(self._on_remove)
            chip.moved.connect(self.moveRequested)
            self._grid.addWidget(chip, index // 2, index % 2)
        rows = (len(self._labels) + 1) // 2
        self._grid.addItem(
            QSpacerItem(0, 0, QSizePolicy.Policy.Minimum,
                        QSizePolicy.Policy.Expanding),
            rows, 0, 1, 2,
        )

    def _on_remove(self, index: int) -> None:
        if 0 <= index < len(self._labels):
            del self._labels[index]
            self._rebuild()
            self.removeRequested.emit(index)
            self.changed.emit()


class MyTagsDialog(AppDialog):
    def __init__(self, labels: list[str], tr, parent=None,
                 tokens: dict[str, str] | None = None) -> None:
        super().__init__(tokens, parent)
        self._tr = tr
        self._tokens = tokens or LIGHT
        self._labels = [label for label in labels if label][:MAX_CUSTOM_LABELS]
        self._skipped = 0

        self.setWindowTitle(tr("my_tags.title"))
        self.resize(560, 520)
        self.setMinimumSize(520, 440)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(note_label(tr("my_tags.lede")))

        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(section_label(tr("my_tags.list_title")))
        head.addStretch(1)
        self._import_btn = QPushButton(tr("my_tags.import"))
        self._export_btn = QPushButton(tr("my_tags.export"))
        for button in (self._import_btn, self._export_btn):
            button.setObjectName("InlineLink")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFixedHeight(20)
            button.setMinimumWidth(0)
            button.setStyleSheet(
                "QPushButton#InlineLink { background: transparent; border: none; "
                f"color: {self._tokens['ink_3']}; font-size: 11px; padding: 0; "
                "min-width: 0; min-height: 0; }"
                f"QPushButton#InlineLink:hover {{ color: {self._tokens['accent']}; }}"
            )
            head.addWidget(button)
        layout.addLayout(head)

        add_row = QHBoxLayout()
        add_row.setSpacing(8)
        self._input = QLineEdit()
        self._input.setObjectName("FieldInput")
        self._input.setFixedHeight(34)
        self._input.setMaxLength(MAX_LABEL_LENGTH * 4)
        self._input.setPlaceholderText(tr("my_tags.placeholder"))
        self._input.setAccessibleName(tr("my_tags.placeholder"))
        self._add_btn = dialog_button(tr("my_tags.add"), "ghost")
        self._add_btn.setFixedWidth(84)
        add_row.addWidget(self._input, 1)
        add_row.addWidget(self._add_btn)
        layout.addLayout(add_row)

        meta = QHBoxLayout()
        meta.setSpacing(8)
        self._hint = QLabel(tr("my_tags.hint"))
        self._hint.setObjectName("Hint")
        meta.addWidget(self._hint)
        meta.addStretch(1)
        self._count = QLabel()
        self._count.setObjectName("Hint")
        meta.addWidget(self._count)
        layout.addLayout(meta)

        self._grid = _TagGrid(tr, self._tokens, self)
        self._grid.set_labels(self._labels)
        layout.addWidget(self._grid, 1)

        rule = QFrame()
        rule.setObjectName("DialogRule")
        rule.setFixedHeight(1)
        layout.addWidget(rule)
        layout.addWidget(note_label(tr("my_tags.note")))

        footer = QHBoxLayout()
        footer.setSpacing(10)
        self._foot_note = QLabel(tr("my_tags.foot_note"))
        self._foot_note.setObjectName("Hint")
        footer.addWidget(self._foot_note)
        footer.addStretch(1)
        self._cancel_btn = dialog_button(tr("settings.cancel"))
        self._save_btn = dialog_button(tr("settings.save"), "primary")
        footer.addWidget(self._cancel_btn)
        footer.addWidget(self._save_btn)
        layout.addLayout(footer)

        self._input.returnPressed.connect(self._add)
        self._add_btn.clicked.connect(self._add)
        self._import_btn.clicked.connect(self._import)
        self._export_btn.clicked.connect(self._export)
        self._cancel_btn.clicked.connect(self.reject)
        self._save_btn.clicked.connect(self.accept)
        self._grid.changed.connect(self._refresh_state)
        self._grid.moveRequested.connect(self._move)
        self._refresh_state()

    # -- editing ---------------------------------------------------------

    def labels(self) -> list[str]:
        return self._grid.labels()

    def _add(self) -> None:
        incoming = parse_custom_labels(self._input.text())
        if not incoming:
            return
        merged, skipped = merge_custom_labels(self._grid.labels(), incoming)
        self._skipped += skipped
        self._grid.set_labels(merged)
        self._input.clear()
        self._refresh_state()
        self._input.setFocus()

    def _move(self, source: int, target: int) -> None:
        labels = self._grid.labels()
        if not (0 <= source < len(labels) and 0 <= target < len(labels)):
            return
        label = labels.pop(source)
        labels.insert(target, label)
        self._grid.set_labels(labels)

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self._tr("my_tags.import"), "", "TXT (*.txt);;All files (*)"
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return
        merged, skipped = merge_custom_labels(
            self._grid.labels(), parse_custom_labels(text)
        )
        self._skipped += skipped
        self._grid.set_labels(merged)
        self._refresh_state()

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, self._tr("my_tags.export"), "my-tags.txt", "TXT (*.txt)"
        )
        if not path:
            return
        try:
            Path(path).write_text("\n".join(self._grid.labels()), encoding="utf-8")
        except OSError:
            return

    def _refresh_state(self) -> None:
        labels = self._grid.labels()
        full = len(labels) >= MAX_CUSTOM_LABELS
        self._input.setEnabled(not full)
        self._add_btn.setEnabled(not full)
        if full:
            self._input.setPlaceholderText(self._tr("my_tags.limit_reached"))
        else:
            self._input.setPlaceholderText(self._tr("my_tags.placeholder"))
        self._count.setText(
            self._tr("my_tags.count", n=len(labels), max=MAX_CUSTOM_LABELS)
        )
        self._count.setStyleSheet(
            f"color: {self._tokens['red']};" if full else ""
        )
        self._save_btn.setEnabled(True)