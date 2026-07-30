import json
import logging

import pytest

import providers as providers_module
from providers import (
    GeminiProvider,
    PROVIDERS,
    get_provider,
    providers_meta,
    validate_model,
)


class _InlineData:
    def __init__(self, data):
        self.data = data


class _Part:
    def __init__(self, inline_data=None):
        self.inline_data = inline_data


class _Content:
    def __init__(self, parts):
        self.parts = parts


class _Candidate:
    def __init__(self, parts):
        self.content = _Content(parts)


class _Usage:
    def __init__(self, prompt_tokens, candidates_tokens, total_tokens):
        self.prompt_token_count = prompt_tokens
        self.candidates_token_count = candidates_tokens
        self.total_token_count = total_tokens


class _FakeResponse:
    def __init__(self, image_bytes=b"PNGDATA", usage=None):
        self.candidates = [_Candidate([_Part(_InlineData(image_bytes))])]
        self.usage_metadata = usage


class _FakeModels:
    def __init__(self, response):
        self._response = response
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        return self._response


class _FakeClient:
    def __init__(self, response):
        self.models = _FakeModels(response)


def test_get_provider_returns_gemini_for_google():
    assert isinstance(get_provider("google"), GeminiProvider)


def test_get_provider_rejects_unknown_provider():
    with pytest.raises(ValueError, match="Unknown provider"):
        get_provider("openai")


def test_validate_model_accepts_known_models():
    validate_model("google", "gemini-2.5-flash-image")
    validate_model("google", "gemini-3-pro-image-preview")


def test_validate_model_rejects_unknown_model():
    with pytest.raises(ValueError, match="Unknown image model"):
        validate_model("google", "dall-e-3")


def test_validate_model_rejects_unknown_provider():
    with pytest.raises(ValueError, match="Unknown provider"):
        validate_model("openai", "gemini-2.5-flash-image")


def test_providers_meta_is_json_serializable_and_has_no_instances():
    meta = providers_meta()
    json.dumps(meta)  # raises TypeError if a provider instance leaked in
    assert meta["google"]["label"] == "Google (Gemini)"
    ids = [m["id"] for m in meta["google"]["image_models"]]
    assert ids == ["gemini-2.5-flash-image", "gemini-3-pro-image-preview"]


# --- PERF-9: client reuse ----------------------------------------------------

def test_generate_image_reuses_client_across_calls(monkeypatch):
    fake_client = _FakeClient(_FakeResponse())
    calls = []

    def fake_get_client():
        calls.append(1)
        return fake_client

    monkeypatch.setattr(providers_module, "get_client", fake_get_client)
    provider = GeminiProvider()

    provider.generate_image("prompt one", [], "model-x")
    provider.generate_image("prompt two", [], "model-x")

    assert len(calls) == 1


def test_generate_image_still_works_after_reuse(monkeypatch):
    fake_client = _FakeClient(_FakeResponse(image_bytes=b"SECOND-CALL-BYTES"))
    monkeypatch.setattr(providers_module, "get_client", lambda: fake_client)
    provider = GeminiProvider()

    provider.generate_image("prompt one", [], "model-x")
    result = provider.generate_image("prompt two", [], "model-x")

    assert result == b"SECOND-CALL-BYTES"


# --- COST/OBS-4: usage_metadata logging --------------------------------------

def test_generate_image_logs_usage_when_present(monkeypatch, caplog):
    usage = _Usage(prompt_tokens=100, candidates_tokens=200, total_tokens=300)
    fake_client = _FakeClient(_FakeResponse(usage=usage))
    monkeypatch.setattr(providers_module, "get_client", lambda: fake_client)
    provider = GeminiProvider()

    with caplog.at_level(logging.INFO):
        provider.generate_image("prompt", [], "model-x")

    assert "100" in caplog.text
    assert "200" in caplog.text
    assert "300" in caplog.text
    assert "model-x" in caplog.text


def test_generate_image_tolerates_missing_usage_metadata(monkeypatch):
    fake_client = _FakeClient(_FakeResponse(usage=None))
    monkeypatch.setattr(providers_module, "get_client", lambda: fake_client)
    provider = GeminiProvider()

    result = provider.generate_image("prompt", [], "model-x")

    assert result == b"PNGDATA"
