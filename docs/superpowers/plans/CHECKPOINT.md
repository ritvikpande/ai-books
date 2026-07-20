# Execution Checkpoint — Fable Suggestions Refactor Implementation

**Plan:** `C:\Users\ritvi\.claude\plans\now-our-next-goal-robust-neumann.md` (analysis-docs plan, approved) — the *implementation* being tracked here is a follow-on the user requested after reading the docs, not itself written up as a separate plan file yet.
**Analysis docs:** [FableSuggestions.md](../../FableSuggestions.md) (12 prioritized findings), [BookCostOptimization.md](../../BookCostOptimization.md), [NextJSWebDesign.md](../../NextJSWebDesign.md) — all at repo root.
**Branch:** `refactor/fable-suggestions` (created from `feat/face-swap` — NOT yet merged/pushed)
**Last updated:** 2026-07-18 (session cut short on usage limit before implementation started)

## Prior branch (`feat/face-swap`) — complete, not yet merged

Face-swap feature (photo upload, face preservation, white-border fix, reference display in UI) fully implemented, tested (98 passed), and manually E2E-validated by the user — quality excellent. Cost measured at ~CAD 3.5–3.8/book (over the $3 POC ceiling), which motivated the Fable analysis docs. `feat/face-swap` itself was never pushed/PR'd — that's still pending after this refactor branch is dealt with. Full history in git log and the (now superseded) prior checkpoint content — see `git log feat/face-swap`.

## Done (this branch)

- Three analysis docs written and committed: `FableSuggestions.md`, `BookCostOptimization.md`, `NextJSWebDesign.md`. Commit `a6006a1`.
- Branch `refactor/fable-suggestions` created off `feat/face-swap`.
- TDD skill loaded; implementation plan (TodoWrite, 11 items below) drafted but **not started** — session hit the usage limit right after setup, before any code/test was written.

## Next — start here

Work through the TodoWrite list below **in order** (dependencies matter — ARCH-6 must land before PERF-7; COST/OBS-4 before the cost-lever experiment). Each item = one TDD cycle (failing test → minimal code → green) per `FableSuggestions.md`'s per-finding "Verification" / "Suggested tests" notes. Gate: `venv\Scripts\python.exe -m pytest -q` must stay green throughout (currently 98 passed) and grow as tests are added.

1. **DUP-8** — hoist the duplicated `client` fixture (`test_app_generate.py:6-9`, `test_upload_photo.py:10-13`) into `tests/conftest.py`; delete both local copies. Mechanical.
2. **COST/OBS-4 + PERF-9** — in `providers.py`: log `response.usage_metadata` per call (model id + tag); build the `genai.Client` once (module-level singleton) instead of per-call in `generate_image`. Tests: fake provider with stub `usage_metadata`; confirm existing fake-provider tests (which return raw bytes, no usage) still pass.
3. **CORR-5** — guard empty/None `response.candidates` in `providers.py:37` (raise the intended `ValueError`, not `IndexError`); add bounded retry/backoff for transient errors only (not safety blocks). Tests: fake provider that raises-then-succeeds; empty-candidates case; no-retry-on-safety-block case.
4. **SEC-1** (own PR-sized change, its own commit) — replace client-supplied absolute paths in `/images` and `/download_pdf` with `story_id`-based lookup jailed to `OUTPUT_DIR`; update `templates/index.html` + JS fetch calls to pass ids not paths. Write negative tests FIRST (traversal, absolute path, unknown id all rejected) before touching the routes.
5. **ARCH-6** — extract `story_service.generate_book(...)` out of `app.py`'s `/generate` view (no Flask imports in the service module). Existing `test_app_generate.py` route tests are the behavior pin — must pass unchanged. Add a direct unit test of the service with fake providers.
6. **PERF-7** (after ARCH-6) — parallelize the independent reference-image generations (thread pool, cap size for rate limits) and overlap story-gen with ref-gen. Must preserve reference-ordering invariant (photoreal-first-then-cartoon) under concurrency — write `test_reference_order_preserved_under_concurrency` first.
7. **SEC-2 interim** — per-IP rate limit on `/generate` (the full fix is auth in the Next.js migration, out of scope here).
8. **Cost Lever #1 enabler** — optional `scene_image_model` routing (so Flash can be tried for cartoon ref + scenes while Pro stays for the photoreal/face-swap reference) + a UI control to pick it. This is the hybrid-routing *experiment infrastructure* from `BookCostOptimization.md`, not a verified savings claim — the real quality verdict still needs a manual run.
9. **OPS-11 + PERF/OPS-3 interim** — pin `requirements.txt`; fix/remove the broken `curl` healthcheck in `Dockerfile`; add non-root `USER`; add `outputs/` to `.dockerignore`; raise gunicorn timeout above worst-case generation time.
10. **DOC-12** — generic error message returned to clients on 500 (log detail server-side, don't leak `str(e)`); gate `debug=True` behind an env var; fix `TECHNICAL_OVERVIEW.md` (still says Streamlit) and the dead `.claude/CLAUDE.md` link in `README.md:70`.
11. **Final** — full suite green, update this CHECKPOINT.md marking each finding done/skipped, note in `FableSuggestions.md`/`BookCostOptimization.md` which findings were actually implemented vs. deferred.

## Pending / open (not blocking, deferred by design)

- SEC-1/SEC-2/PERF-3's **durable** fixes (object storage + job model + real auth) are Next.js-migration scope (`NextJSWebDesign.md`), not this branch.
- Cost Lever #2 (character-library reuse) and #3 (draft-on-Flash → approve → Pro) — migration-era, need persistence/DB, out of scope here.
- `feat/face-swap` still needs to be pushed + PR'd to main (was already pending before this branch existed).
- Re-run E2E to visually confirm the white-border fix (from `feat/face-swap`) — still outstanding, independent of this refactor.
