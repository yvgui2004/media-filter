from pathlib import Path

from PySide6.QtCore import Qt

from mediafilter.core.models import FileRecord
from mediafilter.ui.table_model import SORT_ROLE, FileRecordModel


def _rec(name: str, size: int = 100) -> FileRecord:
    return FileRecord(path=Path(name), name=name, extension=name.rsplit(".", 1)[-1], size=size)


def test_check_state_roundtrip_emits_signal():
    model = FileRecordModel()
    rec = _rec("a.mp4")
    model.set_records([rec])

    idx = model.index(0, FileRecordModel.COL_CHECK)
    assert model.data(idx, Qt.CheckStateRole) == Qt.Unchecked

    fired = []
    model.checkedChanged.connect(lambda: fired.append(1))

    # This is exactly what the view's delegate calls on a checkbox click.
    assert model.setData(idx, Qt.Checked, Qt.CheckStateRole) is True
    assert rec.checked is True
    assert model.checked_records() == [rec]
    assert fired, "setData should emit checkedChanged"


def test_sort_role_returns_numeric_for_size():
    model = FileRecordModel()
    model.set_records([_rec("a.mp4", size=12345)])
    idx = model.index(0, FileRecordModel.COL_SIZE)
    assert model.data(idx, SORT_ROLE) == 12345


def test_set_checked_bulk_updates_and_emits_once():
    model = FileRecordModel()
    model.set_records([_rec("a.mp4"), _rec("b.mp4")])
    fired = []
    model.checkedChanged.connect(lambda: fired.append(1))

    model.set_checked([0, 1], True)
    assert all(r.checked for r in model.records())
    assert len(fired) == 1