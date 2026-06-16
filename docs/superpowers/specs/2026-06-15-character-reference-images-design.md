# Design Spec — Character Reference Images + Structured Multi-Character UI (Mixed-Media)

**Date:** 2026-06-15
**Branch:** `feat/face-swap`
**Status:** Implemented (Tasks 1–9); pending manual E2E (Task 10)
**Plan:** `~/.claude/plans/fizzy-splashing-truffle.md`
**Builds on:** [2026-06-12-mixed-media-model-selection-design.md](2026-06-12-mixed-media-model-selection-design.md)

## Motivation — what the first E2E round revealed

Manual testing of the base mixed-media feature (Gemini, sliding-window):

1. **Gemini Flash is poor at photorealistic generation** — unusable for the photoreal characters.
2. **Pro + "2D flat vector cartoon" = excellent** — characters held across all 5 images with unnoticeable drift.
3. **Pro + "Watercolor" = heavy drift** — characters in images 4 & 5 were completely different from images 1–3.
4. **Classic-mode regression works well.**

**Root cause of #3:** the sliding window *propagates* drift. Each page is conditioned on the previous (already slightly-off) pages, so small deviations compound — worst by scenes 4–5. The 2D-flat-vector style happened to stay stable; watercolor did not.

**Fix:** give every scene a stable, independent appearance anchor — a **reference image per character**, generated once up front and attached to every scene (including scene 1). To capture each character precisely (and to drive those reference images), the free-text character inputs become a **structured, multi-character UI**.

## Locked decisions

- **Per-scene context = character references FIRST, then the existing 2-page sliding window.** References anchor appearance; the window preserves page-to-page continuity. (Belt-and-suspenders; chosen over references-only.)
- **Generate references for both photoreal and cartoon characters.** Cartoon references are skipped when there are no cartoon characters.
- **Mixed-media auto-selects the Pro image model** (`gemini-3-pro-image-preview`) and shows a hint that Flash is weak at photoreal; Flash remains selectable. Frontend default only.
- **Classic mode is unchanged** end-to-end (`reference_paths=None` ⇒ original window-only behavior).

## Data model

Character object (same shape for photoreal and cartoon lists):

```json
{ "name": "Dad", "skin_tone": "medium", "hair_color": "dark brown",
  "body_type": "average", "height": "tall",
  "description": "short beard, green sweater, blue jeans" }
```

`photoreal_characters` / `cartoon_characters` flow as **arrays of these objects**: frontend JSON → `app.py` (`_normalize_characters`) → `generate_story` → `assemble_mixed_media_prompt`. Dropdown fields may be empty ("unspecified"); the composer skips empties. Stored in `story.json`; the reference mapping is persisted as `character_refs`.

### Reference-ordering invariant (single source of truth)

Photoreal characters first (list order), then cartoon characters. The **same** order is used by:
- `generate_reference_images` — save/return order (`refs/photoreal_1.png`, `refs/cartoon_1.png`, …),
- `app.py` — builds `reference_paths` from the returned records and passes it through,
- `generate_all_images` — prepends those reference bytes before the window,
- `assemble_mixed_media_prompt` — the "reference N is &lt;name&gt;" enumeration.

## Architecture

```
story generated (LLM writes per-scene ACTION by name; appearance NOT described)
        │
        ▼
generate_reference_images  →  refs/<kind>_<n>.png   (one no-context call per character)
        │  reference_paths (ordered: photoreal then cartoon)
        ▼
for each scene:  context = [reference bytes…] + [≤2 previous pages]  →  scene_<n>.png
```

### Component changes

- **`prompt_assembly.py`** (pure): `compose_character_description`, `character_label`, `join_labels`; `assemble_reference_prompt(char, kind, art_style)` (photoreal = real-photo, **no** style words; cartoon = STYLE_PHRASES look); `assemble_mixed_media_prompt` now takes character **lists**, builds the contrast sentence from `join_labels`, and emits `_reference_instruction` ("use the attached references; reference N is &lt;name&gt;; only pose/expression/action change; extra images are previous pages").
- **`image_generator.py`**: `generate_reference_images(...)` (no-context, `refs/`, **no caption**); `generate_all_images` / `_generate_with_context` gain `reference_paths` and build `context_images = refs + window` (references first).
- **`story_generator.py`**: `generate_story(..., photoreal_characters: list, cartoon_characters: list)`; `MIXED_MEDIA_SYSTEM_PROMPT` rewritten — the LLM writes action **by name** and must NOT re-describe fixed appearance (the old "repeat the same physical details every scene" rule was removed because it fought the reference images). `_validate_story` / `MIXED_SCENE_KEYS` unchanged.
- **`app.py`**: `_normalize_characters`, list parsing, validation (≥1 photoreal, `MAX_CHARACTERS=6`), orchestration (story → refs → scenes with `reference_paths`), `character_refs` persisted.
- **`templates/index.html`**: dynamic character cards (name + 4 dropdowns + large textarea + remove), `+Add` buttons, `collectCharacters`; Mixed-Media toggle seeds a card, preselects 2D-flat-vector + Pro, shows the hint.

## Cost

Each mixed-media book adds N reference images (one per character) before the 5 scenes. On Pro: ~3 characters ⇒ ~8 images ⇒ ~$1.4 CAD/book. The `MAX_CHARACTERS=6` cap bounds request size and cost.

## Testing

49 new/changed unit tests (composition, reference prompt, mixed-media prompt rewrite, reference generation via fake provider, scene-context ordering, story prompt, Flask `test_client` validation/threading, render smoke). Full suite green. Reference/scene **image generation** itself is validated by manual E2E (Task 10); it is the only API-spending step.

## Open / deferred

- Whether to restrict non-vector styles or label them "experimental" — decide after E2E confirms references tame watercolor drift.
- Displaying reference images in the UI (currently saved + in `story.json` only).
