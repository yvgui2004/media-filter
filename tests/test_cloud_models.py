"""Cloud model list parsing, capability metadata and probe classification."""

from __future__ import annotations

import struct

import pytest

from mediafilter.config import Config
from mediafilter.core import cloud_models, secret_store


def _model(model_id, **extra):
    item = {"id": model_id}
    item.update(extra)
    return item


def test_normalize_base_url_accepts_host_v1_and_chat_url():
    assert cloud_models.normalize_base_url("api.example.com/v1/") == (
        "https://api.example.com/v1"
    )
    assert cloud_models.normalize_base_url(
        "https://api.example.com/v1/chat/completions"
    ) == "https://api.example.com/v1"
    assert cloud_models.normalize_base_url("") == ""
    assert cloud_models.models_urls("https://api.example.com/v1") == [
        "https://api.example.com/v1/models"
    ]
    assert cloud_models.models_urls("https://api.example.com") == [
        "https://api.example.com/models",
        "https://api.example.com/v1/models",
    ]


def test_parse_models_reads_all_supported_metadata_shapes():
    models = cloud_models.parse_models({"data": [
        _model("qwen-cn/vision-a", modalities={"input": ["text", "image"]},
               context_length=1_000_000),
        _model("qwen-cn/vision-b",
               architecture={"input_modalities": ["image", "text"]}),
        _model("qwen-cn/vision-c", capabilities={"vision": True}),
        _model("qwen-cn/text-only", architecture={"input_modalities": ["text"]},
               context_length=256_000),
        _model("qwen-cn/unknown"),
        _model("qwen-cn/embedding", native_endpoints=["/v1/embeddings"]),
    ]})
    by_id = {model.id: model for model in models}
    assert len(models) == 5
    assert by_id["qwen-cn/vision-a"].capability == cloud_models.IMAGE
    assert by_id["qwen-cn/vision-a"].context == "1M"
    assert by_id["qwen-cn/vision-b"].capability == cloud_models.IMAGE
    assert by_id["qwen-cn/vision-c"].capability == cloud_models.IMAGE
    assert by_id["qwen-cn/text-only"].capability == cloud_models.TEXT
    assert by_id["qwen-cn/text-only"].context == "256K"
    assert by_id["qwen-cn/unknown"].capability == cloud_models.UNKNOWN
    assert "qwen-cn/embedding" not in by_id
    assert sum(model.recommended for model in models) == 1
    assert models[0].capability == cloud_models.IMAGE


def test_parse_models_deduplicates_and_reads_models_key():
    models = cloud_models.parse_models({"models": [
        _model("same", display_name="Friendly"),
        _model("same", display_name="Duplicate"),
        _model("other", provider="lab"),
    ]})
    assert [model.id for model in models] == ["same", "other"]
    assert models[0].name == "Friendly"
    assert models[1].vendor == "lab"


def test_list_models_falls_back_to_v1_models_on_404(monkeypatch):
    calls: list[str] = []

    def fake_request(url, api_key, payload=None, timeout=12.0):
        calls.append(url)
        if url.endswith("/models") and not url.endswith("/v1/models"):
            raise cloud_models.CloudModelError("HTTP 404", status=404)
        return {"data": [{"id": "local/model"}]}

    monkeypatch.setattr(cloud_models, "_request_json", fake_request)
    models = cloud_models.list_models("https://api.example.com", "key")
    assert [model.id for model in models] == ["local/model"]
    assert calls == [
        "https://api.example.com/models",
        "https://api.example.com/v1/models",
    ]


def test_make_probe_png_is_a_96px_png():
    png = cloud_models.make_probe_png()
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert png.endswith(b"IEND\xaeB`\x82")
    width, height = struct.unpack(">II", png[16:24])
    assert (width, height) == (96, 96)


def test_probe_vision_confirms_correct_answer(monkeypatch):
    def fake_request(url, api_key, payload=None, timeout=45.0):
        assert payload is not None
        assert payload["messages"][0]["content"][1]["image_url"]["url"].startswith(
            "data:image/png;base64,"
        )
        return {"choices": [{"message": {"content": "7"}}]}

    monkeypatch.setattr(cloud_models, "_request_json", fake_request)
    result = cloud_models.probe_vision(
        "https://api.example.com/v1", "key", "vision-model"
    )
    assert result.capability == cloud_models.VERIFIED_IMAGE


def test_probe_vision_marks_explicit_unsupported_as_text(monkeypatch):
    def fake_request(url, api_key, payload=None, timeout=45.0):
        raise cloud_models.CloudModelError(
            "HTTP 400：image_url is not supported by this model", status=400
        )

    monkeypatch.setattr(cloud_models, "_request_json", fake_request)
    result = cloud_models.probe_vision(
        "https://api.example.com/v1", "key", "text-model"
    )
    assert result.capability == cloud_models.TEXT


def test_probe_vision_does_not_call_wrong_answer_text_only(monkeypatch):
    def fake_request(url, api_key, payload=None, timeout=45.0):
        return {"choices": [{"message": {"content": "无法判断"}}]}

    monkeypatch.setattr(cloud_models, "_request_json", fake_request)
    result = cloud_models.probe_vision(
        "https://api.example.com/v1", "key", "uncertain-model"
    )
    assert result.capability == cloud_models.UNKNOWN


def test_config_roundtrip_keeps_cloud_fields(tmp_path):
    path = tmp_path / "config.json"
    config = Config()
    config.cloud_base_url = "https://example.test/v1"
    config.cloud_model = "lab/vision"
    config.cloud_model_capability = cloud_models.VERIFIED_IMAGE
    config.cloud_model_cache = {"https://example.test/v1|lab/vision|png": "verified_image"}
    config.save(path)
    loaded = Config.load(path)
    assert loaded.cloud_base_url == "https://example.test/v1"
    assert loaded.cloud_model == "lab/vision"
    assert loaded.cloud_model_capability == "verified_image"
    assert loaded.cloud_model_cache["https://example.test/v1|lab/vision|png"] == (
        "verified_image"
    )


@pytest.mark.skipif(not secret_store.is_available(), reason="Windows DPAPI only")
def test_secret_store_roundtrip_and_invalid_ciphertext():
    token = secret_store.protect("sk-test-1234")
    assert token != "sk-test-1234"
    assert secret_store.unprotect(token) == "sk-test-1234"
    assert secret_store.protect("") == ""
    assert secret_store.unprotect("") == ""
    assert secret_store.key_hint("sk-test-1234") == "1234"
    with pytest.raises(secret_store.SecretStoreError):
        secret_store.unprotect("not-base64")


def test_chat_completion_retries_without_a_rejected_reasoning_field(monkeypatch):
    payloads: list[dict] = []

    def fake_request(url, api_key, payload=None, timeout=12.0):
        payloads.append(dict(payload or {}))
        if "reasoning_effort" in (payload or {}):
            raise cloud_models.CloudModelError(
                "HTTP 400：unknown field reasoning_effort", status=400,
            )
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(cloud_models, "_request_json", fake_request)

    answer = cloud_models.chat_completion(
        "https://api.example.com/v1", "k", "deepseek-chat", [],
    )

    assert answer == "ok"
    assert payloads[0]["reasoning_effort"] == "none"
    assert "reasoning_effort" not in payloads[-1]