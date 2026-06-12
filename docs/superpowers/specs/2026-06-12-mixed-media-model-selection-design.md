# Mixed-Media Stories + Provider/Model Selection — Design

**Date:** 2026-06-12
**Branch:** `feat/face-swap`
**Status:** Approved by Ritvik (2026-06-12)

## Goal

Two related features for the AI Storybook Generator:

1. **Mixed-media stories** (Ms Rachel style): the main human characters appear as
   photorealistic photographs while the rest of the scene — background, supporting
   characters — is rendered in the user's selected 2D art style. The contrast makes
   the main characters "pop". Validated manually by Ritvik with a working prompt
   sequence (Dad photoreal, toddler + playground 2D vector cartoon).
2. **Provider/model selection**: frontend dropdowns for image-generation Provider and
   Image Model, with the backend structured so future providers (e.g. OpenAI) are a
   new class + registry entry. For now: one provider (Google/Gemini), two image models.

Photorealistic characters are **fully AI-generated** from text descriptions — no photo
upload in this iteration (privacy/child-safety review still deferred, per POC plan).

**Definition of done:** working locally; 1 classic-mode regression book + 1–2 good
mixed-media books generated. Cloud Run redeploy is a separate later step.

## Decisions Made

| Question | Decision |
|----------|----------|
| Mixed-media UI placement | Separate **checkbox toggle**, independent of Story Type and Art Style |
| Character split UI | Toggle reveals two fields: Photorealistic characters (required), Cartoon characters (optional) |
| Cartoon-world style | Comes from the existing Art Style dropdown |
| Photoreal character source | Fully AI-generated from text; no photo upload |
| Model selection scope | Image model only; story text model stays a backend constant |
| Image models offered | `gemini-2.5-flash-image` (default) and `gemini-3-pro-image-preview` |
| Provider abstraction | Small `ImageProvider` interface + registry (no LiteLLM/LangChain) |
| Mixed-media prompt construction | Hybrid: LLM writes scene-specific fields, Python assembles the proven boilerplate verbatim |

## 1. Provider Abstraction — new module `providers.py`

```python
class ImageProvider(ABC):
    @abstractmethod
    def generate_image(self, prompt: str, context_images: list[bytes], model: str) -> bytes:
        """One image from a text prompt plus optional prior-image context. Returns PNG bytes."""

class GeminiProvider(ImageProvider):
    # Existing google-genai logic moves here:
    # parts = [Part.from_bytes(...) for each context image] + [Part.from_text(prompt)]
    # response_modalities=["IMAGE", "TEXT"]; extract first inline_data part.
```

Registry — single source of truth for backend validation AND frontend dropdowns:

```python
PROVIDERS = {
    "google": {
        "label": "Google (Gemini)",
        "provider": GeminiProvider(),
        "image_models": [
            {"id": "gemini-2.5-flash-image",     "label": "Gemini 2.5 Flash Image — fast, ~$0.06/book"},
            {"id": "gemini-3-pro-image-preview", "label": "Gemini 3 Pro Image (Nano Banana Pro) — best quality, ~$0.90/book"},
        ],
    },
}

def get_provider(provider_id: str) -> ImageProvider          # raises KeyError-style ValueError
def validate_model(provider_id: str, model_id: str) -> None  # raises ValueError if unknown
```

`config.py`: keeps `TEXT_MODEL` and `get_client()`; gains `DEFAULT_PROVIDER = "google"`
and `DEFAULT_IMAGE_MODEL = "gemini-2.5-flash-image"`. The old `IMAGE_MODEL` constant is
removed (replaced by per-request model selection).

`image_generator.py`: keeps all storybook logic (sliding window, caption overlay, PDF).
`_generate_with_context(...)` and `generate_all_images(...)` gain `provider` and `model`
parameters and call `provider.generate_image(prompt, context_bytes, model)` instead of
the Gemini client directly. File I/O (reading context PNGs into bytes, writing output)
stays in `image_generator.py` so providers remain pure API adapters.

## 2. Mixed-Media Prompt Assembly

### Story generation (`story_generator.py`)

`generate_story()` gains parameters: `mixed_media: bool`, `photoreal_characters: str`,
`cartoon_characters: str`. Two system-prompt variants:

- **Classic mode (unchanged):** current behavior, scenes contain a complete `image_prompt`.
- **Mixed-media mode:** each scene returns structured visual fields instead of `image_prompt`:

