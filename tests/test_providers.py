import json

import pytest

from providers import (
    GeminiProvider,
    PROVIDERS,
    get_provider,
    providers_meta,
    validate_model,
)


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
