"""Qt model wrapping the flat list of FileRecord for the table view."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QColor

from ..core.formats import format_bitrate, format_duration, format_mtime, format_size
from ..core.models import FileRecord

# Role used by the sort proxy so numeric/name sorting matches DisplayRole text.
SORT_ROLE = Qt.UserRole + 1


class FileRecordModel(QAbstractTableModel):
    COL_CHECK = 0
    COL_NAME = 1
    COL_SIZE = 2
    COL_DURATION = 3
    COL_BITRATE = 4
    COL_FORMAT = 5
    COL_MTIME = 6
    N_COLS = 7

    checkedChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._records: list[FileRecord] = []
        self._headers = ["", "Name", "Size", "Duration", "Bitrate", "Format", "Modified"]

    # -- rows / columns --------------------------------------------------

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._records)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else self.N_COLS

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self._headers[section]
        return None

    def set_headers(self, headers: list[str]) -> None:
        self._headers = list(headers)
        self.headerDataChanged.emit(Qt.Horizontal, 0, self.N_COLS - 1)

    # -- record access ---------------------------------------------------

    def records(self) -> list[FileRecord]:
        return list(self._records)

    def record(self, row: int) -> FileRecord:
        return self._records[row]

    def set_records(self, records: list[FileRecord]) -> None:
        self.beginResetModel()
        self._records = records
        self.endResetModel()
        self.checkedChanged.emit()

    # -- data ------------------------------------------------------------

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        rec = self._records[index.row()]
        col = index.column()

        if col == self.COL_CHECK:
            if role == Qt.CheckStateRole:
                return Qt.Checked if rec.checked else Qt.Unchecked
            return None

        if role == Qt.DisplayRole:
            if col == self.COL_NAME:
                return rec.name
            if col == self.COL_SIZE:
                return format_size(rec.size)
            if col == self.COL_DURATION:
                return format_duration(rec.duration)
            if col == self.COL_BITRATE:
                return format_bitrate(rec.bitrate) or "—"
            if col == self.COL_FORMAT:
                return rec.extension.upper()
            if col == self.COL_MTIME:
                return format_mtime(rec.mtime) or "—"

        if role == SORT_ROLE:
            if col == self.COL_SIZE:
                return rec.size
            if col == self.COL_DURATION:
                return rec.duration
            if col == self.COL_BITRATE:
                return rec.bitrate
            if col == self.COL_NAME:
                return rec.name.lower()
            if col == self.COL_FORMAT:
                return rec.extension
            if col == self.COL_MTIME:
                return rec.mtime

        if role == Qt.TextAlignmentRole:
            if col in (self.COL_SIZE, self.COL_DURATION, self.COL_BITRATE, self.COL_MTIME):
                return int(Qt.AlignRight | Qt.AlignVCenter)
            return int(Qt.AlignLeft | Qt.AlignVCenter)

        if role == Qt.ToolTipRole:
            if col == self.COL_NAME:
                tip = str(rec.path)
                return f"{tip}\n{rec.error}" if rec.error else tip
            if rec.error and col in (self.COL_DURATION, self.COL_BITRATE):
                return rec.error

        if role == Qt.ForegroundRole and rec.error:
            return QColor("#e0533f")  # readable red on both light and dark rows

        return None

    def flags(self, index):
        # Deliberately NO Qt.ItemIsUserCheckable: the toggle is handled
        # explicitly by MainWindow._on_clicked. Leaving that flag on would let
        # the view's delegate also toggle the state, causing a double-flip.
        # The checkbox still renders because CheckStateRole is provided.
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def setData(self, index, value, role=Qt.EditRole):
        if index.column() == self.COL_CHECK and role == Qt.CheckStateRole:
            rec = self._records[index.row()]
            checked = value == Qt.Checked
            if rec.checked != checked:
                rec.checked = checked
                self.dataChanged.emit(index, index, [Qt.CheckStateRole])
                self.checkedChanged.emit()
            return True
        return False

    # -- check helpers ---------------------------------------------------

    def toggle_check(self, row: int) -> None:
        rec = self._records[row]
        rec.checked = not rec.checked
        idx = self.index(row, self.COL_CHECK)
        self.dataChanged.emit(idx, idx, [Qt.CheckStateRole])
        self.checkedChanged.emit()

    def set_checked(self, rows: list[int], checked: bool) -> None:
        changed = False
        for row in rows:
            rec = self._records[row]
            if rec.checked != checked:
                rec.checked = checked
                changed = True
        if changed:
            top = self.index(0, self.COL_CHECK)
            bottom = self.index(len(self._records) - 1, self.COL_CHECK)
            self.dataChanged.emit(top, bottom, [Qt.CheckStateRole])
            self.checkedChanged.emit()

    def checked_records(self) -> list[FileRecord]:
        return [r for r in self._records if r.checked]

    def remove_rows(self, rows: list[int]) -> None:
        for row in sorted(set(rows), reverse=True):
            self.beginRemoveRows(QModelIndex(), row, row)
            self._records.pop(row)
            self.endRemoveRows()
        self.checkedChanged.emit()