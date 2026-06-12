# Execution Checkpoint — Mixed-Media Stories + Provider/Model Selection

**Plan:** [2026-06-12-mixed-media-model-selection.md](2026-06-12-mixed-media-model-selection.md)
**Spec:** [../specs/2026-06-12-mixed-media-model-selection-design.md](../specs/2026-06-12-mixed-media-model-selection-design.md)
**Branch:** `feat/face-swap`
**Last updated:** 2026-06-12 (after Task 7 — all build tasks done)

## Done

- Design spec written, approved, committed (`d28e61a`)
- Implementation plan written, self-reviewed, committed (`f0e080b`)
- **Task 1: Test infrastructure** — pytest 9.0.3 added + installed (`b53ee03`), verified
- **Task 2: Provider abstraction** — `providers.py` + 6 tests (`8c0e8f1`); spec review ✅, quality review ✅ (no fixes needed)
- **Task 3: Prompt assembly** — `prompt_assembly.py` + 14 tests (`609d918`, polish `f3ea289`); spec review ✅, quality review ✅ (minor docstring + None test applied). Suite: 20 passed

- **Task 4: Provider threading** — `config.py` + `image_generator.py` (`bf145ee`, polish `7c9ac4f`); spec review ✅, quality review ✅. ⚠️ app.py call site intentionally stale until Task 6 — branch not runnable until then.

- **Task 5: Mixed-media story generation** — `story_generator.py` + 10 tests (`b54a718`, polish `40665c3` adds null-field hardening); spec review ✅, quality review ✅. Suite: 30 passed

- **Task 6: Flask wiring** — `app.py` (`547e08e`); spec review ✅, quality review ✅ (no fixes). Stale call site fixed — app runnable again. 30 tests green.

- **Task 7: Frontend** — `templates/index.html` (`a9a5f8f`); spec review ✅, quality review ✅ (no fixes). Note for E2E: art-style auto-select on Mixed Media check is one-directional (unchecking doesn't restore previous style — by design)

- **Final whole-branch review** ✅ — "Ready for manual E2E + merge: Yes (after Task 8)". No critical/important issues. 30 tests green. Minor notes: mixed-media user prompt omits art_style (by design — watch pixel/pencil coherence in E2E); mixed validation stricter than spec (intentional); one-directional art-style auto-select (by design).

## Next

- **Task 8: Manual E2E validation** — user deferred ("not now", 2026-06-12). When resuming: start `venv\Scripts\python app.py`, generate (1) classic regression book, (2) mixed-media on Flash, (3) mixed-media on Pro; verify story.json image_prompts start with "A mixed media children's book illustration collage."; spot-check 400s. Costs ~$1–2 CAD, needs GEMINI_API_KEY in .env.

## Pending

- (after Task 8) finishing-a-development-branch: merge/PR decision; branch not yet pushed to origin
