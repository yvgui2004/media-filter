"""Local colour sampling for cat / dog / car detections.

The detector only returns a class and a box. This module crops the centre of
that box, converts the pixels to HSV with NumPy and returns a coarse colour
name. The tagger votes across frames, so one noisy frame cannot turn a grey
car into a black one.

No OpenCV dependency: the AI extra already requires NumPy, and the app must
still import cleanly on scan-only installs where NumPy is absent.
"""

# pyright: reportMissingImports=false, reportOptionalMemberAccess=false

from __future__ import annotations

import math
from dataclasses import dataclass

try:
    import numpy as np
except ImportError:  # pragma: no cover - scan-only installs
    np = None

#: Bump when the classifier or its thresholds change so disk caches expire.
COLOR_PALETTE_VERSION = "v1"

#: Built-in tag ids that can carry a colour prefix.
COLOR_BASE_IDS = frozenset({"cat", "dog", "car"})

#: COCO classes whose boxes make sense to sample. Bicycles and motorcycles are
#: mostly black frames / tyres, so they are deliberately excluded.
COLOR_COCO_CLASSES = frozenset({"cat", "dog", "car", "bus", "truck"})

COLOR_LABELS: dict[str, str] = {
    "black": "黑",
    "white": "白",
    "gray": "灰",
    "red": "红",
    "orange": "橙",
    "yellow": "黄",
    "green": "绿",
    "blue": "蓝",
    "purple": "紫",
    "pink": "粉",
    "brown": "棕",
}

# Numeric codes make the classifier a handful of vectorised masks instead of
# an object-dtype per-pixel loop.
_BLACK, _WHITE, _GRAY = 0, 1, 2
_RED, _ORANGE, _YELLOW, _GREEN, _BLUE = 3, 4, 5, 6, 7
_PURPLE, _PINK, _BROWN = 8, 9, 10

_CODE_KEYS: dict[int, str] = {
    _BLACK: "black",
    _WHITE: "white",
    _GRAY: "gray",
    _RED: "red",
    _ORANGE: "orange",
    _YELLOW: "yellow",
    _GREEN: "green",
    _BLUE: "blue",
    _PURPLE: "purple",
    _PINK: "pink",
    _BROWN: "brown",
}


@dataclass(frozen=True)
class ColorGuess:
    key: str
    share: float


def compose_color_label(base_label: str, color_key: str) -> str:
    """``"猫"`` + ``"black"`` -> ``"黑猫"``."""
    return f"{COLOR_LABELS[color_key]}{base_label}"


def classify_box(
    frame_rgb,
    box: tuple[float, float, float, float],
    kind: str = "animal",
) -> ColorGuess | None:
    """Sample the centre of a detection box and return its dominant colour.

    ``kind`` is ``"vehicle"`` for car / bus / truck and ``"animal"`` for cats
    and dogs. Vehicles use a narrower horizontal band: roofs, windows, wheels
    and road shadows otherwise dominate the histogram.
    """
    if np is None:
        return None
    crop = _crop(frame_rgb, box, kind)
    if crop is None or crop.size == 0:
        return None

    pixels = crop.reshape(-1, 3).astype(np.float32) / 255.0
    if pixels.shape[0] == 0:
        return None
    total = int(pixels.shape[0])
    hue, sat, val = _hsv(pixels)

    codes = np.zeros(total, dtype=np.int16)
    chroma = (sat >= 0.18) & (val >= 0.12)

    codes[chroma & ((hue < 15) | (hue >= 345))] = _RED
    codes[chroma & (hue >= 15) & (hue < 40)] = _ORANGE
    codes[chroma & (hue >= 40) & (hue < 70)] = _YELLOW
    codes[chroma & (hue >= 70) & (hue < 165)] = _GREEN
    codes[chroma & (hue >= 165) & (hue < 255)] = _BLUE
    codes[chroma & (hue >= 255) & (hue < 300)] = _PURPLE
    codes[chroma & (hue >= 300) & (hue < 345)] = _PINK
    # Brown is dark orange, not a separate hue family.
    codes[chroma & (hue >= 15) & (hue < 40) & (val < 0.55) & (sat > 0.25)] = _BROWN

    chroma_share = float(chroma.mean())
    weights = sat * val
    chroma_weights = weights[chroma]
    if chroma_share >= 0.35 and chroma_weights.size:
        counts = np.bincount(codes[chroma], weights=chroma_weights, minlength=11)
        best = int(np.argmax(counts[1:])) + 1
        best_share = float(counts[best] / max(float(chroma_weights.sum()), 1e-6))
        pixel_share = float((codes == best).sum() / total)
        if best_share >= 0.40 and pixel_share >= 0.18:
            return ColorGuess(_CODE_KEYS[best], pixel_share)

    # No stable chromatic body colour: fall back to black / white / grey.
    black = val < 0.20
    white = (val >= 0.82) & (sat < 0.18)
    gray = (sat < 0.18) & ~black & ~white
    shares = {
        _BLACK: float(black.mean()),
        _WHITE: float(white.mean()),
        _GRAY: float(gray.mean()),
    }
    best_code = max(shares, key=lambda code: shares[code])
    if shares[best_code] >= 0.45:
        return ColorGuess(_CODE_KEYS[best_code], shares[best_code])
    if shares[_WHITE] >= 0.35 and shares[_BLACK] < 0.30:
        return ColorGuess("white", shares[_WHITE])
    if shares[_BLACK] >= 0.35:
        return ColorGuess("black", shares[_BLACK])
    return None


