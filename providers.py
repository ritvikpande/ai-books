import io
import logging
import threading
import time
from abc import ABC, abstractmethod

from google.genai import errors as genai_errors
from google.genai import types
from PIL import Image

from config import get_client

logger = logging.getLogger(__name__)

# Bounded retry for transient API failures. A safety-blocked response (no
# exception, just empty candidates) is handled separately and never retried.
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 1.0


def _is_retryable(exc: Exception) -> bool:
    """Only retry failures a repeat call could plausibly fix.

    Rate limits (429) and server-side errors (5xx) are transient. Any other
    google.genai.errors.APIError (400, 401, 403, 404, ...) is a deterministic
    client mistake — retrying identical input will fail identically. Anything
    that isn't a recognized APIError (e.g. a raw network/connection error) is
    treated as transient, since we can't classify it more precisely.
    """
    if isinstance(exc, genai_errors.ClientError):
        return exc.code == 429
    if isinstance(exc, genai_errors.ServerError):
        return True
    if isinstance(exc, genai_errors.APIError):
        return False
    return True


def _validate_image_bytes(data: bytes) -> None:
    """Raise ValueError if data isn't a decodable image."""
    try:
        Image.open(io.BytesIO(data)).verify()
    except Exception as e:
        raise ValueError(f"Image data returned by the API is not a valid image: {e}")


class ImageProvider(ABC):
    """Adapter for an image-generation API. Pure API calls only — no file I/O."""

    @abstractmethod
    def generate_image(self, prompt: str, context_images: list, model: str) -> bytes:
        """Generate one image from a text prompt plus optional prior images.

        context_images: list of PNG bytes used as visual context (sliding window).
        Returns PNG image bytes. Raises ValueError if the API returns no image
        or returns data that isn't a decodable image.
        """


class GeminiProvider(ImageProvider):
    def __init__(self):
        self._client = None
        self._client_lock = threading.Lock()

    def _get_client(self):
        """Lazily build the Gemini client once and reuse it across calls.

        Lazy (not built in __init__) so importing this module — and the
        module-level PROVIDERS singleton below — never requires a valid
        GEMINI_API_KEY to be present. Double-checked locking: generate_reference_images
        (PERF-7) calls this concurrently from multiple threads on the same
        shared provider instance, so the check-then-build must be race-free;
        the lock is only taken on the rare path where a client doesn't exist
        yet, not on every call once it's built.
        """
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    self._client = get_client()
        return self._client

    def _call_with_retry(self, client, model, contents, config):
        """Call generate_content, retrying transient failures with backoff."""
        attempt = 0
        while True:
            try:
                return client.models.generate_content(
                    model=model, contents=contents, config=config
                )
            except Exception as exc:
                attempt += 1
                if attempt >= MAX_RETRIES or not _is_retryable(exc):
                    raise
                time.sleep(RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1)))

    def generate_image(self, prompt: str, context_images: list, model: str) -> bytes:
        client = self._get_client()
        parts = [
            types.Part.from_bytes(data=img, mime_type="image/png")
            for img in context_images
        ]
        parts.append(types.Part.from_text(text=prompt))

        response = self._call_with_retry(
            client,
            model,
            parts,
            types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
        )

        usage = getattr(response, "usage_metadata", None)
        if usage is not None:
            logger.info(
                "Gemini image call model=%s prompt_tokens=%s candidates_tokens=%s total_tokens=%s",
                model,
                getattr(usage, "prompt_token_count", None),
                getattr(usage, "candidates_token_count", None),
                getattr(usage, "total_token_count", None),
            )

        if not response.candidates:
            feedback = getattr(response, "prompt_feedback", None)
            raise ValueError(f"No image returned in response (prompt_feedback={feedback})")

        for part in response.candidates[0].content.parts:
            if part.inline_data is not None:
                _validate_image_bytes(part.inline_data.data)
                return part.inline_data.data
        raise ValueError("No image returned in response")


PROVIDERS = {
    "google": {
        "label": "Google (Gemini)",
        "provider": GeminiProvider(),
        "image_models": [
            {
                "id": "gemini-2.5-flash-image",
                "label": "Gemini 2.5 Flash Image — fast, ~$0.06/book",
            },
            {
                "id": "gemini-3-pro-image-preview",
                "label": "Gemini 3 Pro Image (Nano Banana Pro) — best quality, ~$0.90/book",
            },
        ],
    },
}


def get_provider(provider_id: str) -> ImageProvider:
    if provider_id not in PROVIDERS:
        raise ValueError(f"Unknown provider: '{provider_id}'")
    return PROVIDERS[provider_id]["provider"]


def validate_model(provider_id: str, model_id: str) -> None:
    if provider_id not in PROVIDERS:
        raise ValueError(f"Unknown provider: '{provider_id}'")
    model_ids = [m["id"] for m in PROVIDERS[provider_id]["image_models"]]
    if model_id not in model_ids:
        raise ValueError(
            f"Unknown image model '{model_id}' for provider '{provider_id}'"
        )


def providers_meta() -> dict:
    """JSON-serializable view of the registry for the frontend (no provider instances)."""
    return {
        pid: {"label": p["label"], "image_models": p["image_models"]}
        for pid, p in PROVIDERS.items()
    }
