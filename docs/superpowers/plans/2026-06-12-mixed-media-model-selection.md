# Mixed-Media Stories + Provider/Model Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Ms Rachel-style mixed-media storybooks (photorealistic main characters in a 2D cartoon world) and frontend provider/image-model selection backed by a provider abstraction (Gemini-only for now).

**Architecture:** A new `providers.py` holds an `ImageProvider` interface, a `GeminiProvider` implementation, and a `PROVIDERS` registry that drives both backend validation and the frontend dropdowns. A new `prompt_assembly.py` wraps LLM-written scene fields in the manually-validated mixed-media prompt boilerplate (verbatim in all 5 scenes). `story_generator.py` gains a mixed-media system-prompt variant; `image_generator.py` keeps all storybook logic but calls the provider instead of the Gemini client directly.

**Tech Stack:** Python 3, Flask, google-genai, Pillow, pytest (new dev dependency), Bootstrap/Jinja frontend.

**Spec:** `docs/superpowers/specs/2026-06-12-mixed-media-model-selection-design.md`

**Environment notes for the executor:**
- Working dir: repo root (`ai-books/`). Windows machine; venv exists at `venv\`.
- Run Python via `venv\Scripts\python`. No API key is needed for any unit test (the Gemini client is created lazily inside `generate_image`). Only Task 8 (manual E2E) calls the paid API.
- Branch: `feat/face-swap` (already checked out).

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `providers.py` | Create | `ImageProvider` ABC, `GeminiProvider`, `PROVIDERS` registry, `get_provider`, `validate_model`, `providers_meta` |
| `prompt_assembly.py` | Create | `STYLE_PHRASES` table + `assemble_mixed_media_prompt` (pure function) |
| `tests/test_providers.py` | Create | Registry/validation unit tests |
| `tests/test_prompt_assembly.py` | Create | Prompt assembly unit tests |
| `tests/test_story_validation.py` | Create | Story-structure validation unit tests |
| `config.py` | Modify | Drop `IMAGE_MODEL`; add `DEFAULT_PROVIDER`, `DEFAULT_IMAGE_MODEL` |
| `image_generator.py` | Modify | Take `provider` + `model` params; drop direct genai usage |
| `story_generator.py` | Modify | Mixed-media mode: new params, second system prompt, extracted validation, prompt assembly |
| `app.py` | Modify | Validate provider/model + mixed-media fields; pass through; feed registry to template |
| `templates/index.html` | Modify | Provider/model dropdowns, Mixed Media toggle + character fields, payload changes |
| `requirements.txt` | Modify | Add `pytest` |

---

### Task 1: Test infrastructure

**Files:**
- Modify: `requirements.txt`
- Create: `tests/` (directory, via first test file in Task 2)

- [ ] **Step 1: Add pytest to requirements.txt**

Append `pytest` so `requirements.txt` becomes:

```
google-genai
pillow
python-dotenv
flask
gunicorn
pytest
```

- [ ] **Step 2: Install pytest into the venv**

Run: `venv\Scripts\pip install pytest`
Expected: `Successfully installed ... pytest-8.x.x` (or "Requirement already satisfied").

- [ ] **Step 3: Verify pytest runs**

Run: `venv\Scripts\python -m pytest --version`
Expected: `pytest 8.x.x`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore: add pytest for unit tests"
```

---

### Task 2: Provider abstraction (`providers.py`)

**Files:**
- Create: `providers.py`
- Test: `tests/test_providers.py`

`GeminiProvider.generate_image` is a thin adapter around the API call currently living in `image_generator.py:_build_contents` / `_generate_with_context` — it is exercised manually in Task 8, not unit-tested. The registry helpers ARE unit-tested.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_providers.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv\Scripts\python -m pytest tests\test_providers.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'providers'`

- [ ] **Step 3: Write the implementation**

Create `providers.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv\Scripts\python -m pytest tests\test_providers.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add providers.py tests/test_providers.py
git commit -m "feat: add ImageProvider abstraction with Gemini provider and registry"
```

---

### Task 3: Mixed-media prompt assembly (`prompt_assembly.py`)

**Files:**
- Create: `prompt_assembly.py`
- Test: `tests/test_prompt_assembly.py`

The boilerplate skeleton (collage opener, contrast sentence, style closer, "No text" closer) was validated manually by the user and must appear verbatim in every scene's prompt. The LLM only supplies `photoreal_action`, `cartoon_elements`, `background`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_prompt_assembly.py`:

