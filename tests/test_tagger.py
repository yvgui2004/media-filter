# numpy comes from the optional [ai] extra; skip type checking the import so a
# scan-only environment can still run pyright.
# pyright: reportMissingImports=false
import numpy as np

from mediafilter.core.tagger import (
    COCO_TO_TAG_ID,
    LOCAL_TAG_IDS,
    Detection,
    aggregate_tags,
    decode_yolo,
    frame_timestamps,
    tally_detections,
)
from mediafilter.core.vocabulary import ALL_TAG_IDS


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


def test_local_mapping_only_uses_builtin_tag_ids():
    assert set(COCO_TO_TAG_ID.values()) <= set(ALL_TAG_IDS)
    assert LOCAL_TAG_IDS == frozenset(COCO_TO_TAG_ID.values())
    assert COCO_TO_TAG_ID["person"] == "person"
    assert COCO_TO_TAG_ID["dog"] == "dog"
    assert COCO_TO_TAG_ID["pizza"] == "food"


def test_local_model_recognises_exactly_eight_tags():
    # README promises 8 local tags; scene / shot-size / technical tags stay
    # cloud-only, so adding a mapping here must update the docs too.
    assert LOCAL_TAG_IDS == frozenset({
        "person", "screen", "computer", "phone", "food", "cat", "dog", "car",
    })


def test_tally_detections_respects_enabled_tags():
    detections = [
        Detection(0, "person", 0.9, (0, 0, 10, 10)),
        Detection(16, "dog", 0.8, (0, 0, 10, 10)),
        Detection(2, "car", 0.7, (0, 0, 10, 10)),
        Detection(45, "bowl", 0.6, (0, 0, 10, 10)),
        Detection(14, "bird", 0.5, (0, 0, 10, 10)),
    ]
    assert tally_detections(detections) == {"人": 1, "狗": 1, "车": 1, "食物": 1}
    assert tally_detections(detections, {"person", "dog"}) == {"人": 1, "狗": 1}
    assert tally_detections(detections, set()) == {}


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