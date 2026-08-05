# Face-Swap Photo Upload for Photoreal Characters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user upload a photo of a real person per photoreal character and have Gemini preserve that person's face/identity while generating body, pose, and clothing from the same structured description fields already in the UI.

**Architecture:** A new `/upload_photo` Flask endpoint validates and normalizes an uploaded image via Pillow and saves it under `outputs/_uploads/<uuid>.png`, returning a path that the frontend stores on the character object as `photo_path`. `generate_reference_images` reads that path per photoreal character, passes the photo's bytes as `context_images` into the *same* Gemini reference-generation call it already makes (with a face-preservation prompt variant from `assemble_reference_prompt`), and copies the original upload into the story's `refs/` folder alongside the generated reference so a human can visually compare input face vs. output character. Nothing downstream of reference generation (the 5-scene sliding window, scene prompt assembly, PDF export) changes.

**Tech Stack:** Flask, Pillow, google-genai (via the existing `ImageProvider` abstraction — no new vendor), pytest with `monkeypatch`/`tmp_path`, vanilla JS + Bootstrap (no new frontend dependencies).

**Spec:** [2026-06-16-face-swap-photo-upload-design.md](../specs/2026-06-16-face-swap-photo-upload-design.md) — read this first for the locked decisions and full rationale. This plan implements it exactly; do not add the two-step generate-then-swap fallback, multi-photo-per-character, consent UI, or `_uploads/` cleanup — all explicitly deferred in the spec.

**Checkpoint convention:** Per project convention, keep `docs/superpowers/plans/CHECKPOINT.md` updated with done/next/pending status after every task in this plan (not just at the end). This plan does not include it as a separate task — update it continuously as you go.

---

## File Structure

| File | Change |
|---|---|
| `app.py` | `CHARACTER_FIELDS` gains `photo_path`; new `MAX_CONTENT_LENGTH` config, `ALLOWED_PHOTO_EXTENSIONS`, `_save_uploaded_photo()` helper, `POST /upload_photo` route |
| `prompt_assembly.py` | `assemble_reference_prompt` gains `has_photo: bool = False`; photoreal branch grows a face-preservation variant; cartoon branch untouched |
| `image_generator.py` | `generate_reference_images` reads `char["photo_path"]`, conditionally passes photo bytes as `context_images`, copies the upload into `refs/`, adds `from_photo` to each record |
| `templates/index.html` | photoreal character cards gain a file input + thumbnail + hidden `.field-photo-path`; upload-on-select wiring; `collectCharacters` reads the new field; Generate button disabled while uploads are in flight |
| `tests/test_app_generate.py` | fix the one assertion broken by the new `CHARACTER_FIELDS` entry; add round-trip + photo-only-character tests; extend the render-smoke test |
| `tests/test_reference_prompt.py` | add `has_photo` coverage (face-preservation language, no-photo regression pin, cartoon ignores it) |
| `tests/test_reference_generation.py` | add photo-path-aware coverage (context images, prompt difference, upload copy, `from_photo`, stale-path fallback, cartoon ignores photo) |
| `tests/test_upload_photo.py` (new) | endpoint tests: valid PNG/JPEG, missing field, bad extension, corrupt bytes, oversized payload (413), oversized dimensions capped |
| `docs/superpowers/specs/2026-06-16-face-swap-photo-upload-design.md` | Status line updated once implemented |

No `tests/conftest.py` exists in this project — each test file defines its own local `client` fixture. `tests/test_upload_photo.py` follows that existing convention rather than introducing a shared fixture file.

---

## Task 1: Data model — `photo_path` field

**Files:**
- Modify: `app.py:20`
- Test: `tests/test_app_generate.py`

- [ ] **Step 1: Update the existing test and add two new ones**

Replace the existing `test_normalize_drops_empty_and_trims` (currently `tests/test_app_generate.py:34-41`) and add two new tests directly after `test_normalize_non_list_returns_empty` (currently ending at line 47, just before the `# --- validation` comment):

