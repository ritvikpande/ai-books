# Design Spec — Face-Swap Photo Upload for Photoreal Characters

**Date:** 2026-06-16
**Branch:** `feat/face-swap`
**Status:** Implemented and manually E2E-tested (2026-06-17). Face-swap quality on Gemini 3 Pro was excellent. Two follow-ups from E2E: (1) a white sticker/cutout border around characters was fixed by removing "collage" prompt wording; (2) measured cost was ~CAD 3.5–3.8 for a 5-page book — over the POC ceiling (see Cost).
**Builds on:** [2026-06-15-character-reference-images-design.md](2026-06-15-character-reference-images-design.md)

## Motivation

The reference-image pipeline built in the prior feature generates each photoreal
character's reference image purely from a text description. That prior design doc
explicitly named the gap: "Photo upload / real-face likeness anchoring (the eventual
'face-swap' goal — next iteration)." This spec is that iteration: let the user upload
a photo of a real person per photoreal character, and have Gemini preserve that
person's face/identity while generating the body, pose, and clothing from the same
structured description fields already in the UI.

Because the reference-image pipeline already anchors every scene to a per-character
reference image, this feature only needs to change *how that one reference image is
produced* for characters with an uploaded photo. Nothing downstream (the 5-scene
sliding window, scene prompt assembly, PDF export) needs to change.

## Locked decisions

- **Per-character upload.** Each photoreal character card gets its own optional photo
  upload (e.g. Dad's photo → Dad, Mom's photo → Mom). Cartoon character cards never get
  an upload widget.
- **Single combined Gemini call, no separate "swap" step.** When a photoreal character
  has an uploaded photo, its bytes are passed as `context_images` into the *same*
  reference-generation call used today, with a modified prompt instructing Gemini to
  keep the uploaded photo's exact face/identity while generating body/pose/clothing from
  the character's description fields. This reuses `generate_reference_images` and
  `provider.generate_image` almost unchanged — no new module, no second vendor/API.
- **`refs/` folder is the only visual-testing mechanism.** When a character has an
  uploaded photo, both the original upload and the final Gemini-generated reference are
  saved into that story's `refs/` folder side by side, so a human can visually compare
  input face vs. output character after a normal run. No standalone test harness.
- **POC privacy scope.** This proceeds under the project's existing POC assumptions —
  developer's own/consenting test photos, no new consent UI, no retention/deletion
  policy. This supersedes the "out of scope, pending privacy/child-safety review" note
  in the 2026-06-12 spec; the user has explicitly asked to build it now.

## Data model

`CHARACTER_FIELDS` in `app.py` gains one entry:

```python
CHARACTER_FIELDS = ("name", "skin_tone", "hair_color", "body_type", "height",
                    "description", "photo_path")
```

