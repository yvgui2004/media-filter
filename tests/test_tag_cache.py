from pathlib import Path

from mediafilter.core.tag_cache import TagCache, cache_key


def test_cache_key_depends_on_identity_and_model():
    a = cache_key("C:/v/a.mp4", 100.0, 10, "m.onnx:1")
    assert a == cache_key("C:/v/a.mp4", 100.0, 10, "m.onnx:1")
    assert a != cache_key("C:/v/a.mp4", 101.0, 10, "m.onnx:1")
    assert a != cache_key("C:/v/a.mp4", 100.0, 11, "m.onnx:1")
    assert a != cache_key("C:/v/a.mp4", 100.0, 10, "m.onnx:2")


def test_cache_roundtrip(tmp_path: Path):
    path = tmp_path / "tags.json"
    cache = TagCache(path)
    cache.put("k1", ["人物", "屏幕"])
    cache.save()

    again = TagCache(path)
    assert again.get("k1") == ["人物", "屏幕"]
    assert again.get("missing") is None


def test_cache_survives_broken_file(tmp_path: Path):
    path = tmp_path / "tags.json"
    path.write_text("{not json", encoding="utf-8")
    cache = TagCache(path)
    assert cache.get("anything") is None
    cache.put("k", ["猫"])
    cache.save()