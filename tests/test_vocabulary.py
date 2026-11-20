from __future__ import annotations

from mediafilter.config import Config
from mediafilter.core.vocabulary import (
    ALL_TAG_IDS, DEFAULT_ENABLED, MAX_CUSTOM_LABELS, TAG_FALLBACK_NAMES,
    TAG_GROUPS, merge_custom_labels, parse_custom_labels,
)


def test_builtin_tag_set_is_twenty_six_and_unique():
    assert len(ALL_TAG_IDS) == 26
    assert len(set(ALL_TAG_IDS)) == 26
    assert set(ALL_TAG_IDS) == set(DEFAULT_ENABLED)
    assert set(ALL_TAG_IDS) == set(TAG_FALLBACK_NAMES)
    assert sum(len(tags) for _, tags in TAG_GROUPS) == 26


def test_groups_match_the_design():
    sizes = {group: len(tags) for group, tags in TAG_GROUPS}
    assert sizes == {
        "taggroup.people": 3,
        "taggroup.object": 9,
        "taggroup.scene": 6,
        "taggroup.shot": 4,
        "taggroup.tech": 4,
    }


def test_parse_custom_labels_handles_all_delimiters():
    text = " 踢足球、篮球 ，王者荣耀\n露营；做饭 "
    assert parse_custom_labels(text) == ["踢足球", "篮球", "王者荣耀", "露营", "做饭"]


def test_parse_custom_labels_dedupes_case_insensitively():
    assert parse_custom_labels("Cat, cat, CAT, 猫") == ["Cat", "猫"]


def test_parse_custom_labels_truncates_and_caps():
    labels = parse_custom_labels("，".join(str(i) for i in range(20)))
    assert len(labels) == MAX_CUSTOM_LABELS == 10
    long_label = parse_custom_labels("x" * 40)[0]
    assert len(long_label) == 20


def test_merge_custom_labels_reports_duplicates_and_cap():
    merged, skipped = merge_custom_labels(
        ["王者荣耀"], ["王者荣耀", "三角洲", "王者荣耀"]
    )
    assert merged == ["王者荣耀", "三角洲"]
    assert skipped == 2

    merged, skipped = merge_custom_labels(
        [f"标签{i}" for i in range(9)], ["新一", "新二", "新三"]
    )
    assert len(merged) == 10
    assert merged[-1] == "新一"
    assert skipped == 0


def test_parse_strips_trailing_full_stop():
    assert parse_custom_labels("露营。") == ["露营"]


def test_config_defaults_for_recognition():
    cfg = Config()
    assert cfg.recognition_mode == "local"
    assert cfg.custom_labels == []
    assert cfg.tag_palette == []
    assert cfg.frame_policy == "auto"
    assert cfg.upload_target_only is True
    assert cfg.first_run_done is False
    assert cfg.first_run_prompted is False
    assert cfg.guide_dismissed is False

def test_config_saves_back_to_the_loaded_path(tmp_path):
    import json

    path = tmp_path / "config.json"
    cfg = Config.load(path)
    cfg.language = "en"
    cfg.save()
    assert json.loads(path.read_text(encoding="utf-8"))["language"] == "en"
