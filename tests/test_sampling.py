"""Frame-intensity policy: one resolver for the run and the confirm card."""

from __future__ import annotations

from mediafilter.core.sampling import (
    AUTO_LONG_SECONDS,
    FAST_FRAMES,
    FINE_LONG_SECONDS,
    normalize_policy,
    sample_count,
    sample_counts,
    total_frames,
)


def test_fast_is_a_fixed_light_sample():
    assert sample_count("fast", 0) == FAST_FRAMES
    assert sample_count("fast", 9999) == FAST_FRAMES


def test_auto_splits_short_and_long_videos():
    assert sample_count("auto", 30) == 6
    assert sample_count("auto", AUTO_LONG_SECONDS - 1) == 6
    assert sample_count("auto", AUTO_LONG_SECONDS) == 8
    assert sample_count("auto", 240) == 8


def test_fine_splits_short_and_long_videos():
    assert sample_count("fine", 30) == 12
    assert sample_count("fine", FINE_LONG_SECONDS - 1) == 12
    assert sample_count("fine", FINE_LONG_SECONDS) == 16


def test_unknown_policy_falls_back_to_auto():
    assert sample_count("legacy", 30) == 6
    assert sample_count("", 240) == 8


def test_unknown_worker_policy_means_auto_not_the_legacy_count():
    assert normalize_policy("legacy") == "auto"
    assert normalize_policy("") == "auto"
    assert normalize_policy("fine") == "fine"
    assert normalize_policy(None) is None      # explicit legacy path


def test_lists_and_totals_use_each_videos_duration():
    durations = [30, 240, 700]
    assert sample_counts(durations, "auto") == [6, 8, 8]
    assert total_frames(durations, "auto") == 22
    assert sample_counts(durations, "fine") == [12, 12, 16]
    assert total_frames(durations, "fine") == 40