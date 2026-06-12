# Execution Checkpoint — Mixed-Media Stories + Provider/Model Selection

**Plan:** [2026-06-12-mixed-media-model-selection.md](2026-06-12-mixed-media-model-selection.md)
**Spec:** [../specs/2026-06-12-mixed-media-model-selection-design.md](../specs/2026-06-12-mixed-media-model-selection-design.md)
**Branch:** `feat/face-swap`
**Last updated:** 2026-06-12 (execution starting)

## Done

- Design spec written, approved, committed (`d28e61a`)
- Implementation plan written, self-reviewed, committed (`f0e080b`)

## Next

- **Task 1: Test infrastructure** — add pytest to requirements.txt, install into venv, verify

## Pending

- Task 2: Provider abstraction (`providers.py` + tests)
- Task 3: Mixed-media prompt assembly (`prompt_assembly.py` + tests)
- Task 4: Thread provider/model through `config.py` + `image_generator.py`
- Task 5: Mixed-media story generation (`story_generator.py` + tests)
- Task 6: Flask wiring (`app.py`)
- Task 7: Frontend (`templates/index.html`)
- Task 8: Manual E2E validation — **requires user confirmation first (costs ~$1–2 CAD)**
- Final code review of the whole branch
