from pathlib import Path

from mediafilter.core.models import FileRecord
from mediafilter.ui.filter_proxy import FilterProxyModel
from mediafilter.ui.table_model import FileRecordModel


def _rec(name, tags=()):
    return FileRecord(
        path=Path(name), name=name, extension=name.rsplit(".", 1)[-1],
        size=1, tags=list(tags),
    )


def _proxy(records):
    model = FileRecordModel()
    model.set_records(records)
    proxy = FilterProxyModel()
    proxy.setSourceModel(model)
    return proxy


def test_tag_filter_matches_any_selected_tag():
    proxy = _proxy([_rec("a.mp4", ["人物"]), _rec("b.mp4", ["屏幕"]), _rec("c.mp4")])
    assert proxy.rowCount() == 3
    proxy.set_tags({"人物"})
    assert proxy.rowCount() == 1
    proxy.set_tags(set())
    assert proxy.rowCount() == 3


def test_search_matches_tags_too():
    proxy = _proxy([_rec("clip.mp4", ["屏幕"]), _rec("other.mp4", ["人物"])])
    proxy.set_search("屏幕")
    assert proxy.rowCount() == 1
    proxy.set_search("clip")
    assert proxy.rowCount() == 1
