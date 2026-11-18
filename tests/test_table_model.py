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


def test_numeric_headers_follow_their_values_alignment():
    model = FileRecordModel()
    for col in (
        FileRecordModel.COL_SIZE,
        FileRecordModel.COL_DURATION,
        FileRecordModel.COL_BITRATE,
    ):
        align = model.headerData(col, Qt.Horizontal, Qt.TextAlignmentRole)
        assert isinstance(align, int)
        assert align & int(Qt.AlignRight)
    name_align = model.headerData(
        FileRecordModel.COL_NAME, Qt.Horizontal, Qt.TextAlignmentRole
    )
    assert isinstance(name_align, int)
    assert name_align & int(Qt.AlignLeft)


def test_set_checked_bulk_updates_and_emits_once():
    model = FileRecordModel()
    model.set_records([_rec("a.mp4"), _rec("b.mp4")])
    fired = []
    model.checkedChanged.connect(lambda: fired.append(1))

    model.set_checked([0, 1], True)
    assert all(r.checked for r in model.records())
    assert len(fired) == 1

def test_update_tags_sets_row_and_collects_all_tags():
    model = FileRecordModel()
    a, b = _rec("a.mp4"), _rec("b.mp4")
    model.set_records([a, b])

    assert model.update_tags(str(a.path), ["人物", "屏幕"]) is True
    assert a.tags == ["人物", "屏幕"]
    assert model.all_tags() == ["人物", "屏幕"]
    assert model.data(model.index(0, FileRecordModel.COL_TAGS), Qt.DisplayRole) == "人物, 屏幕"
    assert model.data(model.index(1, FileRecordModel.COL_TAGS), Qt.DisplayRole) == "—"

    # unknown path is ignored instead of raising
    assert model.update_tags("nope.mp4", ["猫"]) is False


def test_update_tags_records_error_for_tooltip():
    model = FileRecordModel()
    rec = _rec("a.mp4")
    model.set_records([rec])
    model.update_tags(str(rec.path), [], "no frames decoded")
    assert rec.ai_error == "no frames decoded"
    assert model.data(model.index(0, FileRecordModel.COL_TAGS), Qt.ToolTipRole) == "no frames decoded"
