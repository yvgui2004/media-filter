"""Sort/filter proxy: click-to-sort + name search + format filter."""

from __future__ import annotations

from PySide6.QtCore import QSortFilterProxyModel, Qt

from .table_model import SORT_ROLE


class FilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._formats: set[str] = set()
        self._tags: set[str] = set()
        self._search = ""
        self.setSortRole(SORT_ROLE)
        self.setDynamicSortFilter(True)
        self.setSortCaseSensitivity(Qt.CaseInsensitive)

    def set_formats(self, formats: set[str]) -> None:
        """Empty set means 'all formats'."""
        self._begin_change()
        self._formats = set(formats)
        self._end_change()

    def set_tags(self, tags: set[str]) -> None:
        """Empty set means 'any tag'. Matches files carrying any selected tag."""
        self._begin_change()
        self._tags = set(tags)
        self._end_change()

    def set_search(self, text: str) -> None:
        self._begin_change()
        self._search = (text or "").strip()
        self._end_change()

    def _begin_change(self) -> None:
        # Qt 6.10 deprecates invalidateFilter(); begin/endFilterChange is the
        # replacement, but the project still supports PySide6 6.6.
        begin = getattr(self, "beginFilterChange", None)
        if begin is not None:
            begin()

    def _end_change(self) -> None:
        end = getattr(self, "endFilterChange", None)
        if end is not None:
            end(QSortFilterProxyModel.Direction.Rows)
        else:
            self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent) -> bool:
        model = self.sourceModel()
        record = model.record(source_row)
        if self._formats and record.extension not in self._formats:
            return False
        if self._tags and not (self._tags & set(record.tags)):
            return False
        if self._search:
            needle = self._search.lower()
            if needle not in record.name.lower() and not any(needle in t.lower() for t in record.tags):
                return False
        return True