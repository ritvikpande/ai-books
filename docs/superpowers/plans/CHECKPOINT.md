# Execution Checkpoint — Fable Suggestions Refactor Implementation

**Plan:** `C:\Users\ritvi\.claude\plans\now-our-next-goal-robust-neumann.md` (analysis-docs plan, approved) — the *implementation* being tracked here is a follow-on the user requested after reading the docs, not itself written up as a separate plan file.
**Analysis docs:** [FableSuggestions.md](../../FableSuggestions.md) (12 prioritized findings), [BookCostOptimization.md](../../BookCostOptimization.md), [NextJSWebDesign.md](../../NextJSWebDesign.md) — all at repo root.
**Branch:** `refactor/fable-suggestions` (created from `feat/face-swap` — NOT yet merged/pushed)
**Last updated:** 2026-07-29 (after SEC-1; stopping here on user request to resume later)

## Prior branch (`feat/face-swap`) — complete, not yet merged

Face-swap feature (photo upload, face preservation, white-border fix, reference display in UI) fully implemented, tested, and manually E2E-validated by the user — quality excellent. Cost measured at ~CAD 3.5–3.8/book (over the $3 POC ceiling), which motivated the Fable analysis docs. `feat/face-swap` itself was never pushed/PR'd — still pending after this refactor branch is dealt with. Full history: `git log feat/face-swap`.

## Done (this branch) — 4 of 11 items, all TDD, all committed

Every item below followed red→green TDD (failing test written and confirmed failing for the right reason, then minimal implementation, then full-suite green). Suite has grown 98 → **121 passed**, zero regressions across any step.