```json
{
  "scene_number": 1,
  "text": "1-2 short toddler-friendly sentences.",
  "photoreal_action": "a happy adult man (Dad) with short dark hair, jeans and a green sweater, walking breezily and holding hands",
  "cartoon_elements": "a flat 2D cartoon toddler in a yellow shirt holding Dad's hand",
  "background": "a kids playground with beautiful trees and other cartoon children playing"
}
```

System-prompt rules carried over from classic mode: consistent character descriptions
(same hair/clothing/colors) in every scene's fields; 5 scenes; age-appropriate content;
no scary/violent content. `cartoon_elements` may be empty if the user gave no cartoon
characters and the scene needs none beyond the background.

### Prompt assembly (pure function, unit-tested)

```python
def assemble_mixed_media_prompt(scene: dict, photoreal_characters: str,
                                cartoon_characters: str, art_style: str) -> str
```

Template (boilerplate verbatim in all 5 scenes — this skeleton is what was validated
manually and must not be paraphrased by the LLM):

> A mixed media children's book illustration collage. In the center, a photorealistic,
> high-resolution photograph of {photoreal_action}. {cartoon_elements}. The background
> is a purely {world_phrase}: {background}. There is a distinct, sharp contrast between
> the photographic real {photoreal character names} and the completely 2D cartoon world
> {and cartoon …, if cartoon characters exist}. {style_closer}. No text or words in the image.

`STYLE_PHRASES` dict maps each Art Style option to `world_phrase` + `style_closer`:

| Art Style | world_phrase | style_closer |
|-----------|-------------|--------------|
| 2D flat vector cartoon (pastel) — **new option, proven default** | "2D flat vector cartoon" | "Clean lines, pastel colors for the background, collage art style" |
| Watercolor storybook illustration | "2D watercolor storybook illustration" | "Soft watercolor washes for the background, collage art style" |
| Cartoon illustration | "2D cartoon illustration" | "Bold clean outlines, bright friendly colors for the background, collage art style" |
| Pencil sketch illustration | "2D pencil sketch illustration" | "Soft graphite shading for the background, collage art style" |
| Pixel art illustration | "2D pixel art illustration" | "Retro pixel detail for the background, collage art style" |

Assembled final prompts are written into the saved `story.json` (each scene gets its
`image_prompt` filled in post-assembly) so debugging/iteration works exactly as today.
Classic mode is untouched end-to-end.

## 3. Frontend (`templates/index.html`)

- **Provider** + **Image Model** dropdowns rendered server-side via Jinja from the
  `PROVIDERS` registry (passed by the `/` route) — no duplicated model lists in JS.
  Provider has one option for now; Image Model defaults to Flash; labels include cost hints.
- **Mixed Media checkbox** with helper text ("photorealistic main characters in a
  cartoon world"). Checked → the single Characters field is hidden and replaced by
  **Photorealistic characters** (required) and **Cartoon characters** (optional).
  Unchecked → UI and payload identical to today.
- Art Style dropdown gains "2D flat vector cartoon (pastel)" option.
- `/generate` payload gains: `provider`, `image_model`, `mixed_media`,
  `photoreal_characters`, `cartoon_characters`.

## 4. Flask (`app.py`)

`/generate`:
1. Validate `provider`/`image_model` against the registry → 400 with message if unknown.
2. If `mixed_media` and `photoreal_characters` empty → 400.
3. If not `mixed_media`, `characters` required (current behavior).
4. Resolve provider instance; pass `provider`/`model` to `generate_all_images(...)` and
   the mixed-media fields to `generate_story(...)`.

`/`, `/images`, `/download_pdf`, output-folder layout: unchanged.

## 5. Error Handling

- Unknown provider/model, missing required fields → 400 with a clear message.
- Provider API failures keep the existing log-and-500 path; error text surfaces in the
  UI error div. The Pro preview model rate-limits more readily — its message passes
  through verbatim. No retry/backoff in this iteration (consistent with current scope).

## 6. Testing

- **Unit tests (pytest, no API calls):** `assemble_mixed_media_prompt` (boilerplate
  present verbatim, names substituted, empty cartoon_elements handled, every
  STYLE_PHRASES entry covered) and registry validation (`get_provider`/`validate_model`
  accept known, reject unknown).
- **Manual:** 1 classic-mode book (regression), 1–2 mixed-media books on Flash, 1 on
  Pro. Expected spend ~$1–2 CAD, within budget.

## Out of Scope

- Photo upload / real-face likeness anchoring (the eventual "face-swap" goal — next iteration)
- Actual OpenAI (or other) provider implementation
- Selectable text/story model
- Cloud Run redeploy
- Retry/backoff, auth, automated image-quality evaluation
