"""Bottom stats bar: file count, checked count, total duration, total size."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel

from ..core.formats import format_duration, format_size
from ..core.models import FileRecord


class StatsBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(18)

        self._files = QLabel()
        self._selected = QLabel()
        self._duration = QLabel()
        self._size = QLabel()

        layout.addWidget(self._files)
        layout.addWidget(self._selected)
        layout.addWidget(self._duration)
        layout.addWidget(self._size)
        layout.addStretch(1)

        self._actions = QHBoxLayout()
        self._actions.setSpacing(8)
        layout.addLayout(self._actions)

        self._tr = None
        self._total = 0
        self._checked: list[FileRecord] = []

    def add_action(self, button) -> None:
        """Append a right-aligned action button (export / batch / convert)."""
        self._actions.addWidget(button)

    def set_tr(self, tr) -> None:
        self._tr = tr
        self._refresh()

    def set_stats(self, total_files: int, checked: list[FileRecord]) -> None:
        self._total = total_files
        self._checked = checked
        self._refresh()

    def _refresh(self) -> None:
        if self._tr is None:
            return
        size = sum(r.size for r in self._checked)
        duration = sum(r.duration for r in self._checked)
        self._files.setText(self._tr("stat.files", n=self._total))
        self._selected.setText(self._tr("stat.selected", n=len(self._checked)))
        self._duration.setText(self._tr("stat.duration", d=format_duration(duration)))
        self._size.setText(self._tr("stat.size", s=format_size(size)))