def aggregate_color_tags(
    color_votes: dict[str, dict[str, int]],
    class_frames: dict[str, int],
    base_labels: list[str],
) -> list[str]:
    """Turn per-frame colour votes into stable colour tags.

    ``color_votes`` is ``{base label: {colour: frames}}`` and ``class_frames``
    counts how many frames contained that class. A colour must win at least
    half of the class frames (and at least two) before it is emitted.
    """
    tags: list[str] = []
    for base in base_labels:
        total = int(class_frames.get(base, 0))
        votes = color_votes.get(base) or {}
        if total < 2 or not votes:
            continue
        key, count = max(votes.items(), key=lambda item: (item[1], item[0]))
        needed = max(2, math.ceil(total / 2))
        if count >= needed and count / total >= 0.6:
            tags.append(compose_color_label(base, key))
    return tags


def _crop(frame_rgb, box, kind: str):
    if np is None or frame_rgb is None:
        return None
    if getattr(frame_rgb, "ndim", 0) != 3 or frame_rgb.shape[2] < 3:
        return None
    height, width = frame_rgb.shape[:2]
    x, y, bw, bh = (float(value) for value in box)
    if bw <= 0 or bh <= 0:
        return None

    if kind == "vehicle":
        x0, x1 = x + 0.15 * bw, x + 0.85 * bw
        y0, y1 = y + 0.30 * bh, y + 0.80 * bh
    else:
        x0, x1 = x + 0.15 * bw, x + 0.85 * bw
        y0, y1 = y + 0.12 * bh, y + 0.88 * bh

    left = max(0, min(width - 1, int(round(x0))))
    right = max(0, min(width, int(round(x1))))
    top = max(0, min(height - 1, int(round(y0))))
    bottom = max(0, min(height, int(round(y1))))
    if right - left < 4 or bottom - top < 4:
        return None

    crop = frame_rgb[top:bottom, left:right, :3]
    step = max(1, min(crop.shape[0], crop.shape[1]) // 48)
    return crop[::step, ::step]


def _hsv(pixels):
    """Vectorised RGB -> HSV, hue in degrees, all channels 0..1."""
    red, green, blue = pixels[:, 0], pixels[:, 1], pixels[:, 2]
    high = pixels.max(axis=1)
    low = pixels.min(axis=1)
    delta = high - low
    value = high
    sat = np.zeros_like(high)
    np.divide(delta, high, out=sat, where=high > 0)

    hue = np.zeros_like(high)
    nonzero = delta > 0
    safe = np.where(nonzero, delta, 1.0)

    mask = nonzero & (high == red)
    hue[mask] = ((green[mask] - blue[mask]) / safe[mask]) % 6.0
    mask = nonzero & (high == green)
    hue[mask] = (blue[mask] - red[mask]) / safe[mask] + 2.0
    mask = nonzero & (high == blue)
    hue[mask] = (red[mask] - green[mask]) / safe[mask] + 4.0
    hue *= 60.0
    return hue, sat, value