```python
import pytest

from prompt_assembly import DEFAULT_STYLE, STYLE_PHRASES, assemble_mixed_media_prompt

SCENE = {
    "scene_number": 1,
    "text": "Dad and Lily go to the playground.",
    "photoreal_action": "a happy adult man (Dad) with short dark hair, jeans and a green sweater, walking breezily and holding hands",
    "cartoon_elements": "a flat 2D cartoon toddler in a yellow shirt holding Dad's hand",
    "background": "a kids playground with beautiful trees and other cartoon children playing",
}


def _assemble(scene=SCENE, photoreal="a happy adult man (Dad)", cartoon="a toddler",
              style="2D flat vector cartoon (pastel)"):
    return assemble_mixed_media_prompt(scene, photoreal, cartoon, style)


def test_boilerplate_opener_and_closers_present_verbatim():
    prompt = _assemble()
    assert prompt.startswith("A mixed media children's book illustration collage.")
    assert "Clean lines, pastel colors for the background, collage art style." in prompt
    assert prompt.endswith("No text or words in the image.")


def test_photoreal_sentence_uses_scene_action():
    prompt = _assemble()
    assert (
        "In the center, a photorealistic, high-resolution photograph of "
        "a happy adult man (Dad) with short dark hair, jeans and a green sweater, "
        "walking breezily and holding hands." in prompt
    )


def test_contrast_sentence_names_both_character_sets():
    prompt = _assemble()
    assert (
        "There is a distinct, sharp contrast between the photographic real "
        "a happy adult man (Dad) and the completely 2D cartoon world and cartoon a toddler."
        in prompt
    )


def test_contrast_sentence_without_cartoon_characters():
    prompt = _assemble(cartoon="")
    assert "and the completely 2D cartoon world." in prompt
    assert "and cartoon ." not in prompt


def test_empty_cartoon_elements_skipped():
    scene = dict(SCENE, cartoon_elements="")
    prompt = _assemble(scene=scene)
    assert "  " not in prompt  # no double spaces from a dropped empty sentence


def test_background_uses_world_phrase():
    prompt = _assemble()
    assert (
        "The background is a purely 2D flat vector cartoon: "
        "a kids playground with beautiful trees and other cartoon children playing."
        in prompt
    )


def test_unknown_style_falls_back_to_default():
    prompt = _assemble(style="some future style")
    default = STYLE_PHRASES[DEFAULT_STYLE]
    assert default["world_phrase"] in prompt
    assert default["style_closer"] in prompt


@pytest.mark.parametrize("style_key", list(STYLE_PHRASES.keys()))
def test_every_style_produces_its_phrases(style_key):
    prompt = _assemble(style=style_key)
    assert STYLE_PHRASES[style_key]["world_phrase"] in prompt
    assert STYLE_PHRASES[style_key]["style_closer"] in prompt


def test_trailing_periods_in_inputs_do_not_double_up():
    scene = dict(SCENE, photoreal_action=SCENE["photoreal_action"] + ".")
    prompt = _assemble(scene=scene)
    assert ".." not in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv\Scripts\python -m pytest tests\test_prompt_assembly.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'prompt_assembly'`

- [ ] **Step 3: Write the implementation**

Create `prompt_assembly.py`:

