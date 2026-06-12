from abc import ABC, abstractmethod

from google.genai import types

from config import get_client


class ImageProvider(ABC):
    """Adapter for an image-generation API. Pure API calls only — no file I/O."""

    @abstractmethod
    def generate_image(self, prompt: str, context_images: list, model: str) -> bytes:
        """Generate one image from a text prompt plus optional prior images.

        context_images: list of PNG bytes used as visual context (sliding window).
        Returns PNG image bytes. Raises ValueError if the API returns no image.
        """


class GeminiProvider(ImageProvider):
    def generate_image(self, prompt: str, context_images: list, model: str) -> bytes:
        client = get_client()
        parts = [
            types.Part.from_bytes(data=img, mime_type="image/png")
            for img in context_images
        ]
        parts.append(types.Part.from_text(text=prompt))

        response = client.models.generate_content(
            model=model,
            contents=parts,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"]
            ),
        )

        for part in response.candidates[0].content.parts:
            if part.inline_data is not None:
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
