import io
import json
import logging

import pytest
from google.genai import errors as genai_errors
from PIL import Image

import providers as providers_module
from providers import (
    GeminiProvider,
    PROVIDERS,
    get_provider,
    providers_meta,
    validate_model,
)


def _valid_png_bytes(color=(200, 50, 50), size=(2, 2)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="PNG")
    return buf.getvalue()


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
    def __init__(self, image_bytes=None, usage=None, candidates=None):
        if candidates is not None:
            self.candidates = candidates
        else:
            if image_bytes is None:
                image_bytes = _valid_png_bytes()
            self.candidates = [_Candidate([_Part(_InlineData(image_bytes))])]
        self.usage_metadata = usage
        self.prompt_feedback = None


class _FakeModels:
    """Fake `client.models`. Raises `exception` on the first `raise_times`
    calls (to simulate transient failures), then returns `response`."""

    def __init__(self, response=None, raise_times=0, exception=None):
        self._response = response if response is not None else _FakeResponse()
        self.calls = []
        self._raise_times = raise_times
        self._exception = exception or RuntimeError("transient failure")

    def generate_content(self, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        if len(self.calls) <= self._raise_times:
            raise self._exception
        return self._response


class _FakeClient:
    def __init__(self, response=None, models=None):
        self.models = models if models is not None else _FakeModels(response)


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
    expected_bytes = _valid_png_bytes(color=(10, 20, 30))
    fake_client = _FakeClient(_FakeResponse(image_bytes=expected_bytes))
    monkeypatch.setattr(providers_module, "get_client", lambda: fake_client)
    provider = GeminiProvider()

    provider.generate_image("prompt one", [], "model-x")
    result = provider.generate_image("prompt two", [], "model-x")

    assert result == expected_bytes


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
    expected_bytes = _valid_png_bytes()
    fake_client = _FakeClient(_FakeResponse(image_bytes=expected_bytes, usage=None))
    monkeypatch.setattr(providers_module, "get_client", lambda: fake_client)
    provider = GeminiProvider()

    result = provider.generate_image("prompt", [], "model-x")

    assert result == expected_bytes


# --- CORR-5: retry/backoff + response validation -----------------------------

def test_generate_image_retries_transient_server_error(monkeypatch):
    fake_models = _FakeModels(
        raise_times=2, exception=genai_errors.ServerError(500, {"error": {"message": "boom"}})
    )
    fake_client = _FakeClient(models=fake_models)
    monkeypatch.setattr(providers_module, "get_client", lambda: fake_client)
    monkeypatch.setattr(providers_module.time, "sleep", lambda s: None)
    provider = GeminiProvider()

    result = provider.generate_image("prompt", [], "model-x")

    assert result is not None
    assert len(fake_models.calls) == 3  # 2 failures + 1 success


def test_generate_image_retries_rate_limit_error(monkeypatch):
    fake_models = _FakeModels(
        raise_times=1, exception=genai_errors.ClientError(429, {"error": {"message": "rate limited"}})
    )
    fake_client = _FakeClient(models=fake_models)
    monkeypatch.setattr(providers_module, "get_client", lambda: fake_client)
    monkeypatch.setattr(providers_module.time, "sleep", lambda s: None)
    provider = GeminiProvider()

    result = provider.generate_image("prompt", [], "model-x")

    assert result is not None
    assert len(fake_models.calls) == 2  # 1 failure + 1 success


def test_generate_image_does_not_retry_client_error(monkeypatch):
    fake_models = _FakeModels(
        raise_times=99, exception=genai_errors.ClientError(400, {"error": {"message": "bad request"}})
    )
    fake_client = _FakeClient(models=fake_models)
    monkeypatch.setattr(providers_module, "get_client", lambda: fake_client)
    monkeypatch.setattr(providers_module.time, "sleep", lambda s: None)
    provider = GeminiProvider()

    with pytest.raises(genai_errors.ClientError):
        provider.generate_image("prompt", [], "model-x")

    assert len(fake_models.calls) == 1  # a 400 will never succeed on retry


def test_generate_image_raises_after_max_retries_exhausted(monkeypatch):
    fake_models = _FakeModels(
        raise_times=99, exception=genai_errors.ServerError(503, {"error": {"message": "unavailable"}})
    )
    fake_client = _FakeClient(models=fake_models)
    monkeypatch.setattr(providers_module, "get_client", lambda: fake_client)
    monkeypatch.setattr(providers_module.time, "sleep", lambda s: None)
    provider = GeminiProvider()

    with pytest.raises(genai_errors.ServerError):
        provider.generate_image("prompt", [], "model-x")

    assert len(fake_models.calls) == providers_module.MAX_RETRIES


def test_generate_image_empty_candidates_raises_valueerror_without_retry(monkeypatch):
    fake_models = _FakeModels(response=_FakeResponse(candidates=[]))
    fake_client = _FakeClient(models=fake_models)
    monkeypatch.setattr(providers_module, "get_client", lambda: fake_client)
    provider = GeminiProvider()

    with pytest.raises(ValueError, match="No image returned"):
        provider.generate_image("prompt", [], "model-x")

    # A safety-blocked response is not an exception, so it must never be
    # retried — retrying the identical prompt cannot produce a different result.
    assert len(fake_models.calls) == 1


def test_generate_image_rejects_non_image_bytes(monkeypatch):
    fake_client = _FakeClient(_FakeResponse(image_bytes=b"this is not a real image"))
    monkeypatch.setattr(providers_module, "get_client", lambda: fake_client)
    provider = GeminiProvider()

    with pytest.raises(ValueError, match="not a valid image"):
        provider.generate_image("prompt", [], "model-x")
