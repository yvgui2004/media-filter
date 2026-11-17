"""Built-in recognition vocabulary and user-label parsing.

The built-in set is a small open vocabulary the local model (and later the
cloud prompt) can hit without any configuration. The user's own labels are a
closed set kept separately in ``Config.custom_labels``; they are generic on
purpose — "踢足球", "露营", "王者荣耀" all work.
"""

from __future__ import annotations

MAX_CUSTOM_LABELS = 10
MAX_LABEL_LENGTH = 20

#: (group i18n key, tag ids) — 3 + 9 + 6 + 4 + 4 = 26 tags, all enabled by default.
TAG_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("taggroup.people", ("person", "crowd", "face")),
    ("taggroup.object", ("mic", "headphones", "computer", "phone", "screen",
                         "food", "cat", "dog", "car")),
    ("taggroup.scene", ("indoor", "outdoor", "night", "nature", "city", "street")),
    ("taggroup.shot", ("closeup", "medium", "wide", "aerial")),
    ("taggroup.tech", ("vertical", "screencap", "gameplay", "animation")),
)

ALL_TAG_IDS: tuple[str, ...] = tuple(
    tag for _, tags in TAG_GROUPS for tag in tags
)

DEFAULT_ENABLED: tuple[str, ...] = ALL_TAG_IDS

#: Chinese fallback names; the UI normally asks the translator for ``tag.<id>``.
TAG_FALLBACK_NAMES: dict[str, str] = {
    "person": "人", "crowd": "多人", "face": "人脸特写",
    "mic": "麦克风", "headphones": "耳机", "computer": "电脑", "phone": "手机",
    "screen": "屏幕", "food": "食物", "cat": "猫", "dog": "狗", "car": "车",
    "indoor": "室内", "outdoor": "室外", "night": "夜景", "nature": "自然",
    "city": "城市", "street": "街道",
    "closeup": "特写", "medium": "近景", "wide": "远景", "aerial": "航拍",
    "vertical": "竖屏", "screencap": "录屏", "gameplay": "游戏画面",
    "animation": "动画",
}

GROUP_FALLBACK_NAMES: dict[str, str] = {
    "taggroup.people": "人物",
    "taggroup.object": "物体",
    "taggroup.scene": "场景",
    "taggroup.shot": "画面",
    "taggroup.tech": "技术",
}

_DELIMITERS = ",，、;；\n\r\t"


def tag_label(tr, tag_id: str) -> str:
    """Translate a built-in tag id with a Chinese fallback."""
    key = f"tag.{tag_id}"
    text = tr(key)
    return TAG_FALLBACK_NAMES.get(tag_id, tag_id) if text == key else text


def group_label(tr, group_key: str) -> str:
    text = tr(group_key)
    return GROUP_FALLBACK_NAMES.get(group_key, group_key) if text == group_key else text


def parse_custom_labels(text: str) -> list[str]:
    """Split a free-form line into labels; also handles a pasted TXT blob.

    Delimiters cover English/Chinese commas, enumeration commas, semicolons
    and newlines. Labels are trimmed, de-duplicated case-insensitively (first
    spelling wins) and truncated to :data:`MAX_LABEL_LENGTH` characters.
    """
    result: list[str] = []
    seen: set[str] = set()
    for chunk in _split(text):
        label = chunk.strip().strip("。.").strip()
        if not label:
            continue
        label = label[:MAX_LABEL_LENGTH]
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(label)
        if len(result) >= MAX_CUSTOM_LABELS:
            break
    return result


def _split(text: str) -> list[str]:
    pieces: list[str] = [text]
    for delimiter in _DELIMITERS:
        next_pieces: list[str] = []
        for piece in pieces:
            next_pieces.extend(piece.split(delimiter))
        pieces = next_pieces
    return pieces


def merge_custom_labels(existing: list[str], incoming: list[str]) -> tuple[list[str], int]:
    """Append labels up to the cap; returns (merged, skipped_duplicates)."""
    merged = list(existing)
    seen = {label.casefold() for label in merged}
    skipped = 0
    for label in incoming:
        if len(merged) >= MAX_CUSTOM_LABELS:
            break
        key = label.casefold()
        if key in seen:
            skipped += 1
            continue
        seen.add(key)
        merged.append(label[:MAX_LABEL_LENGTH])
    return merged, skipped