```python
"""Assemble mixed-media image prompts from LLM-written scene fields.

The boilerplate skeleton below was validated manually and must appear verbatim
in every scene's prompt — the LLM only supplies the scene-specific middle.
Keys of STYLE_PHRASES are lowercase because app.py lowercases art_style.
"""

STYLE_PHRASES = {
    "2d flat vector cartoon (pastel)": {
        "world_phrase": "2D flat vector cartoon",
        "style_closer": "Clean lines, pastel colors for the background, collage art style",
    },
    "watercolor storybook illustration": {
        "world_phrase": "2D watercolor storybook illustration",
        "style_closer": "Soft watercolor washes for the background, collage art style",
    },
    "cartoon illustration": {
        "world_phrase": "2D cartoon illustration",
        "style_closer": "Bold clean outlines, bright friendly colors for the background, collage art style",
    },
    "pencil sketch illustration": {
        "world_phrase": "2D pencil sketch illustration",
        "style_closer": "Soft graphite shading for the background, collage art style",
    },
    "pixel art illustration": {
        "world_phrase": "2D pixel art illustration",
        "style_closer": "Retro pixel detail for the background, collage art style",
    },
}

DEFAULT_STYLE = "2d flat vector cartoon (pastel)"


def _clause(text: str) -> str:
    """Trim whitespace and any trailing period so sentence joins stay clean."""
    return text.strip().rstrip(".")


def assemble_mixed_media_prompt(
    scene: dict,
    photoreal_characters: str,
    cartoon_characters: str,
    art_style: str,
) -> str:
    phrases = STYLE_PHRASES.get(art_style.lower().strip(), STYLE_PHRASES[DEFAULT_STYLE])

    sentences = [
        "A mixed media children's book illustration collage.",
        (
            "In the center, a photorealistic, high-resolution photograph of "
            f"{_clause(scene['photoreal_action'])}."
        ),
    ]

    cartoon_elements = _clause(scene.get("cartoon_elements") or "")
    if cartoon_elements:
        sentences.append(f"{cartoon_elements}.")

    sentences.append(
        f"The background is a purely {phrases['world_phrase']}: "
        f"{_clause(scene['background'])}."
    )

    contrast = (
        "There is a distinct, sharp contrast between the photographic real "
        f"{_clause(photoreal_characters)} and the completely 2D cartoon world"
    )
    if cartoon_characters.strip():
        contrast += f" and cartoon {_clause(cartoon_characters)}"
    sentences.append(contrast + ".")

    sentences.append(f"{phrases['style_closer']}.")
    sentences.append("No text or words in the image.")

    return " ".join(sentences)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv\Scripts\python -m pytest tests\test_prompt_assembly.py -v`
Expected: 13 passed (9 tests, one parametrized ×5)

- [ ] **Step 5: Commit**

```bash
git add prompt_assembly.py tests/test_prompt_assembly.py
git commit -m "feat: add mixed-media prompt assembly with style phrase table"
```

---

### Task 4: Thread provider/model through `config.py` and `image_generator.py`

**Files:**
- Modify: `config.py`
- Modify: `image_generator.py`

No new unit tests here (the changes are API/file plumbing, verified by import checks now and manual E2E in Task 8) — but the full suite must still pass, which guards against broken imports.

- [ ] **Step 1: Update config.py**

Replace the model constants block in `config.py` (lines 7–9: the comment, `TEXT_MODEL`, `IMAGE_MODEL`) with:

```python
# Model used for story/text generation (image models live in providers.py)
TEXT_MODEL = "gemini-3-flash-preview"

# Defaults for image generation; must exist in providers.PROVIDERS
DEFAULT_PROVIDER = "google"
DEFAULT_IMAGE_MODEL = "gemini-2.5-flash-image"
```

Everything else in `config.py` (imports, `load_dotenv()`, `OUTPUT_DIR`, `get_client`) stays unchanged. Note: defaults live here, the registry lives in `providers.py` — `providers.py` imports `config`, never the reverse (no circular import).

- [ ] **Step 2: Rewrite image_generator.py's generation core**

In `image_generator.py`:

a. Replace the imports at the top of the file:

```python
import os
import io
import time
import logging
from PIL import Image, ImageDraw, ImageFont
from config import OUTPUT_DIR
```

(removes `from google.genai import types` and the `get_client, IMAGE_MODEL` imports; the caption-overlay section and `generate_pdf` are untouched.)

b. Replace `_build_contents` (currently lines 77–84) with:

```python
def _load_context_bytes(context_paths: list) -> list:
    """Read sliding-window context images from disk as PNG bytes."""
    images = []
    for path in context_paths:
        with open(path, "rb") as f:
            images.append(f.read())
    return images
```

c. Replace `_generate_with_context` with:

```python
def _generate_with_context(
    prompt: str,
    context_paths: list,
    output_path: str,
    provider,
    model: str,
    caption_text: str = ""
) -> str:
    """
    Generate one image with optional context images (sliding window).
    Saves to output_path, applies caption if provided.
    Returns output_path.
    """
    logger.info(f"Generating image: {os.path.basename(output_path)} "
                f"(model: {model}, context: {len(context_paths)} previous image(s))")
    start = time.time()

    image_data = provider.generate_image(
        prompt=prompt,
        context_images=_load_context_bytes(context_paths),
        model=model,
    )

    elapsed = time.time() - start
    logger.info(f"Image response received in {elapsed:.1f}s")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(image_data)

    # Burn caption onto image
    if caption_text:
        add_caption(output_path, caption_text)

    logger.info(f"Image saved: {output_path}")
    return output_path
```

