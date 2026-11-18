"""Cloud model discovery and image-capability probing.

Pure stdlib: the settings dialog can ask an OpenAI-compatible endpoint for its
model list, turn ``modalities`` metadata into image / text / unknown, and (for
models without metadata) verify image input with a tiny generated PNG.  No API
key is ever logged; HTTP errors are reduced to a short status message.
"""

from __future__ import annotations

import base64
import json
import struct
import urllib.error
import urllib.request
import zlib
from dataclasses import dataclass, replace

USER_AGENT = "MediaFilter/0.1"
DEFAULT_TIMEOUT = 12.0
PROBE_TIMEOUT = 45.0

IMAGE = "image"
TEXT = "text"
UNKNOWN = "unknown"
VERIFIED_IMAGE = "verified_image"


class CloudModelError(RuntimeError):
    """A short, user-safe error; never contains the API key."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class ModelInfo:
    id: str
    name: str
    vendor: str = ""
    context: str = ""
    capability: str = UNKNOWN       # image | text | unknown
    recommended: bool = False

    @property
    def is_custom(self) -> bool:
        return self.vendor == "custom"


@dataclass(frozen=True)
class ProbeResult:
    capability: str                 # verified_image | text | unknown
    detail: str = ""


def normalize_base_url(url: str) -> str:
    """Accept ``host`` / ``host/v1`` / a full chat URL and return a base."""
    text = (url or "").strip().rstrip("/")
    if not text:
        return ""
    if not text.startswith(("http://", "https://")):
        text = "https://" + text
    for suffix in ("/chat/completions", "/models"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].rstrip("/")
    return text


def models_urls(base_url: str) -> list[str]:
    base = normalize_base_url(base_url)
    if not base:
        return []
    if base.endswith("/v1"):
        return [f"{base}/models"]
    return _unique([f"{base}/models", f"{base}/v1/models"])


def chat_urls(base_url: str) -> list[str]:
    base = normalize_base_url(base_url)
    if not base:
        return []
    if base.endswith("/v1"):
        return [f"{base}/chat/completions"]
    return _unique([
        f"{base}/chat/completions",
        f"{base}/v1/chat/completions",
    ])


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def list_models(
    base_url: str,
    api_key: str = "",
    timeout: float = DEFAULT_TIMEOUT,
) -> list[ModelInfo]:
    """Fetch and normalise ``GET {base}/models`` from a compatible API."""
    errors: list[str] = []
    for url in models_urls(base_url):
        try:
            payload = _request_json(url, api_key, timeout=timeout)
        except CloudModelError as exc:
            if exc.status == 404:
                errors.append(str(exc))
                continue
            raise
        models = parse_models(payload)
        if models:
            return models
        errors.append("接口返回了空模型列表")
    if errors:
        raise CloudModelError(errors[-1])
    raise CloudModelError("请填写 BASE URL")


def parse_models(payload: object) -> list[ModelInfo]:
    """Parse OpenAI-style ``{"data": [...]}`` and common variants."""
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        raw = payload.get("data", payload.get("models", []))
        items = raw if isinstance(raw, list) else []
    else:
        items = []

    models: list[ModelInfo] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or item.get("model") or "").strip()
        if not model_id or model_id in seen:
            continue
        if not _is_chat_model(item, model_id):
            continue
        seen.add(model_id)
        name = str(item.get("display_name") or item.get("name") or model_id).strip()
        if name == model_id:
            name = _pretty_name(model_id)
        vendor = str(item.get("owned_by") or item.get("provider") or "").strip()
        if not vendor and "/" in model_id:
            vendor = model_id.split("/", 1)[0]
        context = _format_context(
            item.get("context_length")
            or item.get("context_window")
            or item.get("max_context_length")
            or item.get("max_input_tokens")
        )
        models.append(ModelInfo(
            id=model_id,
            name=name,
            vendor=vendor,
            context=context,
            capability=capability_from_metadata(item),
        ))

    models.sort(key=lambda model: (
        {IMAGE: 0, UNKNOWN: 1, TEXT: 2}.get(model.capability, 1),
        model.name.lower(),
        model.id,
    ))
    first_image = next((m for m in models if m.capability == IMAGE), None)
    if first_image is not None:
        models = [
            replace(m, recommended=(m.id == first_image.id)) if m.capability == IMAGE else m
            for m in models
        ]
    return models


def capability_from_metadata(item: dict) -> str:
    """Derive image / text / unknown from optional provider metadata."""
    inputs = _input_modalities(item)
    if inputs:
        lowered = {str(value).lower() for value in inputs}
        if "image" in lowered:
            return IMAGE
        if lowered and lowered <= {"text"}:
            return TEXT
        if "text" in lowered and "image" not in lowered:
            return TEXT

    vision = _vision_flag(item)
    if vision is True:
        return IMAGE
    if vision is False:
        return TEXT
    return UNKNOWN


def _input_modalities(item: dict) -> list[str]:
    values: list[str] = []

    with_modalities = item.get("modalities")
    if isinstance(with_modalities, dict):
        raw = with_modalities.get("input")
        if isinstance(raw, list):
            values.extend(str(value) for value in raw)
        elif isinstance(raw, str):
            values.append(raw)
    elif isinstance(with_modalities, list):
        values.extend(str(value) for value in with_modalities)

    architecture = item.get("architecture")
    if isinstance(architecture, dict):
        raw = architecture.get("input_modalities")
        if isinstance(raw, list):
            values.extend(str(value) for value in raw)

    capabilities = item.get("capabilities")
    if isinstance(capabilities, dict):
        raw = capabilities.get("input_modalities")
        if isinstance(raw, list):
            values.extend(str(value) for value in raw)

    raw = item.get("input_modalities")
    if isinstance(raw, list):
        values.extend(str(value) for value in raw)

    return _unique([value.lower() for value in values if value])


def _vision_flag(item: dict) -> bool | None:
    for key in ("vision", "supports_vision"):
        if isinstance(item.get(key), bool):
            return item[key]
    capabilities = item.get("capabilities")
    if isinstance(capabilities, dict) and isinstance(capabilities.get("vision"), bool):
        return bool(capabilities["vision"])
    return None


def _is_chat_model(item: dict, model_id: str) -> bool:
    endpoints = item.get("native_endpoints")
    if isinstance(endpoints, list) and endpoints:
        if not any(
            "chat/completions" in str(endpoint) or "/messages" in str(endpoint)
            for endpoint in endpoints
        ):
            return False
    lowered = model_id.lower()
    blocked = ("embedding", "embed-", "rerank", "whisper", "tts", "moderation")
    return not any(token in lowered for token in blocked)


def _pretty_name(model_id: str) -> str:
    tail = model_id.split("/")[-1]
    if tail.endswith("[1M]"):
        tail = tail[:-4].rstrip() + " [1M]"
    return tail.replace("-", " ").replace("_", " ").strip() or model_id


def _format_context(value: object) -> str:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return ""
    if number <= 0:
        return ""
    if number >= 1_000_000:
        text = f"{number / 1_000_000:.1f}".rstrip("0").rstrip(".")
        return f"{text}M"
    if number >= 1_000:
        text = f"{number / 1_000:.0f}"
        return f"{text}K"
    return str(number)


def make_probe_png() -> bytes:
    """96x96 white PNG with a black digit 7; used to test image input."""
    size = 96
    pixels = bytearray([255]) * (size * size * 3)
    glyph = (
        "11111",
        "00001",
        "00010",
        "00100",
        "01000",
        "01000",
        "01000",
    )
    scale = 10
    glyph_w = len(glyph[0]) * scale
    glyph_h = len(glyph) * scale
    left = (size - glyph_w) // 2
    top = (size - glyph_h) // 2
    for row, line in enumerate(glyph):
        for col, bit in enumerate(line):
            if bit != "1":
                continue
            for dy in range(scale):
                y = top + row * scale + dy
                for dx in range(scale):
                    x = left + col * scale + dx
                    offset = (y * size + x) * 3
                    pixels[offset:offset + 3] = b"\x00\x00\x00"

    rows = [
        b"\x00" + bytes(pixels[y * size * 3:(y + 1) * size * 3])
        for y in range(size)
    ]
    raw = b"".join(rows)
    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(raw, 9))
        + _png_chunk(b"IEND", b"")
    )


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def probe_vision(
    base_url: str,
    api_key: str,
    model: str,
    timeout: float = PROBE_TIMEOUT,
) -> ProbeResult:
    """Send a tiny image; distinguish unsupported / confirmed / inconclusive."""
    if not model:
        raise CloudModelError("请选择模型")
    png = make_probe_png()
    data_url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": "图中数字是几？只回答数字。"},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }],
        "max_tokens": 8,
        "temperature": 0,
        "stream": False,
    }
    if _needs_reasoning_none(base_url, model):
        payload["reasoning_effort"] = "none"

    last_error: CloudModelError | None = None
    for url in chat_urls(base_url):
        try:
            response = _request_json(url, api_key, payload=payload, timeout=timeout)
        except CloudModelError as exc:
            if exc.status == 404:
                last_error = exc
                continue
            if _is_unsupported_image_error(exc):
                return ProbeResult(TEXT, str(exc))
            raise
        content = _response_text(response)
        if "7" in content:
            return ProbeResult(VERIFIED_IMAGE, content[:80])
        return ProbeResult(
            UNKNOWN,
            "模型有响应，但没有确认图像内容" + (f"：{content[:48]}" if content else ""),
        )
    if last_error is not None:
        raise last_error
    raise CloudModelError("请填写 BASE URL")


def _needs_reasoning_none(base_url: str, model: str) -> bool:
    lowered = model.lower()
    return "deepseek" in lowered or "127.0.0.1:3425" in base_url


def chat_completion(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    timeout: float = 60.0,
    max_tokens: int = 200,
) -> str:
    """POST an OpenAI-style chat request and return the assistant text.

    The key only ever travels in the Authorization header; error messages
    are short and never echo it.
    """
    if not model:
        raise CloudModelError("请选择模型")
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream": False,
    }
    if _needs_reasoning_none(base_url, model):
        payload["reasoning_effort"] = "none"

    last_error: CloudModelError | None = None
    for url in chat_urls(base_url):
        try:
            response = _request_json(url, api_key, payload=payload, timeout=timeout)
        except CloudModelError as exc:
            if exc.status == 404:
                last_error = exc
                continue
            raise
        content = _response_text(response)
        if not content:
            raise CloudModelError("模型返回了空内容")
        return content
    if last_error is not None:
        raise last_error
    raise CloudModelError("请填写 BASE URL")


def _response_text(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return str(payload.get("output_text") or payload.get("text") or "")
    choice = choices[0] if isinstance(choices[0], dict) else {}
    raw_message = choice.get("message")
    message = raw_message if isinstance(raw_message, dict) else {}
    content = message.get("content", choice.get("text", ""))
    return _flatten_text(content).strip()


def _flatten_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or ""))
        return " ".join(part for part in parts if part)
    if isinstance(value, dict):
        return str(value.get("text") or "")
    return ""


def _is_unsupported_image_error(exc: CloudModelError) -> bool:
    text = str(exc).lower()
    if not any(token in text for token in ("image", "vision", "multimodal", "图片")):
        return False
    return any(token in text for token in (
        "not support", "unsupported", "invalid", "does not accept", "无法",
        "不支持", "invalid content", "image_url",
    ))


def _request_json(
    url: str,
    api_key: str,
    payload: dict | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> object:
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    data = None
    method = "GET"
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        detail = _http_error_text(exc)
        raise CloudModelError(
            f"HTTP {exc.code}" + (f"：{detail}" if detail else ""),
            status=exc.code,
        ) from exc
    except urllib.error.URLError as exc:
        reason = str(exc.reason) if getattr(exc, "reason", None) else str(exc)
        raise CloudModelError(f"无法连接：{reason}") from exc
    except TimeoutError as exc:
        raise CloudModelError("请求超时") from exc
    try:
        return json.loads(body.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise CloudModelError("接口返回的不是 JSON") from exc


def _http_error_text(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read(4000).decode("utf-8", errors="replace")
    except Exception:
        return ""
    try:
        parsed = json.loads(body)
        if isinstance(parsed, dict):
            error = parsed.get("error")
            if isinstance(error, dict):
                return str(error.get("message") or error.get("code") or "")[:240]
            if isinstance(error, str):
                return error[:240]
            message = parsed.get("message")
            if message:
                return str(message)[:240]
    except json.JSONDecodeError:
        pass
    return body[:240].replace("\n", " ").strip()