```python
def test_normalize_drops_empty_and_trims():
    out = app_module._normalize_characters([
        {"name": "  Dad  ", "hair_color": "brown"},
        {"name": "", "description": "   "},   # fully empty -> dropped
        "not-a-dict",                          # ignored
    ])
    assert out == [{"name": "Dad", "skin_tone": "", "hair_color": "brown",
                    "body_type": "", "height": "", "description": "", "photo_path": ""}]


def test_normalize_non_list_returns_empty():
    assert app_module._normalize_characters(None) == []
    assert app_module._normalize_characters("Dad") == []


def test_normalize_carries_photo_path_through():
    out = app_module._normalize_characters([
        {"name": "Dad", "photo_path": "outputs/_uploads/abc123.png"},
    ])
    assert out == [{"name": "Dad", "skin_tone": "", "hair_color": "",
                    "body_type": "", "height": "", "description": "",
                    "photo_path": "outputs/_uploads/abc123.png"}]


def test_normalize_keeps_photo_only_character():
    out = app_module._normalize_characters([
        {"name": "", "photo_path": "outputs/_uploads/abc123.png"},
    ])
    assert len(out) == 1
    assert out[0]["photo_path"] == "outputs/_uploads/abc123.png"
    assert out[0]["name"] == ""
```

(Only `test_normalize_drops_empty_and_trims`'s expected dict literal changes — gains `"photo_path": ""`. The other two are new.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv\Scripts\python.exe -m pytest tests/test_app_generate.py -v`
Expected: `test_normalize_drops_empty_and_trims` FAILS (dict mismatch — actual dict has no `photo_path` key). `test_normalize_keeps_photo_only_character` FAILS (`len(out) == 1` — actual is `0`, since a photo-only dict has no truthy value under the current `CHARACTER_FIELDS` and gets dropped as "empty"). `test_normalize_carries_photo_path_through` FAILS similarly (dict mismatch, missing key).

- [ ] **Step 3: Add `photo_path` to `CHARACTER_FIELDS`**

In `app.py`, replace line 20:

```python
CHARACTER_FIELDS = ("name", "skin_tone", "hair_color", "body_type", "height", "description")
```

with:

```python
CHARACTER_FIELDS = ("name", "skin_tone", "hair_color", "body_type", "height",
                    "description", "photo_path")
```

No other change is needed — `_normalize_characters` (lines 24-39) already builds its result dict by iterating `CHARACTER_FIELDS`, so `photo_path` flows through automatically, including the "keep if any field is truthy" check.

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv\Scripts\python.exe -m pytest tests/test_app_generate.py -v`
Expected: PASS (all tests in the file, including the 3 above).

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_app_generate.py
git commit -m "feat: add photo_path to structured character data model"
```

---

## Task 2: Reference prompt — face-preservation language

**Files:**
- Modify: `prompt_assembly.py:120-145`
- Test: `tests/test_reference_prompt.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_reference_prompt.py`, after `test_photoreal_has_no_cartoon_style_words` (currently ending at line 38, just before the `# --- cartoon` comment):

```python
def test_photoreal_with_photo_includes_face_preservation_language():
    p = assemble_reference_prompt(CHAR, "photoreal", "watercolor storybook illustration",
                                   has_photo=True)
    low = p.lower()
    assert "attached photo" in low
    assert "exact face and identity" in low
    assert "Dad" in p


def test_photoreal_without_photo_unchanged():
    # Regression pin: has_photo=False (the default) must produce byte-for-byte
    # the same prompt as before this parameter existed.
    p = assemble_reference_prompt(CHAR, "photoreal", "watercolor storybook illustration")
    assert p == (
        "A photorealistic, high-resolution full-body studio photograph of "
        "Dad: tall height, medium skin tone, dark brown hair, average build, "
        "green sweater, blue jeans. Natural lighting, plain neutral background, "
        "sharp focus, neutral friendly expression, looking at the camera. "
        "This is a real photograph of a real person. "
        "No text or words in the image."
    )
```

And after `test_cartoon_every_style_produces_its_phrases` (currently ending at line 63, just before the `# --- shared` comment):

```python
def test_cartoon_ignores_has_photo():
    style = "watercolor storybook illustration"
    with_photo = assemble_reference_prompt(CHAR, "cartoon", style, has_photo=True)
    without_photo = assemble_reference_prompt(CHAR, "cartoon", style, has_photo=False)
    assert with_photo == without_photo
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv\Scripts\python.exe -m pytest tests/test_reference_prompt.py -v`
Expected: `test_photoreal_with_photo_includes_face_preservation_language` FAILS with `TypeError: assemble_reference_prompt() got an unexpected keyword argument 'has_photo'`. `test_cartoon_ignores_has_photo` FAILS the same way. `test_photoreal_without_photo_unchanged` already PASSES (it's a pin on current behavior, not new behavior) — confirm it passes now so you know the literal is correct before the function changes under it.

- [ ] **Step 3: Implement `has_photo`**

In `prompt_assembly.py`, replace `assemble_reference_prompt` (lines 120-145):

```python
def assemble_reference_prompt(char: dict, kind: str, art_style: str, has_photo: bool = False) -> str:
    """Build a standalone reference-image prompt for one character.

    kind="photoreal": reads as a real studio photograph — deliberately carries
    NO art-style words so the person never picks up a 2D/cartoon look. When
    has_photo=True, an uploaded photo of the real person is attached as context
    to the generation call, so the prompt instead asks Gemini to preserve that
    photo's exact face/identity while still generating body/pose/clothing from
    the description.
    kind="cartoon": a flat 2D character sheet in the chosen STYLE_PHRASES look.
    Ignores has_photo entirely — there is no cartoon upload UI to ever set it True.
    The reference is generated with no context images (other than the uploaded
    photo, when present) so characters never blend with each other.
    """
    description = _clause(compose_character_description(char))

    if kind == "photoreal":
        if has_photo:
            return (
                "Using the exact face and identity of the person in the attached "
                "photo — same facial features, skin tone, and likeness, face "
                "unchanged from the photo — generate a photorealistic, "
                f"high-resolution full-body studio photograph of {description}. "
                "Natural lighting, plain neutral background, sharp focus, "
                "neutral friendly expression, looking at the camera. "
                "This is a real photograph of a real person. "
                "No text or words in the image."
            )
        return (
            "A photorealistic, high-resolution full-body studio photograph of "
            f"{description}. Natural lighting, plain neutral background, sharp focus, "
            "neutral friendly expression, looking at the camera. "
            "This is a real photograph of a real person. "
            "No text or words in the image."
        )

    phrases = STYLE_PHRASES.get(art_style.lower().strip(), STYLE_PHRASES[DEFAULT_STYLE])
    return (
        f"A {phrases['world_phrase']} character reference of {description}. "
        "Full body, front view, plain background. "
        f"{phrases['style_closer']}. "
        "No text or words in the image."
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv\Scripts\python.exe -m pytest tests/test_reference_prompt.py -v`
Expected: PASS (all tests in the file).

- [ ] **Step 5: Commit**

```bash
git add prompt_assembly.py tests/test_reference_prompt.py
git commit -m "feat: add face-preservation prompt variant for photo-based references"
```

---

## Task 3: Reference generation — wire `photo_path` through

**Files:**
- Modify: `image_generator.py:1-10`, `image_generator.py:145-190`
- Test: `tests/test_reference_generation.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_reference_generation.py`, after `test_prompt_routing_by_kind` (the last test in the file, currently ending at line 70):

```python
def test_photo_path_passed_as_context_images(tmp_path):
    photo_path = tmp_path / "upload.png"
    photo_path.write_bytes(b"FAKE-UPLOADED-PHOTO-BYTES")
    provider = FakeProvider()
    generate_reference_images(
        [{"name": "Dad", "photo_path": str(photo_path)}], [], STYLE, str(tmp_path), provider, "m",
    )
    assert provider.calls[0]["context_images"] == [b"FAKE-UPLOADED-PHOTO-BYTES"]


def test_photo_based_prompt_differs_from_no_photo(tmp_path):
    photo_path = tmp_path / "upload.png"
    photo_path.write_bytes(b"FAKE-UPLOADED-PHOTO-BYTES")
    provider = FakeProvider()
    generate_reference_images(
        [{"name": "Dad", "photo_path": str(photo_path)}], [], STYLE, str(tmp_path), provider, "m",
    )
    generate_reference_images([{"name": "Dad"}], [], STYLE, str(tmp_path), provider, "m")
    assert provider.calls[0]["prompt"] != provider.calls[1]["prompt"]
    assert "attached" in provider.calls[0]["prompt"].lower()


def test_upload_copy_saved_alongside_reference(tmp_path):
    photo_path = tmp_path / "upload.png"
    photo_path.write_bytes(b"FAKE-UPLOADED-PHOTO-BYTES")
    provider = FakeProvider()
    records = generate_reference_images(
        [{"name": "Dad", "photo_path": str(photo_path)}], [], STYLE, str(tmp_path), provider, "m",
    )
    refs_dir = os.path.dirname(records[0]["path"])
    upload_copy = os.path.join(refs_dir, "photoreal_1_upload.png")
    assert os.path.exists(upload_copy)
    with open(upload_copy, "rb") as f:
        assert f.read() == b"FAKE-UPLOADED-PHOTO-BYTES"


def test_from_photo_field_in_records(tmp_path):
    photo_path = tmp_path / "upload.png"
    photo_path.write_bytes(b"FAKE-UPLOADED-PHOTO-BYTES")
    provider = FakeProvider()
    records = generate_reference_images(
        [{"name": "Dad", "photo_path": str(photo_path)}, {"name": "Mom"}], [],
        STYLE, str(tmp_path), provider, "m",
    )
    assert records[0]["from_photo"] is True
    assert records[1]["from_photo"] is False


def test_missing_photo_path_falls_back_to_no_context(tmp_path):
    provider = FakeProvider()
    records = generate_reference_images(
        [{"name": "Dad", "photo_path": str(tmp_path / "does_not_exist.png")}], [],
        STYLE, str(tmp_path), provider, "m",
    )
    assert provider.calls[0]["context_images"] == []
    assert records[0]["from_photo"] is False


def test_cartoon_character_with_photo_path_ignored(tmp_path):
    photo_path = tmp_path / "upload.png"
    photo_path.write_bytes(b"FAKE-UPLOADED-PHOTO-BYTES")
    provider = FakeProvider()
    records = generate_reference_images(
        [], [{"name": "Lily", "photo_path": str(photo_path)}],
        STYLE, str(tmp_path), provider, "m",
    )
    assert provider.calls[0]["context_images"] == []
    assert records[0]["from_photo"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv\Scripts\python.exe -m pytest tests/test_reference_generation.py -v`
Expected: all 6 new tests FAIL — `test_photo_path_passed_as_context_images` and `test_missing_photo_path_falls_back_to_no_context` fail on the `context_images` assertion (currently always `[]` regardless of `photo_path`); `test_photo_based_prompt_differs_from_no_photo` fails because both prompts are currently identical; `test_upload_copy_saved_alongside_reference` fails because the upload copy file doesn't exist; `test_from_photo_field_in_records`, `test_missing_photo_path_falls_back_to_no_context`, and `test_cartoon_character_with_photo_path_ignored` fail with `KeyError: 'from_photo'`.

- [ ] **Step 3: Implement**

In `image_generator.py`, add `shutil` to the imports (line 1-4 currently read `import os` / `import io` / `import time` / `import logging`):

```python
import os
import io
import shutil
import time
import logging
```

Replace `generate_reference_images` (lines 145-190):

```python
def generate_reference_images(
    photoreal_characters: list,
    cartoon_characters: list,
    art_style: str,
    output_dir: str,
    provider,
    model: str,
) -> list:
    """Generate one standalone reference image per character.

    Order is the reference-ordering invariant shared with the prompt assembler and
    generate_all_images: photoreal characters first, then cartoon. Saved under
    <output_dir>/refs/ as <kind>_<index>.png with NO caption (these anchor the
    characters' appearance and must stay clean). Cartoon characters are skipped
    entirely when that list is empty.

    Photoreal characters with a usable photo_path (photoreal only — cartoon never
    has upload UI) pass that photo's bytes as context_images and get a
    face-preservation prompt; the original photo is copied alongside the
    generated reference as <kind>_<index>_upload.png. A missing/stale photo_path
    degrades gracefully to the no-photo path.

    Returns ordered records: [{"kind", "index", "name", "path", "from_photo"}, ...].
    """
    refs_dir = os.path.join(output_dir, "refs")
    os.makedirs(refs_dir, exist_ok=True)

    records = []
    groups = (
        ("photoreal", photoreal_characters or []),
        ("cartoon", cartoon_characters or []),
    )
    for kind, chars in groups:
        for index, char in enumerate(chars, start=1):
            photo_path = char.get("photo_path") if kind == "photoreal" else None
            has_photo = bool(photo_path) and os.path.exists(photo_path)

            prompt = assemble_reference_prompt(char, kind, art_style, has_photo=has_photo)
            label = character_label(char)
            logger.info(f"Generating {kind} reference {index} ({label})"
                        f"{' from uploaded photo' if has_photo else ''}")
            start = time.time()

            context_images = _load_context_bytes([photo_path]) if has_photo else []
            image_data = provider.generate_image(
                prompt=prompt, context_images=context_images, model=model
            )

            logger.info(f"Reference image received in {time.time() - start:.1f}s")
            path = os.path.join(refs_dir, f"{kind}_{index}.png")
            with open(path, "wb") as f:
                f.write(image_data)

            if has_photo:
                upload_copy_path = os.path.join(refs_dir, f"{kind}_{index}_upload.png")
                shutil.copyfile(photo_path, upload_copy_path)

            records.append({
                "kind": kind, "index": index, "name": label,
                "path": path, "from_photo": has_photo,
            })

    logger.info(f"{len(records)} character reference image(s) generated.")
    return records
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv\Scripts\python.exe -m pytest tests/test_reference_generation.py -v`
Expected: PASS (all tests in the file, old and new).

Then run the full suite to confirm no regressions: `venv\Scripts\python.exe -m pytest -v`
Expected: PASS (all tests across the project).

- [ ] **Step 5: Commit**

```bash
git add image_generator.py tests/test_reference_generation.py
git commit -m "feat: pass uploaded photo bytes into reference generation"
```

---

## Task 4: Upload endpoint — `POST /upload_photo`

**Files:**
- Modify: `app.py:1-21`, `app.py` (insert after line 39)
- Test: `tests/test_upload_photo.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_upload_photo.py`. This file defines its own local `client` fixture rather than relying on a shared one — this project has no `tests/conftest.py`, and `tests/test_app_generate.py` already establishes the convention of a per-file local fixture:

```python
import io
import os

import pytest
from PIL import Image

import app as app_module


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def _image_bytes(fmt: str, size=(100, 100)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=(200, 50, 50)).save(buf, format=fmt)
    return buf.getvalue()


def test_valid_png_upload_returns_path(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    data = {"photo": (io.BytesIO(_image_bytes("PNG")), "me.png")}
    resp = client.post("/upload_photo", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    path = resp.get_json()["photo_path"]
    assert os.path.exists(path)
    assert path.endswith(".png")


def test_valid_jpeg_upload_converted_to_png(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    data = {"photo": (io.BytesIO(_image_bytes("JPEG")), "me.jpg")}
    resp = client.post("/upload_photo", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    path = resp.get_json()["photo_path"]
    assert path.endswith(".png")
    with Image.open(path) as img:
        assert img.format == "PNG"


def test_missing_photo_field_returns_400(client):
    resp = client.post("/upload_photo", data={}, content_type="multipart/form-data")
    assert resp.status_code == 400


def test_disallowed_extension_returns_400(client):
    data = {"photo": (io.BytesIO(b"not an image"), "me.gif")}
    resp = client.post("/upload_photo", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400


def test_corrupt_bytes_with_allowed_extension_returns_400(client):
    data = {"photo": (io.BytesIO(b"this is not a real png"), "me.png")}
    resp = client.post("/upload_photo", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400


def test_oversized_payload_returns_413(client):
    oversized = b"\x00" * (9 * 1024 * 1024)  # over the 8MB cap; never decoded
    data = {"photo": (io.BytesIO(oversized), "me.png")}
    resp = client.post("/upload_photo", data=data, content_type="multipart/form-data")
    assert resp.status_code == 413


def test_oversized_dimensions_capped(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    data = {"photo": (io.BytesIO(_image_bytes("PNG", size=(2000, 2000))), "big.png")}
    resp = client.post("/upload_photo", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    path = resp.get_json()["photo_path"]
    with Image.open(path) as img:
        assert img.size == (1536, 1536)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv\Scripts\python.exe -m pytest tests/test_upload_photo.py -v`
Expected: all 7 tests FAIL with 404 (the `/upload_photo` route doesn't exist yet, so Flask returns "Not Found" for every request, including the oversized-payload one — `MAX_CONTENT_LENGTH` isn't configured yet either).

- [ ] **Step 3: Implement**

In `app.py`, replace the imports and module-level setup (lines 1-21):

```python
import os
import json
import time
import uuid
import datetime
import logging
from io import BytesIO
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
from PIL import Image

from story_generator import generate_story
from image_generator import generate_all_images, generate_reference_images, generate_pdf
from config import OUTPUT_DIR, DEFAULT_PROVIDER, DEFAULT_IMAGE_MODEL
from providers import get_provider, validate_model, providers_meta

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8MB cap on uploaded photos

# Structured-character handling (mixed-media mode)
CHARACTER_FIELDS = ("name", "skin_tone", "hair_color", "body_type", "height",
                    "description", "photo_path")
MAX_CHARACTERS = 6  # soft cap to bound request size / cost across refs + window

# Photo upload handling (face-swap reference photos)
ALLOWED_PHOTO_EXTENSIONS = {".png", ".jpg", ".jpeg"}
MAX_PHOTO_DIMENSION = 1536
```

Then insert this helper and route right after `_normalize_characters` (after line 39, before the `@app.route('/')` index view on line 41):

```python
def _save_uploaded_photo(file_storage) -> str:
    """Validate, normalize, and persist an uploaded character photo.

    Validates the extension before attempting to decode (cheap rejection for
    obviously-wrong files), normalizes via Pillow to RGB and a max 1536px
    dimension, and saves as PNG under a UUID filename — filenames are never
    user-derived, which sidesteps path traversal entirely. Raises ValueError
    for any client-caused problem (caught by the route and turned into a 400).
    The upload directory is computed fresh from OUTPUT_DIR on every call (not
    cached as a module-level constant) so tests that monkeypatch OUTPUT_DIR
    affect it correctly.
    """
    filename = file_storage.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_PHOTO_EXTENSIONS:
        raise ValueError("Photo must be a PNG or JPG file.")

    try:
        img = Image.open(file_storage.stream).convert("RGB")
    except Exception:
        raise ValueError("Could not read photo file.")

    img.thumbnail((MAX_PHOTO_DIMENSION, MAX_PHOTO_DIMENSION))

    upload_dir = os.path.join(OUTPUT_DIR, "_uploads")
    os.makedirs(upload_dir, exist_ok=True)
    path = os.path.join(upload_dir, f"{uuid.uuid4().hex}.png")
    img.save(path, "PNG")
    return path


@app.route('/upload_photo', methods=['POST'])
def upload_photo():
    file = request.files.get('photo')
    if not file or not file.filename:
        return jsonify({"error": "No photo file provided."}), 400
    try:
        path = _save_uploaded_photo(file)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Photo upload error: {e}")
        return jsonify({"error": "Could not process photo."}), 500
    return jsonify({"photo_path": path})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv\Scripts\python.exe -m pytest tests/test_upload_photo.py -v`
Expected: PASS (all 7 tests).

Then run the full suite: `venv\Scripts\python.exe -m pytest -v`
Expected: PASS (all tests across the project — confirms the new `MAX_CONTENT_LENGTH` config and import changes didn't break `/generate` or `/download_pdf`, whose JSON payloads are well under 8MB).

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_upload_photo.py
git commit -m "feat: add POST /upload_photo endpoint for character reference photos"
```

---

## Task 5: Frontend — upload UI on photoreal cards

**Files:**
- Modify: `templates/index.html`
- Test: `tests/test_app_generate.py` (render-smoke test)

- [ ] **Step 1: Extend the render-smoke test**

In `tests/test_app_generate.py`, replace `test_index_renders_character_ui` (lines 23-29):

```python
def test_index_renders_character_ui(client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    for token in ("photorealCharacterList", "cartoonCharacterList",
                  "addPhotorealBtn", "addCartoonBtn", "proHint",
                  "field-photo-input", "/upload_photo"):
        assert token in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv\Scripts\python.exe -m pytest tests/test_app_generate.py::test_index_renders_character_ui -v`
Expected: FAIL — `"field-photo-input" in body` is `False` (the upload markup doesn't exist yet).

- [ ] **Step 3: Implement**

In `templates/index.html`, add a `pendingUploads` counter right after `let currentStoryData = null;` (line 120):

```javascript
        let currentStoryData = null;
        let pendingUploads = 0;
```

Add a `photoUploadHTML()` helper right after the `selectHTML` function (after line 135, before the `// Build one character card` comment):

```javascript
        // Photoreal-only photo upload block: file input + thumbnail + hidden path.
        function photoUploadHTML() {
            return (
                '<div class="mb-2">' +
                  '<input type="file" class="form-control form-control-sm field-photo-input" accept=".png,.jpg,.jpeg">' +
                  '<img class="img-thumbnail mt-1 d-none field-photo-thumb" style="max-height:80px;">' +
                  '<small class="text-muted d-block field-photo-status"></small>' +
                  '<input type="hidden" class="field-photo-path" value="">' +
                '</div>'
            );
        }

        // Wire a photoreal card's file input: upload immediately on selection,
        // show a thumbnail preview, and stash the server-assigned path for submit.
        function attachPhotoUploadHandler(card) {
            const input = card.querySelector('.field-photo-input');
            const thumb = card.querySelector('.field-photo-thumb');
            const status = card.querySelector('.field-photo-status');
            const pathField = card.querySelector('.field-photo-path');

            input.addEventListener('change', async () => {
                const file = input.files[0];
                pathField.value = '';
                if (!file) {
                    thumb.classList.add('d-none');
                    status.textContent = '';
                    return;
                }

                thumb.src = URL.createObjectURL(file);
                thumb.classList.remove('d-none');
                status.textContent = 'Uploading…';

                pendingUploads++;
                document.getElementById('generateBtn').disabled = true;

                try {
                    const formData = new FormData();
                    formData.append('photo', file);
                    const response = await fetch('/upload_photo', { method: 'POST', body: formData });
                    const data = await response.json();
                    if (!response.ok) throw new Error(data.error || 'Upload failed');
                    pathField.value = data.photo_path;
                    status.textContent = 'Photo attached.';
                } catch (err) {
                    status.textContent = err.message;
                } finally {
                    pendingUploads--;
                    if (pendingUploads === 0) {
                        document.getElementById('generateBtn').disabled = false;
                    }
                }
            });
        }
```

Replace `addCharacterCard` (currently lines 137-160 — the comment line plus the function):

```javascript
        // Build one character card (static markup; no user data interpolated here).
        // Photo upload UI is only added for photoreal cards (cartoon characters never
        // get an upload widget).
        function addCharacterCard(listId) {
            const isPhotoreal = listId === 'photorealCharacterList';
            const list = document.getElementById(listId);
            const card = document.createElement('div');
            card.className = 'card mb-2 character-card';
            card.innerHTML =
                '<div class="card-body p-2">' +
                  '<div class="d-flex mb-2">' +
                    '<input type="text" class="form-control form-control-sm field-name" placeholder="Name (e.g. Dad)">' +
                    '<button type="button" class="btn btn-sm btn-outline-danger ms-2 remove-character" title="Remove">&times;</button>' +
                  '</div>' +
                  (isPhotoreal ? photoUploadHTML() : '') +
                  '<div class="row g-1 mb-2">' +
                    '<div class="col-6">' + selectHTML('field-skin-tone', 'Skin tone…', SKIN_TONES) + '</div>' +
                    '<div class="col-6">' + selectHTML('field-hair-color', 'Hair color…', HAIR_COLORS) + '</div>' +
                    '<div class="col-6">' + selectHTML('field-body-type', 'Body type…', BODY_TYPES) + '</div>' +
                    '<div class="col-6">' + selectHTML('field-height', 'Height…', HEIGHTS) + '</div>' +
                  '</div>' +
                  '<textarea class="form-control form-control-sm field-description" rows="4" ' +
                    'placeholder="Anything else — clothing, age, glasses, accessories…"></textarea>' +
                '</div>';
            card.querySelector('.remove-character').addEventListener('click', () => card.remove());
            if (isPhotoreal) {
                attachPhotoUploadHandler(card);
            }
            list.appendChild(card);
            return card;
        }
```

Replace `collectCharacters` (currently lines 163-172):

```javascript
        // Read a character list into an array of objects, dropping fully-empty cards.
        function collectCharacters(listId) {
            return [...document.querySelectorAll('#' + listId + ' .character-card')].map(card => {
                const photoField = card.querySelector('.field-photo-path');
                return {
                    name: card.querySelector('.field-name').value.trim(),
                    skin_tone: card.querySelector('.field-skin-tone').value,
                    hair_color: card.querySelector('.field-hair-color').value,
                    body_type: card.querySelector('.field-body-type').value,
                    height: card.querySelector('.field-height').value,
                    description: card.querySelector('.field-description').value.trim(),
                    photo_path: photoField ? photoField.value : '',
                };
            }).filter(c => c.name || c.description || c.skin_tone || c.hair_color || c.body_type || c.height || c.photo_path);
        }
```

No other parts of `templates/index.html` change: `addPhotorealBtn`/`addCartoonBtn` listeners already call `addCharacterCard` with the right `listId` and need no edits; the mixed-media toggle's seeded `addCharacterCard('photorealCharacterList')` call automatically gets the new upload UI.

- [ ] **Step 4: Run test to verify it passes**

Run: `venv\Scripts\python.exe -m pytest tests/test_app_generate.py -v`
Expected: PASS (all tests in the file).

Then run the full suite: `venv\Scripts\python.exe -m pytest -v`
Expected: PASS (all tests across the project).

- [ ] **Step 5: Commit**

```bash
git add templates/index.html tests/test_app_generate.py
git commit -m "feat: add per-character photo upload UI to photoreal cards"
```

---

## Task 6: Docs — mark the spec implemented

**Files:**
- Modify: `docs/superpowers/specs/2026-06-16-face-swap-photo-upload-design.md:5`

- [ ] **Step 1: Update the status line**

Replace:

```
**Status:** Approved by Ritvik (2026-06-16); implementation pending
```

with:

```
**Status:** Implemented (Tasks 1–6); pending manual E2E (Task 7)
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-06-16-face-swap-photo-upload-design.md
git commit -m "docs: mark face-swap photo upload spec implemented"
```

---

## Task 7: Manual E2E (USER runs; needs `GEMINI_API_KEY`)

Not subagent-executable — costs real Gemini API calls and needs human visual judgment. Cost is unchanged from the existing reference-image pipeline: one image-generation call per character either way (~$1.4 CAD/book on Pro for ~3 characters, per the prior feature's cost model).

1. `venv\Scripts\python.exe app.py` → http://localhost:5000
2. Enable Mixed Media, add one photoreal character (e.g. "Dad"), upload a real test photo. Confirm: thumbnail appears immediately; status flips to "Photo attached."; Generate Story button is disabled during the upload and re-enables after.
3. Fill in the rest of the form (keywords, setting, etc.) and submit. Confirm the run completes and `outputs/story_<timestamp>/refs/` contains both `photoreal_1.png` (Gemini's generated reference) and `photoreal_1_upload.png` (the original photo) side by side.
4. **Visual check (the main thing to evaluate):** open both files. Does `photoreal_1.png` preserve the uploaded photo's face/identity while reflecting the character's description fields (clothing, etc.)? Does it stay anchored to the description's pose/body, or does it over-anchor to the uploaded photo's own pose/background (the risk called out in the spec)?
5. Confirm `story.json`'s `character_refs` entry for Dad has `"from_photo": true`.
6. Add a second photoreal character (e.g. "Mom") with no photo upload. Confirm her reference generates normally (no upload UI artifacts, `"from_photo": false`), and Dad's face-swapped reference is unaffected by the no-photo path running alongside it.
7. Error path: try uploading a non-image file (e.g. a `.txt` renamed to `.png`) and confirm the UI surfaces the "Could not read photo file." error from `/upload_photo` instead of silently failing.
8. Record results in `docs/superpowers/plans/CHECKPOINT.md`. If Gemini over-anchors to the photo's pose/background (risk in the spec), note it — the documented fallback (not built) is a two-step generate-then-swap call, out of scope for this plan.