d. Update the two public functions to accept and forward `provider` and `model`:

```python
def generate_single_image(prompt: str, output_path: str, provider, model: str,
                          caption_text: str = "") -> str:
    """
    Generate a single image from a text prompt (no context).
    Kept for standalone testing.
    """
    return _generate_with_context(prompt, [], output_path, provider, model, caption_text)


def generate_all_images(story: dict, output_dir: str, provider, model: str) -> list:
    """
    Generate all 5 scene images using a sliding window of previous images.

    Window:
      Scene 1: no context
      Scene 2: [scene_1]
      Scene 3: [scene_1, scene_2]
      Scene 4: [scene_2, scene_3]
      Scene 5: [scene_3, scene_4]

    Returns list of saved image paths.
    """
    scenes = story["scenes"]
    saved_paths = []

    for i, scene in enumerate(scenes):
        n = scene["scene_number"]

        # Build sliding window: up to 2 previous images
        window_start = max(0, i - 2)
        context = saved_paths[window_start:i]

        output_path = os.path.join(output_dir, f"scene_{n}.png")
        _generate_with_context(
            prompt=scene["image_prompt"],
            context_paths=context,
            output_path=output_path,
            provider=provider,
            model=model,
            caption_text=scene["text"]
        )
        saved_paths.append(output_path)

    logger.info(f"All {len(saved_paths)} images generated.")
    return saved_paths
```

e. Update the `__main__` quick-test block at the bottom — replace its last three lines (`output_path = ...`, `saved = ...`, `print/show`) with:

```python
    from providers import get_provider
    from config import DEFAULT_PROVIDER, DEFAULT_IMAGE_MODEL

    output_path = os.path.join(OUTPUT_DIR, "test", "scene_1.png")
    saved = generate_single_image(
        test_prompt,
        output_path,
        provider=get_provider(DEFAULT_PROVIDER),
        model=DEFAULT_IMAGE_MODEL,
        caption_text="Mia and Biscuit walk into the candy forest!",
    )
    print(f"\nImage saved to: {saved}")
    Image.open(saved).show()
```

- [ ] **Step 3: Verify all modules still import and the suite passes**

Run: `venv\Scripts\python -c "import config, providers, image_generator, story_generator, app; print('imports OK')"`
Expected: `imports OK`

Run: `venv\Scripts\python -m pytest tests -v`
Expected: all tests pass (19 at this point)

Note: `app.py` still calls `generate_all_images(story, story_dir)` without provider/model — that call site is fixed in Task 6. Importing still works; only invoking `/generate` would fail, and nothing invokes it between now and Task 6.

- [ ] **Step 4: Commit**

```bash
git add config.py image_generator.py
git commit -m "refactor: route image generation through ImageProvider, add model defaults"
```

---

### Task 5: Mixed-media story generation (`story_generator.py`)

**Files:**
- Modify: `story_generator.py`
- Test: `tests/test_story_validation.py`

Validation is extracted into a pure `_validate_story(story, mixed_media)` function so it can be unit-tested without API calls.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_story_validation.py`:

```python
import pytest

from story_generator import _validate_story


def _classic_story():
    return {
        "title": "A Day Out",
        "scenes": [
            {"scene_number": n, "text": "Some text.", "image_prompt": "A prompt."}
            for n in range(1, 6)
        ],
    }


def _mixed_story():
    return {
        "title": "A Day Out",
        "scenes": [
            {
                "scene_number": n,
                "text": "Some text.",
                "photoreal_action": "Dad waving",
                "cartoon_elements": "a cartoon toddler",
                "background": "a playground",
            }
            for n in range(1, 6)
        ],
    }


def test_classic_story_valid():
    _validate_story(_classic_story(), mixed_media=False)


def test_mixed_story_valid():
    _validate_story(_mixed_story(), mixed_media=True)


def test_missing_title_rejected():
    story = _classic_story()
    del story["title"]
    with pytest.raises(AssertionError):
        _validate_story(story, mixed_media=False)


