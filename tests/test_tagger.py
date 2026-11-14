import numpy as np

from mediafilter.core.tagger import (
    COCO_NAMES,
    ZH_TAGS,
    aggregate_tags,
    decode_yolo,
    frame_timestamps,
)


def test_frame_timestamps_evenly_spaced_inside_duration():
    assert frame_timestamps(10, 3) == [2.5, 5.0, 7.5]
    assert frame_timestamps(0, 3) == []
    assert frame_timestamps(10, 0) == []


def test_aggregate_tags_keeps_majority_and_orders_by_votes():
    votes = {"人物": 3, "屏幕": 2, "狗": 1}
    assert aggregate_tags(votes, 3) == ["人物", "屏幕"]


def test_aggregate_tags_falls_back_to_best_single_observation():
    assert aggregate_tags({"猫": 1, "狗": 1}, 3) in (["猫"], ["狗"])


def test_aggregate_tags_empty():
    assert aggregate_tags({}, 3) == []


def test_every_coco_class_has_a_chinese_tag():
    missing = [name for name in COCO_NAMES if name not in ZH_TAGS]
    assert missing == []


def test_decode_yolo_reads_box_and_class():
    out = np.zeros((1, 84, 8400), dtype=np.float32)
    # one anchor at (320, 320), 100x100, high score for class 0 (person)
    out[0, 0, 0], out[0, 1, 0], out[0, 2, 0], out[0, 3, 0] = 320, 320, 100, 100
    out[0, 4, 0] = 0.9
    dets = decode_yolo(out)
    assert len(dets) == 1
    assert dets[0].class_id == 0
    assert dets[0].name == "person"
    assert dets[0].score > 0.85


def test_decode_yolo_empty_when_below_threshold():
    out = np.zeros((1, 84, 8400), dtype=np.float32)
    out[0, 4, :] = 0.05
    assert decode_yolo(out) == []