1. **DUP-8** — hoisted the duplicated `client` pytest fixture (`test_app_generate.py` + `test_upload_photo.py`) into `tests/conftest.py`; deleted both local copies. Commit `86b07f4`. Suite: 98 passed (unchanged count — pure dedup).
2. **COST/OBS-4 + PERF-9** — `GeminiProvider` now builds its `genai.Client` lazily once and reuses it (was rebuilt every call); logs `response.usage_metadata` (prompt/candidates/total tokens + model) per call when present. This is the instrumentation the cost investigation needs — no real book has been run against it yet to explain the CAD 3.83-vs-~CAD-1.35-list-price anomaly noted in `BookCostOptimization.md`. Commit `4e902b7`. Suite: 102 passed (+4).
3. **CORR-5** — fixed `response.candidates[0]` throwing `IndexError` instead of the intended `ValueError` on an empty/safety-blocked response; added bounded retry (3 attempts, exponential backoff) verified against the real `google.genai.errors` hierarchy — retries `ServerError`(5xx)/`ClientError(429)` only, never other 4xx or the safety-block case; added `_validate_image_bytes` (PIL decode+verify) so corrupt API responses are rejected at the boundary instead of silently written to disk. Commit `d5a8b05`. Suite: 108 passed (+6).
4. **SEC-1** (the most serious finding) — `/images` no longer takes a client-supplied filesystem path (was `?path=<anything>`, exploitable for `/proc/self/environ` → API key leak, plus enumerable uploaded face photos); now `/images/<story_id>/<filename>`, both validated and realpath-contained inside `OUTPUT_DIR`. `/download_pdf` no longer takes client `image_paths`/`story_dir` (was also a **write** primitive — client chose where the PDF landed); now takes only `story_id` and rebuilds everything from that story's own `story.json` on disk. `/generate`'s JSON response no longer contains any filesystem path anywhere (top-level or nested in `character_refs`) — only `story_id` + relative filenames. Frontend (`templates/index.html`) updated to match: `imageUrl(storyId, filename)` helper, `renderReferences` takes a `storyId` param, PDF download sends only `{story_id}`. New test file `tests/test_images_security.py` (13 tests: positive serving incl. nested `refs/` paths, unknown/malformed story ids, `..` traversal both as a literal segment and reaching a sibling story dir, direct unit tests of the resolver for leading-slash/backslash filenames that Werkzeug's own router normalizes away before reaching the view, `/download_pdf` proven to ignore attacker-supplied `image_paths`/`story_dir`/`story_title` even when present in the same request body). Commit `ccf88e7`. Suite: 121 passed (+13).

## Next — resume here (ARCH-6)

**ARCH-6** — extract `story_service.generate_book(...)` out of `app.py`'s `/generate` view (currently ~80 lines mixing validation, orchestration, persistence, timing). The service module must have **no Flask imports** so it's callable from a worker/CLI/test without a request context — this is the enabler for PERF-7 (next item) and eventually the Next.js migration's job model. The existing `test_app_generate.py` route tests (`test_mixed_media_threads_arrays_and_reference_paths`, `test_classic_mode_does_not_generate_references`, the validation tests) are the behavior pin and must keep passing **unchanged** — they test through the HTTP layer, so if they still pass after the extraction, the contract held. Add a new direct unit test of the service function itself with fake providers (not going through Flask). Note SEC-1's response-shaping logic (`story_id`, `image_filenames`, `character_refs[].filename`/`.upload_filename` — currently inline in `/generate`) should move into the service too, or stay a thin view-layer concern — decide when writing this; either is defensible, just be deliberate and consistent with "no Flask imports in the service."

## Pending / open (not started) — items 6–11 of the original 11

Work through in order (dependencies matter — PERF-7 needs ARCH-6 done first; the cost-lever enabler wants COST/OBS-4's logging already in place, which it is):

6. **PERF-7** (after ARCH-6) — parallelize the independent reference-image generations (thread pool, cap size for rate limits) and overlap story-gen with ref-gen. Must preserve reference-ordering invariant (photoreal-first-then-cartoon) under concurrency — write `test_reference_order_preserved_under_concurrency` first.
7. **SEC-2 interim** — per-IP rate limit on `/generate` (the full fix is auth in the Next.js migration, out of scope here).
8. **Cost Lever #1 enabler** — optional `scene_image_model` routing (so Flash can be tried for cartoon ref + scenes while Pro stays for the photoreal/face-swap reference) + a UI control to pick it. This is the hybrid-routing *experiment infrastructure* from `BookCostOptimization.md`, not a verified savings claim — the real quality verdict still needs a manual run.
9. **OPS-11 + PERF/OPS-3 interim** — pin `requirements.txt`; fix/remove the broken `curl` healthcheck in `Dockerfile`; add non-root `USER`; add `outputs/` to `.dockerignore`; raise gunicorn timeout above worst-case generation time.
10. **DOC-12** — generic error message returned to clients on 500 (log detail server-side, don't leak `str(e)` — note `/download_pdf` already does this as of SEC-1; `/generate`'s except block at the bottom of the view still leaks `str(e)` and needs the same treatment); gate `debug=True` behind an env var; fix `TECHNICAL_OVERVIEW.md` (still says Streamlit) and the dead `.claude/CLAUDE.md` link in `README.md:70`.
11. **Final** — full suite green, update this CHECKPOINT.md marking each finding done/skipped, note in `FableSuggestions.md`/`BookCostOptimization.md` which findings were actually implemented vs. deferred, then decide on `finishing-a-development-branch` (push, PR) for `refactor/fable-suggestions` — and separately, `feat/face-swap` is still unpushed underneath it.

## Pending / open (deferred by design, not part of this branch's 11 items)

- SEC-1/SEC-2/PERF-3's **durable** fixes (object storage + job model + real auth) are Next.js-migration scope (`NextJSWebDesign.md`), not this branch.
- Cost Lever #2 (character-library reuse) and #3 (draft-on-Flash → approve → Pro) — migration-era, need persistence/DB, out of scope here.
- `feat/face-swap` still needs to be pushed + PR'd to main.
- Re-run E2E to visually confirm the white-border fix (from `feat/face-swap`) — still outstanding, independent of this refactor.
- A real book run against the new `usage_metadata` logging (item 2 above) to actually explain the CAD 3.83-vs-list-price cost anomaly — nothing in this branch does that on its own, it just makes the data visible next time a book is generated.