def test_wrong_scene_count_rejected():
    story = _classic_story()
    story["scenes"] = story["scenes"][:4]
    with pytest.raises(AssertionError):
        _validate_story(story, mixed_media=False)


def test_classic_scene_missing_image_prompt_rejected():
    story = _classic_story()
    del story["scenes"][2]["image_prompt"]
    with pytest.raises(AssertionError):
        _validate_story(story, mixed_media=False)


def test_mixed_scene_missing_photoreal_action_rejected():
    story = _mixed_story()
    del story["scenes"][0]["photoreal_action"]
    with pytest.raises(AssertionError):
        _validate_story(story, mixed_media=True)


def test_mixed_scene_empty_background_rejected():
    story = _mixed_story()
    story["scenes"][4]["background"] = "  "
    with pytest.raises(AssertionError):
        _validate_story(story, mixed_media=True)


def test_mixed_scene_empty_cartoon_elements_allowed():
    story = _mixed_story()
    story["scenes"][1]["cartoon_elements"] = ""
    _validate_story(story, mixed_media=True)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv\Scripts\python -m pytest tests\test_story_validation.py -v`
Expected: `ImportError: cannot import name '_validate_story'`

- [ ] **Step 3: Implement mixed-media mode in story_generator.py**

a. Add to the imports at the top:

```python
from prompt_assembly import assemble_mixed_media_prompt
```

b. After the existing `SYSTEM_PROMPT`, add the mixed-media system prompt:

```python
MIXED_MEDIA_SYSTEM_PROMPT = """You are a toddler's picture book author.
Given user inputs, generate a 5-scene story for toddlers aged 2-5.

The book is MIXED MEDIA: the characters listed as "photorealistic characters"
appear as real photographed people, while everything else (other characters,
the background world) is flat 2D cartoon. You do NOT write full image prompts —
you only fill in three visual fields per scene; a fixed template adds all the
style wording.

Return ONLY valid JSON — no markdown, no code blocks, no extra text.

Format:
{
  "title": "Story title",
  "scenes": [
    {
      "scene_number": 1,
      "text": "1-2 short sentences for this scene. Simple words, warm and fun tone.",
      "photoreal_action": "the photorealistic character(s) with consistent physical details (hair, clothing, colors) and what they are doing in this scene",
      "cartoon_elements": "the cartoon character(s), described as flat 2D cartoon with consistent details, and what they are doing. Empty string if no cartoon characters appear in this scene.",
      "background": "the background/setting for this scene: place, objects, time of day, plus any incidental cartoon children or animals"
    }
  ]
}

Rules:
- Story must have a clear beginning, middle, and end across 5 scenes
- Keep language simple — short sentences, common words
- In EVERY scene, describe each character with the SAME physical details (same hair, same clothing, same colors) so they look consistent across all images
- Do not include art style words like "watercolor" or "vector" in photoreal_action — the photorealistic characters must read as a real photograph
- photoreal_action and background must never be empty
- No scary, violent, or inappropriate content"""
```

c. Add the extracted validation function (replacing nothing yet — it goes right above `generate_story`):

```python
CLASSIC_SCENE_KEYS = ("scene_number", "text", "image_prompt")
MIXED_SCENE_KEYS = ("scene_number", "text", "photoreal_action", "cartoon_elements", "background")


def _validate_story(story: dict, mixed_media: bool = False) -> None:
    """Validate the parsed LLM response structure. Raises AssertionError on problems."""
    assert "title" in story, "Missing 'title' in response"
    assert "scenes" in story, "Missing 'scenes' in response"
    assert len(story["scenes"]) == 5, f"Expected 5 scenes, got {len(story['scenes'])}"
    required = MIXED_SCENE_KEYS if mixed_media else CLASSIC_SCENE_KEYS
    for scene in story["scenes"]:
        for key in required:
            assert key in scene, f"Scene missing '{key}'"
        if mixed_media:
            assert scene["photoreal_action"].strip(), "photoreal_action must not be empty"
            assert scene["background"].strip(), "background must not be empty"
