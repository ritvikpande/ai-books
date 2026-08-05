# Execution Checkpoint — Fable Suggestions Refactor Implementation

**Plan:** `C:\Users\ritvi\.claude\plans\now-our-next-goal-robust-neumann.md` (analysis-docs plan, approved) — the *implementation* tracked here is a follow-on the user requested after reading the docs.
**Analysis docs:** [FableSuggestions.md](../../FableSuggestions.md) (12 findings, priority matrix with completion status), [BookCostOptimization.md](../../BookCostOptimization.md), [NextJSWebDesign.md](../../NextJSWebDesign.md) — all at repo root.
**Branch:** `refactor/fable-suggestions` (created from `feat/face-swap`)
**Last updated:** 2026-08-04 (all 11 planned items done)

## Status: DONE — 11 of 11 planned items implemented, ready for finishing-a-development-branch

Every item followed red→green TDD (failing test confirmed failing for the right reason, then minimal implementation, then full-suite green). Suite grew **98 → 156 passed**, zero regressions across every step. Full commit list (`git log feat/face-swap..HEAD`, oldest first):

1. `a6006a1` docs: add Fable analysis docs
2. `b993bab` docs: checkpoint before implementation (mid-session pause)
3. `86b07f4` **DUP-8** — hoisted duplicated `client` pytest fixture into `tests/conftest.py`
4. `4e902b7` **COST/OBS-4 + PERF-9** — `GeminiProvider` reuses one lazily-built client (thread-safe double-checked locking); logs `usage_metadata` per call
5. `d5a8b05` **CORR-5** — fixed `IndexError`-not-`ValueError` on empty candidates; bounded retry (verified against real `google.genai.errors` hierarchy: retries 5xx/429, never other 4xx or safety-blocks); validates returned bytes decode as an image
6. `ccf88e7` **SEC-1** (most serious finding) — `/images` and `/download_pdf` no longer accept client-supplied filesystem paths; both now resolve a `story_id` jailed to `OUTPUT_DIR`; `/generate`'s response never contains an absolute path
7. `0f08da9` docs: checkpoint after SEC-1 (mid-session pause)
8. `30166ec` **ARCH-6** — extracted `story_service.py` (no Flask import) from `app.py`'s `/generate`; dependency-injected the three generation-step functions so existing gray-box monkeypatch tests kept working unmodified
9. `43e6616` **PERF-7** — reference-image generation now runs concurrently (bounded thread pool, ordering preserved regardless of completion order); story generation and reference generation now overlap in mixed-media mode (verified via real timing-overlap tests, stable across repeated runs)
10. `e3a729c` **SEC-2 interim** — per-IP rate limit on `/generate` (hand-rolled `RateLimiter`, skipped under `TESTING` config so the rest of the suite doesn't flake)
11. `c0d1334` **Cost Lever #1 enabler** — `model_routing.py` + optional `scene_image_model` field/UI so the cartoon reference + scenes can route to a cheaper model while the photoreal reference stays on the main model. **Infrastructure only — no quality verdict; still needs a human-judged manual run.**
12. `97f92d8` **OPS-11 + PERF/OPS-3 interim** — pinned `requirements.txt` to exact tested versions; fixed the broken `curl` healthcheck (stdlib-only now); added a non-root Docker user; added `outputs/`/`.pytest_cache/`/`tests/` to `.dockerignore`; raised gunicorn timeout 120s→300s
13. `2a2ced6` **DOC-12** — `/generate`'s 500 handler no longer leaks `str(e)`; `debug=True` gated behind `FLASK_DEBUG` env var; `TECHNICAL_OVERVIEW.md` rewritten (was describing the old Streamlit app); `README.md`'s dead `.claude/CLAUDE.md` link repointed at `BookCostOptimization.md`

## Incident during this work (disclosed, logged to memory)

While TDD-writing the "unknown `scene_image_model` returns 400" test (item 11), an early draft posted to `/generate` without mocking the generation pipeline, assuming the not-yet-implemented validation would reject the request first. Since it didn't exist yet, the request fell through to a **real Gemini API call** and generated a full 5-image book on `gemini-3-pro-image-preview` (~134s, real cost — roughly CAD 3.5–3.8 per this project's own cost data). Fixed by making every `/generate`-posting test mock the pipeline unconditionally, never relying on validation order. Logged to persistent memory (`feedback-mock-pipeline-unconditionally-in-generate-tests`) so future sessions in this repo don't repeat it.

## Not done (deliberately, tracked in FableSuggestions.md's priority matrix)

- **DEADCODE-10** — `generate_single_image` internal-only cleanup. Re-verified 2026-08-04: still only referenced by `image_generator.py`'s `__main__` demo block. Trivial, just wasn't picked up this round.
- **DUP-8's text-provider seam** — `story_generator.py` still calls `config.get_client()` directly rather than through a provider abstraction (only the pytest fixture duplication was fixed). Optional sub-scope.
- **DOC-12's idempotency guard** — no protection against double-submitting `/generate` (a fat-fingered double click on a CAD-3.5+ action). Was in the original finding's prose but not carried into the executed checkpoint plan.
- **Cost Lever #1's actual experiment** — the routing infrastructure exists; nobody has run a real book with `scene_image_model` set and judged whether Flash-for-scenes holds up visually when anchored by a Pro photoreal reference. This is the single highest-leverage next step for the cost problem (see `BookCostOptimization.md`).

## Next

- **Push `refactor/fable-suggestions`, open a PR to `feat/face-swap`** (or wherever it should land) — use `superpowers:finishing-a-development-branch` when ready.
- Separately, **`feat/face-swap` itself is still unpushed** underneath this branch — was already pending before this branch existed, still pending after.
- Re-run E2E to visually confirm the `feat/face-swap` white-border fix — still outstanding, independent of this refactor.
- Whenever ready: run the Cost Lever #1 experiment (set `scene_image_model` to Flash on a real mixed-media/face-swap book, judge quality page-by-page against an all-Pro book) — this is what turns the routing infrastructure into an actual cost decision.
