"""Sort/filter proxy: click-to-sort + name search + format filter."""

from __future__ import annotations

from PySide6.QtCore import QSortFilterProxyModel, Qt

from .table_model import SORT_ROLE


class FilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._formats: set[str] = set()
        self._search = ""
        self.setSortRole(SORT_ROLE)
        self.setDynamicSortFilter(True)
        self.setSortCaseSensitivity(Qt.CaseInsensitive)

    def set_formats(self, formats: set[str]) -> None:
        """Empty set means 'all formats'."""
        self._formats = set(formats)
        self.invalidateFilter()

    def set_search(self, text: str) -> None:
        self._search = (text or "").strip()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent) -> bool:
        model = self.sourceModel()
        record = model.record(source_row)
        if self._formats and record.extension not in self._formats:
            return False
        if self._search and self._search.lower() not in record.name.lower():
            return False
        return True