```

d. Replace the whole `generate_story` function with:

```python
def generate_story(keywords: str, characters: str, setting: str, story_type: str,
                   art_style: str, mixed_media: bool = False,
                   photoreal_characters: str = "", cartoon_characters: str = "") -> dict:
    """
    Generate a 5-scene children's story with image prompts.

    Classic mode: the LLM writes a complete image_prompt per scene.
    Mixed-media mode: the LLM writes visual fields (photoreal_action,
    cartoon_elements, background) and the proven boilerplate template
    assembles the final image_prompt for each scene.

    Returns a dict with keys: title, scenes (list of 5 scene dicts).
    Every scene has scene_number, text, image_prompt after this function returns.
    """
    client = get_client()

    if mixed_media:
        system_prompt = MIXED_MEDIA_SYSTEM_PROMPT
        user_prompt = f"""Create a toddler's picture book with these inputs:
- Keywords/interests: {keywords}
- Photorealistic characters: {photoreal_characters}
- Cartoon characters: {cartoon_characters or "none"}
- Setting: {setting}
- Story type: {story_type}"""
    else:
        system_prompt = SYSTEM_PROMPT
        user_prompt = f"""Create a toddler's picture book with these inputs:
- Keywords/interests: {keywords}
- Characters: {characters}
- Setting: {setting}
- Story type: {story_type}
- Art style: {art_style}

Remember to replace ART_STYLE in every image_prompt with: {art_style}"""

    logger.info(f"Generating story with Gemini... (mixed_media={mixed_media})")
    start = time.time()

    response = client.models.generate_content(
        model=TEXT_MODEL,
        contents=user_prompt,
        config={
            "system_instruction": system_prompt,
            "temperature": 0.9,
        }
    )

    elapsed = time.time() - start
    logger.info(f"Story response received in {elapsed:.1f}s")

    raw = response.text.strip()
    logger.info("Parsing JSON...")

    # Strip markdown code blocks if Gemini wraps the JSON anyway
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    story = json.loads(raw)
    _validate_story(story, mixed_media=mixed_media)

    if mixed_media:
        for scene in story["scenes"]:
            scene["image_prompt"] = assemble_mixed_media_prompt(
                scene, photoreal_characters, cartoon_characters, art_style
            )

    logger.info(f"Story generated: '{story['title']}'")
    return story
```

(The old inline `assert` block disappears into `_validate_story`. The `__main__` quick-test block at the bottom of the file is unchanged — it exercises classic mode.)

- [ ] **Step 4: Run the full suite**

Run: `venv\Scripts\python -m pytest tests -v`
Expected: all tests pass (27 at this point)

- [ ] **Step 5: Commit**

```bash
git add story_generator.py tests/test_story_validation.py
git commit -m "feat: add mixed-media story mode with template-assembled image prompts"
```

---

### Task 6: Flask wiring (`app.py`)

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Update imports and the index route**

Replace the two config/provider-related imports in `app.py` (line 11: `from config import OUTPUT_DIR`) with:

```python
from config import OUTPUT_DIR, DEFAULT_PROVIDER, DEFAULT_IMAGE_MODEL
from providers import get_provider, validate_model, providers_meta
```

Replace the `index` route with:

```python
@app.route('/', methods=['GET'])
def index():
    return render_template(
        'index.html',
        providers=providers_meta(),
        default_provider=DEFAULT_PROVIDER,
        default_image_model=DEFAULT_IMAGE_MODEL,
    )
```

- [ ] **Step 2: Update the /generate route**

Replace the input-parsing and validation section of `generate()` (everything from `data = request.json` through the `if not keywords ...` check) with:

```python
    data = request.json
    keywords = data.get('keywords')
    characters = data.get('characters')
    setting = data.get('setting')
    story_type = data.get('story_type', 'Adventure').lower()
    art_style = data.get('art_style', 'Watercolor storybook illustration').lower()

    provider_id = data.get('provider', DEFAULT_PROVIDER)
    image_model = data.get('image_model', DEFAULT_IMAGE_MODEL)
    try:
        validate_model(provider_id, image_model)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    mixed_media = bool(data.get('mixed_media'))
    photoreal_characters = (data.get('photoreal_characters') or '').strip()
    cartoon_characters = (data.get('cartoon_characters') or '').strip()

    if mixed_media:
        if not keywords or not setting or not photoreal_characters:
            return jsonify({"error": "Please fill in Keywords, Setting, and Photorealistic Characters."}), 400
    else:
        if not keywords or not characters or not setting:
            return jsonify({"error": "Please fill in Keywords, Characters, and Setting."}), 400
