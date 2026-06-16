# Execution Checkpoint — Character Reference Images + Structured Multi-Character UI

**Plan:** `~/.claude/plans/fizzy-splashing-truffle.md` (approved 2026-06-15)
**Prior feature plan:** [2026-06-12-mixed-media-model-selection.md](2026-06-12-mixed-media-model-selection.md)
**Branch:** `feat/face-swap`
**Last updated:** 2026-06-15 (after Task 8)

## Testing findings (E2E round 1 — manual, by user)

1. **Gemini Flash is poor at photorealistic generation** — unusable for photoreal characters.
2. **Pro + "2D flat vector" = excellent** — characters held across all 5 images, unnoticeable drift.
3. **Pro + "Watercolor" = heavy drift** — characters in images 4 & 5 completely different from 1–3. Root cause: the sliding window propagates drift (each page conditioned on already-drifted previous pages → error compounds).
4. **Classic-mode regression works well.**

These motivate the current feature: per-character **reference images** attached to every scene as a stable appearance anchor, plus a structured multi-character UI. Locked decisions: refs + 2-page window (belt & suspenders); generate refs for photoreal **and** cartoon; mixed-media defaults to Pro (Flash still selectable).

## Prior feature (mixed-media + provider/model selection) — DONE & validated

Tasks 1–7 built, reviewed, committed (`f0e080b`..`2faf7fb`); manual E2E performed by user (findings above). Base mixed-media mode works on Pro.

## Done (this feature)

- **Task 1: Composition helpers** — `prompt_assembly.py`: `compose_character_description`, `character_label`, `join_labels` + 15 tests (`tests/test_character_composition.py`). Commit `287fcfb`. Full suite: 45 passed.
- **Task 2: Reference prompt** — `assemble_reference_prompt(char, kind, art_style)` in `prompt_assembly.py` (photoreal = real-photo, no style words; cartoon = STYLE_PHRASES) + 11 tests (`tests/test_reference_prompt.py`). Full suite: 56 passed.
- **Task 3: Mixed-media prompt → arrays** — `assemble_mixed_media_prompt` now takes character **lists**; contrast built from `join_labels`; new `_reference_instruction` sentence enumerates "reference N is <name>" (photoreal then cartoon). `tests/test_prompt_assembly.py` rewritten (17 tests). Full suite: 59 passed. ⚠️ `story_generator` mixed-path call site passes strings → intentionally stale until Task 6; classic path unaffected; mixed path is not unit-tested so suite stays green.

- **Task 4: Reference generation** — `generate_reference_images(photoreal, cartoon, art_style, output_dir, provider, model)` in `image_generator.py`: one no-context call per character, saved `refs/<kind>_<n>.png`, no caption, returns ordered records (photoreal then cartoon; cartoon skipped if empty). Fake-provider tests (6) in `tests/test_reference_generation.py`. Full suite: 65 passed.
- **Task 5: Thread references into scenes** — `generate_all_images` / `_generate_with_context` gain `reference_paths` (default None); context = refs FIRST + 2-page window. Classic (None) = window-only, unchanged. Recording-provider tests (2) in `tests/test_scene_context.py` assert refs-first + per-scene counts. Full suite: 67 passed.
- **Task 6: Story generation → arrays** — `generate_story(..., photoreal_characters: list, cartoon_characters: list)`; mixed user prompt lists characters via `_describe_characters` (uses `compose_character_description`); `MIXED_MEDIA_SYSTEM_PROMPT` rewritten to action-by-name (appearance fixed by refs — old "repeat physical details" rule deleted); assembler now receives arrays. `_validate_story` unchanged. Tests (4) in `tests/test_story_prompt.py`. Full suite: 71 passed.
- **Task 7: Flask wiring** — `app.py`: `_normalize_characters` (drop empties, trim), parse photoreal/cartoon as **lists**, validate (≥1 photoreal → 400, soft cap `MAX_CHARACTERS=6` → 400), orchestrate story → `generate_reference_images` → `generate_all_images(reference_paths=...)`, persist `character_refs` in story.json. Classic path unchanged (no refs, `reference_paths=None`). `test_client` tests (7) in `tests/test_app_generate.py`. Full suite: 78 passed. **Backend now runnable end-to-end for both modes.**
- **Task 8: Frontend** — `templates/index.html`: dynamic character cards (`#photorealCharacterList`/`#cartoonCharacterList`, `+ Add` buttons, per-card name + 4 dropdowns + large `rows=4` textarea + `×` remove); `selectHTML`/`addCharacterCard`/`collectCharacters` (per-card `.field-*` querySelectors, no global IDs). Mixed-Media toggle seeds one photoreal card, auto-selects 2D-flat-vector + Pro model, shows `#proHint`; restores Flash when off. Submit sends arrays (`[]` in classic) + JS guard for ≥1 photoreal. Render smoke test added (now 8 in `test_app_generate.py`). Full suite: 79 passed. Note: all cards removable; ≥1 photoreal enforced at submit + backend (not by locking the first card).

## Next

- **Task 9:** new spec `docs/superpowers/specs/2026-06-15-character-reference-images-design.md`.

## Pending
- Task 10: manual E2E (user; needs `GEMINI_API_KEY`; ~$1.4 CAD/book on Pro).