`photo_path` flows through `_normalize_characters` exactly like every other field (no
special-casing needed — it's just another string). It is populated by the new upload
endpoint, never typed by the user directly. `compose_character_description` and
`character_label` only read specific named keys, so they're unaffected by the new key.

A character with a photo but no name is valid and kept (not dropped by the "empty
character" filter) — it will simply be labeled "the character" in prompts and
`story.json`, matching how nameless characters already behave today.

## Architecture

```
photoreal character card, photo selected
        │
        ▼
POST /upload_photo  →  validates + normalizes (Pillow) →  outputs/_uploads/<uuid>.png
        │  photo_path stored on the character
        ▼
generate_reference_images (per character):
  has_photo = bool(photo_path) and os.path.exists(photo_path)
  context_images = [photo bytes] if has_photo else []
  prompt = assemble_reference_prompt(char, kind, art_style, has_photo=has_photo)
        │
        ▼
refs/<kind>_<n>.png        (Gemini output — same artifact shape as today)
refs/<kind>_<n>_upload.png (copy of the original photo, only when has_photo)
        │
        ▼
[UNCHANGED] reference_paths threaded into every scene's sliding-window context
```

### Component changes

- **`app.py`**: new `POST /upload_photo` endpoint; `UPLOAD_DIR = outputs/_uploads`;
  `ALLOWED_PHOTO_EXTENSIONS = {".png", ".jpg", ".jpeg"}`; `MAX_CONTENT_LENGTH` (~8MB) set
  on the Flask app; `CHARACTER_FIELDS` gains `photo_path`. Validates extension before
  decoding, decodes via Pillow (converts to RGB, `.thumbnail((1536, 1536))`), saves as
  PNG under a UUID filename (sidesteps path-traversal — filenames are never
  user-derived). Client errors → 400; oversized payloads → 413 (Flask's own
  enforcement); decode failures → 400; unexpected failures → 500.
- **`prompt_assembly.py`** (stays pure, no filesystem access): `assemble_reference_prompt`
  gains `has_photo: bool = False`. When `kind="photoreal"` and `has_photo=True`, the
  returned prompt opens with face-preservation language ("Using the exact face and
  identity of the person in the attached photo...") instead of asking Gemini to invent a
  face from the description. The `kind="cartoon"` branch ignores `has_photo` entirely —
  there is no cartoon upload UI to ever set it `True` in practice.
- **`image_generator.py`**: `generate_reference_images` reads `char.get("photo_path")`
  per photoreal character, guards with `os.path.exists` (a stale/missing path degrades
  gracefully to the no-photo path rather than crashing), passes the photo bytes as
  `context_images` via the existing `_load_context_bytes` helper, and copies the
  original photo into `refs/<kind>_<n>_upload.png` alongside the generated reference.
  Returned records gain a `from_photo: bool` field for traceability in `story.json`.
- **`templates/index.html`**: photoreal cards only (`addCharacterCard('photorealCharacterList')`)
  gain a file input + thumbnail preview + hidden `.field-photo-path`. Selecting a file
  immediately POSTs to `/upload_photo`; the "Generate Story" button is disabled while any
  upload is in flight. `collectCharacters()` reads `.field-photo-path` into the character
  object like any other field.

## Cost

No change to the existing per-book cost model. A photo-based reference still costs
exactly one image-generation call, same as a text-only reference — this was the reason
the combined single-call approach was chosen over a two-step generate-then-swap
alternative (which would have added a second image-gen call, ~$0.06–0.45 CAD/book, per
photo character).

**Measured (2026-06-17):** an actual 5-page mixed-media book with face-swap on Gemini 3
Pro Image cost **~CAD 3.5–3.8** (two runs: 3.53 and an instrumented 3.83) — over the
project's $3 POC ceiling and well above the early ~$0.90/book estimate. The instrumented
run logged **8 API calls, 0 errors, 7 Nano Banana Pro image requests** (2 references + 5
scenes) and 1 Flash text request; Pro image generation dominated both tokens and cost
(Pro: 5.85K in / 11.65K out; Flash: 0.63K in / 2.13K out). Full table in CHECKPOINT.md.
The combined-call approach kept this feature from making it *worse*, but the underlying
mixed-media cost (one Pro reference per character + 5 Pro scene images) is the real
driver. **This does not scale at the current per-book cost.** Cutting Pro image calls
(cheaper model for non-face steps, fewer/reused references, fewer scene images) is the
main open problem before scaling — quality on Pro is not the issue.

## Risks

- **Gemini may anchor too hard on the uploaded photo's pose/background** instead of the
  description fields, since one call is being asked to both preserve identity and
  reroll body/pose/clothing. This is the main thing to evaluate during manual E2E. The
  documented (not built) fallback if this proves unreliable is a two-step
  generate-then-swap call: generate the body reference from text as today, then a
  second Gemini call that swaps the uploaded face onto that result.
- **Gemini may refuse or return no image** for a real-person-likeness request (safety
  filtering). No special handling is added — the existing `ValueError("No image
  returned in response")` already surfaces through `/generate`'s try/except as a 500
  with the error message, which is sufficient for a POC.
- **No cleanup of `outputs/_uploads/`.** Matches the project's existing lack of
  lifecycle management for `outputs/story_<timestamp>/` directories; not a new category
  of problem, and out of scope for a developer-tested POC.

## Testing

All new tests use fake/recording providers — no real Gemini calls in the suite (manual
E2E is the only API-spending step, same convention as every prior feature on this
branch):

- `tests/test_upload_photo.py` (new): valid PNG/JPEG upload → 200 + working file on
  disk; missing file field, disallowed extension, corrupt bytes → 400; oversized
  payload → 413; oversized image dimensions get capped to 1536px.
- `tests/test_app_generate.py`: fix `test_normalize_drops_empty_and_trims` (now expects
  `photo_path: ""` in the normalized dict — this is the one existing assertion that
  breaks from adding the field); add coverage for `photo_path` round-tripping and for a
  photo-only (no name) character surviving normalization; extend the render-smoke test
  to assert the new upload markup is present.
- `tests/test_reference_prompt.py`: face-preservation language present when
  `has_photo=True`; byte-for-byte unchanged output when `has_photo=False` (regression
  pin); cartoon kind ignores `has_photo`.
- `tests/test_reference_generation.py`: photo bytes passed as `context_images` when
  `photo_path` is set; prompt differs from the no-photo case; upload copy saved
  alongside the generated reference; `from_photo` field correct in both branches; a
  missing/stale `photo_path` falls back to the no-photo path unchanged.

## Out of scope / deferred

- Two-step generate-then-swap (fallback only if the combined-call approach proves
  unreliable in manual E2E).
- Multiple photos per character (e.g. several angles to improve fidelity).
- Consent UI, upload retention/deletion policy, or any other privacy/child-safety
  product work beyond current POC assumptions.
- Cleanup/lifecycle management for `outputs/_uploads/`.
- A standalone fast-iteration test script outside the full pipeline (explicitly
  declined in favor of relying on the per-story `refs/` folder).