```

Then update the two generation calls inside the `try` block:

```python
        story = generate_story(
            keywords=keywords,
            characters=characters or "",
            setting=setting,
            story_type=story_type,
            art_style=art_style,
            mixed_media=mixed_media,
            photoreal_characters=photoreal_characters,
            cartoon_characters=cartoon_characters,
        )
```

```python
        image_paths = generate_all_images(
            story, story_dir, get_provider(provider_id), image_model
        )
```

Everything else in `generate()` (timestamp/folder creation, story.json dump, response JSON, error handling) and the `/images` + `/download_pdf` routes stay unchanged.

- [ ] **Step 3: Verify imports and suite**

Run: `venv\Scripts\python -c "import app; print('app imports OK')"`
Expected: `app imports OK`

Run: `venv\Scripts\python -m pytest tests -v`
Expected: all tests pass

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: wire provider/model selection and mixed-media inputs through /generate"
```

---

### Task 7: Frontend (`templates/index.html`)

**Files:**
- Modify: `templates/index.html`

- [ ] **Step 1: Replace the Characters field with toggle + three character inputs**

Replace the existing Characters `div.mb-3` (around lines 25–28) with:

```html
                    <div class="form-check mb-3">
                        <input class="form-check-input" type="checkbox" id="mixed_media">
                        <label class="form-check-label" for="mixed_media">
                            Mixed Media<br>
                            <small class="text-muted">photorealistic main characters in a cartoon world</small>
                        </label>
                    </div>
                    <div class="mb-3" id="classicCharactersField">
                        <label class="form-label">Characters</label>
                        <input type="text" class="form-control" id="characters" placeholder="e.g. a curious girl named Mia" required>
                    </div>
                    <div class="d-none" id="mixedMediaFields">
                        <div class="mb-3">
                            <label class="form-label">Photorealistic Characters</label>
                            <input type="text" class="form-control" id="photoreal_characters" placeholder="e.g. a happy adult man (Dad)">
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Cartoon Characters <small class="text-muted">(optional)</small></label>
                            <input type="text" class="form-control" id="cartoon_characters" placeholder="e.g. a toddler">
                        </div>
                    </div>
```

- [ ] **Step 2: Add the new Art Style option and the Provider/Image Model dropdowns**

In the Art Style `select`, add a new first option:

```html
                            <option>2D flat vector cartoon (pastel)</option>
```

(Keep `Watercolor storybook illustration` and the rest below it — watercolor remains the default selected option in classic mode because it is listed without `selected` and... NOTE: in plain HTML the FIRST option is default-selected. To keep watercolor the classic default, add `selected` to the watercolor option explicitly:)

```html
                            <option selected>Watercolor storybook illustration</option>
```

After the Art Style `div.mb-3`, add:

```html
                    <div class="mb-3">
                        <label class="form-label">Provider</label>
                        <select class="form-select" id="provider">
                            {% for pid, p in providers.items() %}
                            <option value="{{ pid }}" {% if pid == default_provider %}selected{% endif %}>{{ p.label }}</option>
                            {% endfor %}
                        </select>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Image Model</label>
                        <select class="form-select" id="image_model">
                            {% for m in providers[default_provider].image_models %}
                            <option value="{{ m.id }}" {% if m.id == default_image_model %}selected{% endif %}>{{ m.label }}</option>
                            {% endfor %}
                        </select>
                    </div>
```

- [ ] **Step 3: Add the toggle/repopulation JS and extend the payload**

At the top of the existing `<script>` block (right after `let currentStoryData = null;`), add:

```javascript
        const PROVIDER_MODELS = {{ providers | tojson }};

        // Mixed Media toggle: swap character fields, preselect the proven style
        document.getElementById('mixed_media').addEventListener('change', (e) => {
            const mixed = e.target.checked;
            document.getElementById('classicCharactersField').classList.toggle('d-none', mixed);
            document.getElementById('mixedMediaFields').classList.toggle('d-none', !mixed);
            document.getElementById('characters').required = !mixed;
            document.getElementById('photoreal_characters').required = mixed;
            if (mixed) {
                document.getElementById('art_style').value = '2D flat vector cartoon (pastel)';
            }
        });

        // Repopulate model list when provider changes (future-proofing; one provider today)
        document.getElementById('provider').addEventListener('change', (e) => {
            const select = document.getElementById('image_model');
            select.innerHTML = '';
            PROVIDER_MODELS[e.target.value].image_models.forEach(m => {
                const opt = document.createElement('option');
                opt.value = m.id;
                opt.textContent = m.label;
                select.appendChild(opt);
            });
        });
```

