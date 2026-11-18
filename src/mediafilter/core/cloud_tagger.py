"""Cloud content tagging over an OpenAI-compatible vision endpoint.

Frames are pulled through an ``ffmpeg`` pipe as JPEG (no temp files), sent as
``image_url`` data URLs in a chat request, and the answer is constrained to a
closed label set. Several frames vote, exactly like the local tagger. Pure
stdlib + subprocess so it is testable without Qt.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

from .cloud_models import CloudModelError, chat_completion, normalize_base_url
from .tagger import TagResult, aggregate_tags, frame_timestamps

JPEG_MAX_SIDE = 768
JPEG_QUALITY = 3                 # ffmpeg -q:v, 2 (best) .. 31 (worst)
DEFAULT_TIMEOUT = 60.0
MAX_ERROR_TEXT = 160


@dataclass(frozen=True)
class CloudTagConfig:
    base_url: str
    api_key: str
    model: str
    labels: list[str]
    timeout: float = DEFAULT_TIMEOUT


def cloud_model_id(mode: str, base_url: str, model: str, labels: list[str]) -> str:
    """Cache identity: mode + endpoint + model + the exact label set."""
    digest = hashlib.sha1("|".join(labels).encode("utf-8")).hexdigest()[:10]
    base = normalize_base_url(base_url)
    return f"cloud:{mode}:{base}:{model}:{digest}"


def extract_jpeg(
    ffmpeg: str,
    path: str | Path,
    timestamp: float,
    max_side: int = JPEG_MAX_SIDE,
    timeout: float = 20.0,
) -> bytes | None:
    """One frame as JPEG bytes; aspect preserved, never upscaled."""
    vf = (
        f"scale='min({max_side},iw)':'min({max_side},ih)':"
        "force_original_aspect_ratio=decrease"
    )
    cmd = [
        ffmpeg, "-v", "error", "-nostdin", "-ss", f"{timestamp:.3f}",
        "-i", str(path), "-frames:v", "1", "-vf", vf,
        "-q:v", str(JPEG_QUALITY), "-f", "image2pipe", "-vcodec", "mjpeg", "-",
    ]
    startupinfo = None
    if hasattr(subprocess, "STARTUPINFO"):   # Windows: no console flash per frame
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout, startupinfo=startupinfo)
    except (OSError, subprocess.TimeoutExpired):
        return None
    data = proc.stdout
    if not data.startswith(b"\xff\xd8"):
        return None
    return data


def build_messages(
    labels: list[str],
    image_data_url: str,
    context_tags: list[str] | None = None,
) -> list[dict]:
    """Closed-set prompt: the model may only answer with these labels."""
    lines = [
        "You label one video frame for a media library.",
        "Choose only from the allowed labels below; never invent a label.",
        "",
        "Allowed labels:",
    ]
    lines += [f"- {label}" for label in labels]
    if context_tags:
        lines += [
            "",
            "A local model already saw these in this video (context only):",
            "- " + ", ".join(context_tags),
        ]
    lines += [
        "",
        'Reply with JSON only: {"labels": ["label"]}.',
        'If nothing matches, reply {"labels": []}. Do not explain.',
    ]
    return [
        {"role": "system", "content": "You are a precise frame tagger. Output JSON only."},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "\n".join(lines)},
                {"type": "image_url", "image_url": {"url": image_data_url}},
            ],
        },
    ]


def parse_labels(text: str, allowed: list[str]) -> list[str]:
    """Extract labels from a model answer, keeping only the allowed set."""
    payload = _extract_json(text)
    raw: object = []
    if isinstance(payload, dict):
        raw = payload.get("labels", payload.get("tags", []))
    elif isinstance(payload, list):
        raw = payload
    if not isinstance(raw, list):
        return []

    wanted = {label.casefold(): label for label in allowed}
    found: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        key = " ".join(item.split()).strip().strip('"').casefold()
        label = wanted.get(key)
        if label is not None:
            found.add(label)
    return [label for label in allowed if label in found]


def _extract_json(text: str) -> object:
    text = text.strip()
    for candidate in (text, _fenced(text)):
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return None


def _fenced(text: str) -> str:
    match = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    return match.group(1).strip() if match else ""


def safe_error(exc: BaseException, api_key: str = "") -> str:
    """Short, key-free error text for the table and status bar."""
    text = str(exc) or type(exc).__name__
    if api_key:
        text = text.replace(api_key, "***")
    text = " ".join(text.split())
    return text if len(text) <= MAX_ERROR_TEXT else text[:MAX_ERROR_TEXT] + "…"


def cloud_tag_video(
    ffmpeg: str,
    path: str | Path,
    duration: float,
    config: CloudTagConfig,
    sample_count: int = 3,
    context_tags: list[str] | None = None,
    cancel_event: threading.Event | None = None,
) -> TagResult:
    """Sample frames, ask the cloud model for each, and vote on labels."""
    stamps = frame_timestamps(duration, sample_count)
    if not stamps:
        return TagResult(error="duration unknown")

    votes: dict[str, int] = {}
    errors: list[str] = []
    sampled = 0
    for stamp in stamps:
        if cancel_event is not None and cancel_event.is_set():
            break
        jpeg = extract_jpeg(ffmpeg, path, stamp)
        if jpeg is None:
            errors.append("抽帧失败")
            continue
        data_url = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
        messages = build_messages(config.labels, data_url, context_tags)
        try:
            answer = chat_completion(
                config.base_url, config.api_key, config.model, messages,
                timeout=config.timeout,
            )
        except CloudModelError as exc:
            errors.append(safe_error(exc, config.api_key))
            continue
        sampled += 1
        for label in parse_labels(answer, config.labels):
            votes[label] = votes.get(label, 0) + 1

    if sampled == 0:
        if cancel_event is not None and cancel_event.is_set():
            return TagResult(frames=0)
        return TagResult(error=errors[0] if errors else "云端识别没有返回结果")
    return TagResult(
        tags=aggregate_tags(votes, sampled),
        frames=sampled,
        detections=sum(votes.values()),
    )