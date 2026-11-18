"""Resolve the user's frame-intensity policy into per-video sample counts.

The settings page exposes three levels; the same resolver feeds the local
tagger, the cloud worker and the upload-confirmation card so the number shown
there is the number of frames the run will actually try to sample.
"""

from __future__ import annotations

from collections.abc import Iterable

FRAME_POLICIES: tuple[str, ...] = ("fast", "auto", "fine")
DEFAULT_POLICY = "auto"

FAST_FRAMES = 4
AUTO_SHORT_FRAMES = 6
AUTO_LONG_FRAMES = 8
FINE_SHORT_FRAMES = 12
FINE_LONG_FRAMES = 16

#: Above this duration "auto" adds two frames; "fine" adds four.
AUTO_LONG_SECONDS = 120.0
FINE_LONG_SECONDS = 600.0


def sample_count(policy: str, duration: float) -> int:
    """Frames for one video under ``policy``.

    Unknown policies fall back to "auto" rather than silently using the old
    fixed count, so a stale config can never disable the setting again.
    """
    seconds = max(0.0, float(duration or 0.0))
    if policy == "fast":
        return FAST_FRAMES
    if policy == "fine":
        return FINE_LONG_FRAMES if seconds >= FINE_LONG_SECONDS else FINE_SHORT_FRAMES
    if seconds >= AUTO_LONG_SECONDS:
        return AUTO_LONG_FRAMES
    return AUTO_SHORT_FRAMES


def normalize_policy(policy: str | None) -> str | None:
    """Return a policy the workers can use.

    ``None`` keeps the legacy fixed-count path for callers that explicitly
    pass no policy; any other unknown value means "auto", matching the
    resolver used by the confirmation card.
    """
    if policy is None:
        return None
    return policy if policy in FRAME_POLICIES else DEFAULT_POLICY


def sample_counts(durations: Iterable[float], policy: str) -> list[int]:
    return [sample_count(policy, duration) for duration in durations]


def total_frames(durations: Iterable[float], policy: str) -> int:
    return sum(sample_counts(durations, policy))