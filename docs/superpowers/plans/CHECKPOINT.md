# Execution Checkpoint — Character Reference Images + Structured Multi-Character UI

**Plan:** `~/.claude/plans/fizzy-splashing-truffle.md` (approved 2026-06-15)
**Prior feature plan:** [2026-06-12-mixed-media-model-selection.md](2026-06-12-mixed-media-model-selection.md)
**Branch:** `feat/face-swap`
**Last updated:** 2026-06-15 (after Task 1)

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

## Next

- **Task 2: Reference prompt** — `assemble_reference_prompt(char, kind, art_style)` in `prompt_assembly.py` (photoreal = real-photo wording, no style words; cartoon = STYLE_PHRASES world_phrase/style_closer) + tests.

## Pending

- Task 3: rewrite `assemble_mixed_media_prompt` for character arrays + reference-instruction sentence (rewrite `tests/test_prompt_assembly.py`).
- Task 4: `generate_reference_images` (no-context, `refs/`, no caption) in `image_generator.py`.
- Task 5: thread `reference_paths` into `generate_all_images` / `_generate_with_context` (refs first, then 2-page window); classic unchanged.
- Task 6: `story_generator.py` → arrays + rewritten `MIXED_MEDIA_SYSTEM_PROMPT` (action-by-name, appearance fixed by refs).
- Task 7: `app.py` → parse arrays, validate ≥1 photoreal + soft cap, orchestrate story→refs→scenes, persist `character_refs`.
- Task 8: `templates/index.html` → dynamic character cards (dropdowns + large textarea, +/× buttons), `collectCharacters`, Pro default + hint.
- Task 9: new spec `docs/superpowers/specs/2026-06-15-character-reference-images-design.md`.
- Task 10: manual E2E (user; needs `GEMINI_API_KEY`; ~$1.4 CAD/book on Pro).