Then extend the `payload` object in the submit handler to:

```javascript
            const payload = {
                keywords: document.getElementById('keywords').value,
                characters: document.getElementById('characters').value,
                setting: document.getElementById('setting').value,
                story_type: document.getElementById('story_type').value,
                art_style: document.getElementById('art_style').value,
                provider: document.getElementById('provider').value,
                image_model: document.getElementById('image_model').value,
                mixed_media: document.getElementById('mixed_media').checked,
                photoreal_characters: document.getElementById('photoreal_characters').value,
                cartoon_characters: document.getElementById('cartoon_characters').value
            };
```

- [ ] **Step 4: Smoke-test the page renders**

Run: `venv\Scripts\python -c "import app; c = app.app.test_client(); r = c.get('/'); assert r.status_code == 200; html = r.data.decode(); assert 'gemini-2.5-flash-image' in html; assert 'mixed_media' in html; assert '2D flat vector cartoon (pastel)' in html; print('page renders OK')"`
Expected: `page renders OK`

(Works without an API key — `get_client()` is only called inside generation.)

- [ ] **Step 5: Commit**

```bash
git add templates/index.html
git commit -m "feat: add mixed-media toggle and provider/model dropdowns to UI"
```

---

### Task 8: Manual end-to-end validation (costs ~$1–2 CAD, needs GEMINI_API_KEY)

**Files:**
- None (manual verification; note results in commit message or PR description)

**STOP — check with the user before this task**: it spends real API money. Confirm they want to run it now and whether they will drive the browser themselves.

- [ ] **Step 1: Start the app**

Run: `venv\Scripts\python app.py`
Expected: Flask dev server on http://localhost:5000

- [ ] **Step 2: Classic-mode regression book**

In the browser: defaults (Mixed Media unchecked, Watercolor, Flash model), e.g. keywords "ice cream, rainbows", characters "a curious girl named Mia", setting "a candy forest". Generate.
Expected: behaves exactly as before this branch — 5 watercolor images, captions, PDF downloads.

- [ ] **Step 3: Mixed-media book on Flash**

Check Mixed Media (art style auto-flips to "2D flat vector cartoon (pastel)"), photoreal characters "a happy adult man (Dad)", cartoon characters "a toddler", keywords "playground, slide", setting "a kids playground". Generate.
Expected: 5 images where Dad reads as photographic against a flat pastel cartoon world; `outputs/story_<ts>/story.json` shows every `image_prompt` starting with "A mixed media children's book illustration collage." and containing the contrast sentence.

- [ ] **Step 4: Mixed-media book on Pro**

Same inputs, Image Model = "Gemini 3 Pro Image (Nano Banana Pro)". Generate.
Expected: same structure, visibly higher quality/consistency; confirms the model dropdown actually switches the API call (check the `model:` in the server logs).

- [ ] **Step 5: Validation-error spot checks**

With Mixed Media checked and Photorealistic Characters empty, the browser's `required` blocks submit. Via curl/PowerShell, POST `/generate` with `"provider": "openai"` →
Expected: HTTP 400, `{"error": "Unknown provider: 'openai'"}`.

- [ ] **Step 6: Record results and commit any prompt tweaks**

If prompts needed tuning during review, commit the tweaks:

```bash
git add -A
git commit -m "tune: adjust mixed-media prompts after manual review"
```

---

## Self-Review Notes (completed at planning time)

- **Spec coverage:** §1 providers → Task 2+4; §2 prompt assembly + story gen → Tasks 3+5; §3 frontend → Task 7; §4 Flask → Task 6; §5 error handling → Tasks 6 (400s) + 8 step 5; §6 testing → Tasks 2/3/5 (unit) + 8 (manual). New art-style option → Task 7 step 2.
- **Type consistency:** `generate_image(prompt, context_images, model) -> bytes` matches between Task 2 (definition) and Task 4 (call site). `assemble_mixed_media_prompt(scene, photoreal_characters, cartoon_characters, art_style)` matches between Task 3 and Task 5. `generate_all_images(story, output_dir, provider, model)` matches between Task 4 and Task 6.
- **Known mid-plan inconsistency (intentional):** after Task 4, `app.py`'s call site is stale until Task 6 — documented in Task 4 step 3; nothing executes that path in between.
