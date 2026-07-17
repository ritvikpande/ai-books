# Fable Suggestions — Codebase Analysis & Prioritized Refactors

**Author:** Claude Fable 5 · **Date:** 2026-07-17 · **Branch:** `feat/face-swap`
**Status:** Analysis only — *no code has been changed.* Each finding is written so a later agent (or a cheaper model) can execute it behavior-preservingly.

> Companion docs: [BookCostOptimization.md](BookCostOptimization.md) (the CAD 3.5–3.8/book problem) and [NextJSWebDesign.md](NextJSWebDesign.md) (frontend migration). Several findings here are *permanently* fixed by the Next.js redesign; those cross-references are called out inline.

---

## Section A — Architecture Map

The app is a synchronous Flask monolith that turns a form submission into a 5-image storybook via Gemini, saving artifacts to the local disk and serving them back to the browser.

```
Browser (templates/index.html — Bootstrap + vanilla JS)
   │  POST /generate  (JSON: keywords, setting, characters, mixed_media, arrays, model)
   ▼
app.py  ──────────────────────────────────────────────────────────────────────
   • routes: /  /generate  /upload_photo  /images  /download_pdf
   • _normalize_characters()  → clean character dicts (CHARACTER_FIELDS)
   • _save_uploaded_photo()   → Pillow-normalize upload → outputs/_uploads/<uuid>.png
   • /generate orchestration (validation → story → refs → scenes → persist → JSON)
   │
   ├─► story_generator.py
   │      generate_story()  → Gemini 3 Flash (TEXT_MODEL) → 5-scene JSON
   │      • classic: LLM writes full image_prompt per scene
   │      • mixed:  LLM writes action-only fields, then
   │               assemble_mixed_media_prompt() builds the final prompt
   │
   ├─► prompt_assembly.py   (PURE — no I/O, no network)
   │      STYLE_PHRASES, compose_character_description(), character_label(),
   │      assemble_reference_prompt(has_photo=…), assemble_mixed_media_prompt()
   │      ▶ reference-ordering invariant: photoreal chars first, then cartoon
   │
   ├─► image_generator.py
   │      generate_reference_images()  → 1 ref image per character (refs/<kind>_<n>.png)
   │      generate_all_images()        → 5 scenes, sliding window = refs + ≤2 prev pages
   │      add_caption() (PIL text burn), generate_pdf() (PIL → PDF)
   │
   └─► providers.py
          GeminiProvider.generate_image(prompt, context_images, model) -> PNG bytes
          │
          └─► config.py  get_client() (reads GEMINI_API_KEY), TEXT_MODEL, OUTPUT_DIR

Artifacts: outputs/story_<timestamp>/{story.json, refs/*.png, scene_1..5.png, *.pdf}
Served back to the browser via GET /images?path=<absolute path>
```

**Two flows share one pipeline.** *Classic mode* asks the LLM to write a full `image_prompt` per scene and generates 5 images with a sliding window only. *Mixed-media mode* adds a **reference image per character** (a stable appearance anchor, including the optional uploaded-face "face swap"), attaches all references to every scene, and has the LLM write action-only fields that a deterministic assembler wraps in validated boilerplate.

**The load-bearing invariant** is reference ordering — *photoreal characters first, then cartoon* — repeated across `generate_reference_images`, the `reference_paths` build in `app.py`, `generate_all_images`, and `assemble_mixed_media_prompt`'s "reference N is <name>" enumeration. Any refactor that touches character ordering must preserve it in all four places.

**Where complexity concentrates.** `app.py`'s `/generate` view (≈80 lines) is the only place validation, orchestration, persistence, and timing are interleaved; `prompt_assembly.py` is clean and well-tested; `providers.py` is thin but is the single choke point for every paid API call (which makes it the right home for instrumentation, retries, and client reuse).

---

## Section B — Findings

Each finding: **What · Where · Why it matters · Refactor strategy · Why better · Tradeoffs · Verification · Suggested tests · Agent-execution note.** IDs are stable so the other docs and future PRs can reference them.

### SEC-1 — Arbitrary file read/write via `/images` and `/download_pdf` 🔴

- **What:** The browser sends server filesystem paths and the server reads/writes them with no containment.
- **Where:** `app.py:193-201` (`get_image` → `send_from_directory` on `request.args['path']`); `app.py:204-218` (`download_pdf` opens client-supplied `image_paths` and **writes** the PDF into client-supplied `story_dir` via `generate_pdf`).
- **Why it matters:** `GET /images?path=C:\Windows\win.ini` (or `/etc/passwd`, or **`/proc/self/environ` → leaks `GEMINI_API_KEY` → attacker-funded Gemini spend**) returns arbitrary files. Story dirs are timestamp-named (`story_YYYYMMDD_HHMMSS`), so uploaded **children's face photos** at `refs/photoreal_1_upload.png` are *enumerable*, not merely readable. `/download_pdf` is additionally a **write** primitive (attacker chooses where a PDF lands). This is the most serious issue in the codebase.
- **Refactor strategy (behavior-preserving for legitimate use):** Stop accepting paths from the client. Serve by identifier: `GET /images/<story_id>/<filename>` where `story_id` matches `^story_[0-9_]+$` and `filename` matches `^[A-Za-z0-9_.-]+$` (no separators). Resolve against `OUTPUT_DIR`, then assert the real path stays inside `OUTPUT_DIR` (`os.path.realpath(...).startswith(os.path.realpath(OUTPUT_DIR))`) before `send_from_directory`. For `/download_pdf`, send only `story_id` + `story_title`; the server rebuilds the file list from its own `story.json` and writes only inside that story dir. Update `templates/index.html` and the `currentStoryData` plumbing to pass ids instead of paths.
- **Why better:** Removes both the read and write primitives entirely; the server only ever touches paths it constructed. Legitimate rendering/downloads are unchanged from the user's perspective.
- **Tradeoffs:** Touches the frontend contract (`image_paths` → ids) and the PDF payload shape; a small amount of coordinated change across `app.py` + template + the two JS fetch calls.
- **Verification:** `pytest -q` stays green; manually confirm a generated book still renders and the PDF still downloads; add negative tests below and confirm they 400/404.
- **Suggested tests:** `test_images_rejects_absolute_path`, `test_images_rejects_dotdot_traversal`, `test_images_rejects_unknown_story_id`, `test_images_serves_valid_story_asset`, `test_download_pdf_ignores_client_paths`.
- **Agent-execution note:** **Judgment + review required** — cross-file (backend + frontend) and security-sensitive. Not for an unsupervised cheap model; should be its own PR with the negative tests written first (TDD).

### SEC-2 — Unauthenticated money-spending endpoint 🔴

- **What:** `/generate` is public and every call costs real CAD (~CAD 3.5–3.8/book).
- **Where:** `app.py:105` (`@app.route('/generate', …)`, no auth); deploy is Cloud Run `--allow-unauthenticated` (README deploy command).
- **Why it matters:** Anyone with the URL can spend your Gemini budget without limit; with 2 sync gunicorn workers × 120s timeout, two concurrent long requests also saturate an instance (DoS), and Cloud Run scaling out to cope *increases* spend. Largest expected-dollar risk in the project.
- **Refactor strategy:** Short term (before the Next.js work): put the service behind auth or a shared secret header, add a per-IP rate limit, set a **GCP budget alert** and an **API-key quota cap** so worst-case spend is bounded. Long term: this is closed properly by the Next.js design — user auth at the BFF, Python service made **private** (`--no-allow-unauthenticated`), per-user quotas (see [NextJSWebDesign.md](NextJSWebDesign.md) "Auth + spend control" and [BookCostOptimization.md](BookCostOptimization.md) lever #5).
- **Why better:** Converts unbounded, anonymous spend into metered, attributable spend.
- **Tradeoffs:** Adds an auth step to what is currently a zero-friction demo; interim shared-secret is ugly but fast.
- **Verification:** Confirm unauthenticated `/generate` is rejected; confirm the budget alert fires in a test project.
- **Suggested tests:** `test_generate_requires_auth` (once an auth mechanism exists).
- **Agent-execution note:** Interim mitigations are **mostly ops/config** (cheap-model-safe with the operator applying GCP console steps). The real fix is part of the migration and needs judgment.

### PERF/OPS-3 — gunicorn 120s timeout < generation time; ephemeral per-instance filesystem 🔴

- **What:** A book takes 1–2+ minutes but the worker timeout is 120s, and generated files live on a per-instance in-memory disk.
- **Where:** `Dockerfile:20` (`gunicorn … --workers 2 --timeout 120`); `config.py:15` (`OUTPUT_DIR = "outputs"`, a local relative dir); Cloud Run runtime.
- **Why it matters:** A slow run gets killed *after* most images are already paid for → the user retries the whole book → **silent 2× spend**. On Cloud Run, `outputs/` consumes instance memory, and any second instance can't serve `/images` for a book the first instance generated (404s / flaky downloads).
- **Refactor strategy:** Interim — raise the gunicorn timeout above worst-case generation and pin `min/max instances = 1` (or `--workers 1`) so one instance serves what it generated. Real fix — the asynchronous **job model + object storage** in [NextJSWebDesign.md](NextJSWebDesign.md): the request returns a `book_id` immediately and a worker generates in the background, so no HTTP request blocks for minutes and assets live in GCS, not instance RAM.
- **Why better:** Eliminates timeout-kill double-spend and the multi-instance 404 class of bug.
- **Tradeoffs:** Interim single-instance limits concurrency; the durable fix is a larger architectural change (tracked in the migration doc).
- **Verification:** Generate a book that exceeds 120s and confirm it completes; confirm assets survive across instances (post-migration).
- **Agent-execution note:** Interim = **one-line Dockerfile + Cloud Run flag** (cheap-model-safe). Durable = migration-scale (judgment).

### COST/OBS-4 — No `usage_metadata` (token/cost) logging 🔴

- **What:** The pipeline never records Gemini token usage; cost is reconstructed by hand in `Test_Results.md`.
- **Where:** `providers.py:29-40` (`generate_content` response is consumed only for image bytes; `response.usage_metadata` is ignored). Text calls in `story_generator.py` similarly.
- **Why it matters:** Every cost decision in [BookCostOptimization.md](BookCostOptimization.md) needs per-call numbers, and this is what explains the **2.8× anomaly** (measured CAD 3.83 vs ~CAD 1.35 list for 7 Pro images — likely billed interim "thought images", since Gemini 3 Pro Image has always-on thinking). Cheapest, highest-leverage change here.
- **Refactor strategy:** Add a thin logging wrapper at the single choke point (`GeminiProvider.generate_image`, and the text call): read `response.usage_metadata` (prompt/candidates/total token counts, and image-modality counts if present), log per call with the model id and a book/scene tag, and accumulate a per-book total returned alongside the result. This is the natural place to also fix **DUP-8** (text via provider) and **PERF-9** (client reuse).
- **Why better:** Turns cost from a manual spreadsheet into an automatic, per-run artifact; makes the hybrid-routing experiment measurable.
- **Tradeoffs:** Slightly more logging noise; a small response-shape assumption (guard for `usage_metadata is None`).
- **Verification:** `pytest -q` green (fake providers unaffected — they don't return usage); run one real book and confirm a token/cost line per call.
- **Suggested tests:** `test_generate_image_logs_usage_when_present` (fake provider returning a stub `usage_metadata`); ensure existing fake-provider tests still pass (they return raw bytes, so the wrapper must tolerate missing usage).
- **Agent-execution note:** **Mechanical, cheap-model-safe** if scoped to "log usage, don't change control flow." Pairs well with PERF-9.

### CORR-5 — No retry/backoff; unguarded `candidates[0]` 🔴

- **What:** A single API call per image with no retry, and an index into `candidates[0]` that can throw the wrong error.
- **Where:** `providers.py:37` (`response.candidates[0]` — `IndexError` if the response was safety-blocked/empty, instead of the intended `ValueError("No image returned in response")` at `providers.py:40`).
- **Why it matters:** One transient flake or safety refusal at scene 5 aborts the whole run *after* ~CAD 2.7 of images are paid for; the user re-runs → failure cost ≈ 2× a book. The mis-typed error also surfaces confusingly.
- **Refactor strategy:** Guard `candidates` (empty/None → raise the intended `ValueError` with any `prompt_feedback`/finish-reason detail). Wrap the call in bounded exponential backoff (e.g. 3 tries) for transient errors only (not safety refusals). Validate that returned bytes are a decodable image before accepting.
- **Why better:** Caps marginal failure cost at one image; makes failures legible.
- **Tradeoffs:** Retries add latency on a bad path and could double-bill a single image if the API charged before failing (rare); keep the retry count small.
- **Verification:** `pytest -q` green; add unit tests with a fake provider that raises then succeeds, and one returning empty candidates.
- **Suggested tests:** `test_generate_image_retries_transient_error`, `test_generate_image_empty_candidates_raises_valueerror`, `test_generate_image_does_not_retry_safety_block`.
- **Agent-execution note:** **Judgment-light but review recommended** (error taxonomy matters). TDD-friendly.

### ARCH-6 — Extract a service layer from `app.py` `/generate` 🟡

- **What:** The `/generate` view mixes request parsing, validation, orchestration (story → refs → scenes), persistence, and timing in ~80 lines.
- **Where:** `app.py:105-190`.
- **Why it matters:** This is the enabler for almost everything downstream — the async **job model**, the **FastAPI** surface the Next.js app calls, and the **parallelization** wins (PERF-7). It's hard to add a worker/queue around logic welded to the Flask request/response.
- **Refactor strategy:** Extract `story_service.generate_book(inputs) -> BookResult` (a plain module/dataclass, no Flask imports) that does story → refs → scenes → persist and returns paths/metadata. The view becomes: parse+validate → `generate_book(...)` → `jsonify`. Keep validation in the view (or a `validate_inputs` helper) so HTTP concerns stay at the edge.
- **Why better:** The pipeline becomes callable from a worker, a CLI, a test, or a FastAPI route without a request context; shrinks the view to HTTP glue.
- **Tradeoffs:** Moderate churn; must preserve the exact JSON contract the current frontend expects until the frontend changes.
- **Verification:** The existing `tests/test_app_generate.py` route tests pin the contract and must stay green unchanged; add a direct unit test of `generate_book` with fake providers.
- **Suggested tests:** `test_generate_book_service_returns_expected_shape` (fake providers, `tmp_path` `OUTPUT_DIR`); keep all current route tests untouched as the regression pin.
- **Agent-execution note:** **Judgment required**, its own PR. Do **before** PERF-7 and before the migration.

### PERF-7 — Serialized independent work (refs; story vs refs) 🟡

- **What:** Independent generations run sequentially.
- **Where:** `image_generator.py:178-206` (`generate_reference_images` loops characters one at a time); `app.py:145-164` (story is generated, *then* refs).
- **Why it matters:** The 2–3 reference images are mutually independent, and `generate_reference_images` needs only the form characters + `art_style` (not the story JSON), so it can overlap story generation. Cost-neutral but cuts wall-clock and shrinks the timeout-kill window (PERF/OPS-3). Scene images must stay sequential — the sliding window makes each depend on prior pages.
- **Refactor strategy:** After ARCH-6, run the reference generations concurrently (thread pool — these are I/O-bound API calls, so the GIL isn't a barrier) and start ref-gen concurrently with story-gen, joining before scene generation. Preserve the reference-ordering invariant when collecting results (sort by (kind, index), don't rely on completion order).
- **Why better:** Noticeably faster books with zero quality/cost change.
- **Tradeoffs:** Concurrency adds complexity and must respect Gemini rate limits (cap pool size); ordering must be reconstructed deterministically.
- **Verification:** `pytest -q` green; confirm `refs/` filenames and `character_refs` order are identical to today; measure wall-clock improvement.
- **Suggested tests:** `test_reference_order_preserved_under_concurrency` (fake provider with artificial delays), reuse existing ref-generation tests as pins.
- **Agent-execution note:** **Judgment required** (concurrency + invariant). After ARCH-6.

### DUP-8 — Duplicated `client` pytest fixture; text bypasses provider abstraction 🟡

- **What:** Two identical fixtures; and the text model is called outside the provider layer.
- **Where:** `tests/test_app_generate.py:6-9` and `tests/test_upload_photo.py:10-13` (byte-identical `client` fixture; no `tests/conftest.py`); `story_generator.py` imports `get_client` from `config` directly rather than going through a provider.
- **Why it matters:** Small DRY/consistency issues; the fixture duplication is a textbook `conftest.py` case, and the text-path bypass means COST/OBS-4 instrumentation has to be added in two different styles.
- **Refactor strategy:** Hoist the shared fixture into `tests/conftest.py` and delete both local copies (pytest auto-discovers it). Optionally introduce a `TextProvider`/`generate_text` seam so text and image calls share one instrumented client path (do this together with COST/OBS-4).
- **Why better:** One fixture, one client path; less drift.
- **Tradeoffs:** The text-provider seam is optional scope — don't over-engineer if only instrumentation is needed.
- **Verification:** `pytest -q` green with the same test count (90).
- **Suggested tests:** none new — the existing suite is the check.
- **Agent-execution note:** The `conftest.py` hoist is **fully mechanical, cheap-model-safe**. The text-provider seam is judgment (bundle with COST/OBS-4).

### PERF-9 — New `genai.Client` constructed on every image call 🟡

- **What:** A fresh client is built per image (~7×/book).
- **Where:** `providers.py:22` (`client = get_client()` inside `generate_image`); `config.py:18-25`.
- **Why it matters:** Wasteful object/connection setup on a hot path; trivially avoidable.
- **Refactor strategy:** Construct the client once (module-level lazy singleton in `providers.py`, or injected into `GeminiProvider.__init__`) and reuse. Keep `get_client`'s key-validation. Fold into the COST/OBS-4 wrapper.
- **Why better:** Fewer allocations/handshakes; a single place to attach usage logging and retries.
- **Tradeoffs:** Must stay thread-safe if PERF-7 introduces a pool (the google-genai client is safe to share; verify against the pinned SDK version).
- **Verification:** `pytest -q` green (fake providers bypass the client); one real book still generates.
- **Agent-execution note:** **Mechanical, cheap-model-safe.**

### DEADCODE/COMPLEX-10 — Internal-only helpers 🟢

- **What:** Helpers used only within `image_generator.py`.
- **Where:** `image_generator.py:137` (`generate_single_image`, called only at the `__main__` demo `:300`), `image_generator.py:36` (`add_caption`, **used** by the scene path at `:127` — keep it).
- **Why it matters:** Minor surface area. `generate_single_image` is effectively a demo/testing entry point; document or drop it, but **verify** callers first (nothing external imports it).
- **Refactor strategy:** Confirm no importers (grep), then either keep it explicitly labeled "standalone demo" or remove it with the `__main__` block. No behavior change to the real pipeline.
- **Tradeoffs:** Removing a convenient manual-test hook; low value either way.
- **Verification:** `pytest -q` green; grep shows no external callers.
- **Agent-execution note:** **Mechanical** — but must grep-verify before deleting.

### OPS-11 — Docker / deploy hygiene 🟢

- **What:** Several container/packaging issues.
- **Where:** `requirements.txt` (fully unpinned, incl. the fast-moving `google-genai` preview SDK); `Dockerfile:17` (`HEALTHCHECK` uses `curl`, absent from `python:3.10-slim`, and Cloud Run ignores Dockerfile healthchecks anyway); `Dockerfile` (runs as **root**, no `USER`); `.dockerignore` (missing `outputs/`, so local PNGs — including a real uploaded face photo — bake into the image).
- **Why it matters:** Unpinned deps make builds non-reproducible and risk an SDK break; the healthcheck misleads local compose; root is needless privilege; baking `outputs/` bloats the image and ships PII.
- **Refactor strategy:** Pin dependencies (`pip freeze` the working set, or `==` the majors). Remove the broken healthcheck or install `curl`/use a Python check. Add a non-root `USER`. Add `outputs/` to `.dockerignore`.
- **Tradeoffs:** Pinning requires periodic bumps; otherwise pure upside.
- **Verification:** `docker build` succeeds; image no longer contains `outputs/`; container runs non-root.
- **Agent-execution note:** **Fully mechanical, cheap-model-safe.** Fold into the migration's containerization step (NextJSWebDesign.md) if not done sooner.

### DOC-12 — Documentation drift & minor hardening 🟢

- **What:** Stale/inconsistent docs and a couple of small correctness/UX gaps.
- **Where:** `TECHNICAL_OVERVIEW.md` (prose/structure say **Streamlit** while the stack table says Flask — internally contradictory); `README.md:70` points at `.claude/CLAUDE.md`, which doesn't exist in the repo; `app.py:188-190` returns raw `str(e)` to the client (path/detail leak); no idempotency guard on the double-submit of a CAD-3.83 action; `app.py:224` `debug=True` (fine for local, must be off in the container — gunicorn already bypasses it, but worth an explicit note).
- **Why it matters:** Onboarding confusion; small info leak; double-charge risk on a fat-fingered double click.
- **Refactor strategy:** Rewrite `TECHNICAL_OVERVIEW.md` to Flask reality (or delete the Streamlit sections); fix the README link; return a generic error message to clients and log the detail server-side; add a client-side submit-lock + optional server idempotency key.
- **Tradeoffs:** None material.
- **Verification:** Docs read correctly; a forced exception returns a generic message; double-click produces one book.
- **Agent-execution note:** **Mechanical, cheap-model-safe** (docs + a small error-handling edit).

---

## Section C — Priority Matrix

Impact = user/£ risk if left alone. Effort: S ≤ ~1h, M ≈ half-day, L ≈ multi-day. "Agent" = safe for a cheap/mechanical model (✅) vs needs judgment + review (🧠).

| ID | Finding | Impact | Effort | Depends on | Agent |
|----|---------|--------|--------|------------|-------|
| SEC-1 | Arbitrary file read/write via `/images` & `/download_pdf` | **High** | M | — | 🧠 |
| SEC-2 | Unauthenticated money-spending `/generate` | **High** | S (interim) / L (full) | — / migration | 🧠 (ops parts ✅) |
| PERF/OPS-3 | 120s timeout < gen time; ephemeral FS | **High** | S (interim) / L (full) | — / migration | ✅ interim / 🧠 full |
| COST/OBS-4 | No `usage_metadata` logging | **High** | S | — | ✅ |
| CORR-5 | No retry/backoff; unguarded `candidates[0]` | **High** | S–M | — | 🧠 (light) |
| ARCH-6 | Service-layer extraction from `/generate` | Med | M | — | 🧠 |
| PERF-7 | Parallelize refs; overlap story+refs | Med | M | ARCH-6 | 🧠 |
| DUP-8 | Duplicated `client` fixture; text bypass | Med | S | (text seam: COST/OBS-4) | ✅ (fixture) |
| PERF-9 | New `genai.Client` per call | Med | S | — | ✅ |
| DEADCODE-10 | Internal-only `generate_single_image` | Low | S | — | ✅ (grep first) |
| OPS-11 | Docker/deps hygiene | Low | S | — | ✅ |
| DOC-12 | Doc drift; error leak; idempotency | Low | S | — | ✅ |

**Recommended order.** Do the cheap, high-value, dependency-free wins first (COST/OBS-4, PERF-9, DUP-8, OPS-11, DOC-12 — all ✅), which also instrument cost before you spend on experiments. Then the security/correctness High items (SEC-1, SEC-2 interim, CORR-5, PERF/OPS-3 interim). Then the architectural spine (ARCH-6 → PERF-7). The durable versions of SEC-1/SEC-2/PERF-3 land with the Next.js migration.

---

## Section D — Execution Guidance for Agents / Lower Models

**Global rule (every finding):** the regression gate is `venv\Scripts\python.exe -m pytest -q` staying green (currently **90 passed**). No finding here is allowed to change that count *down*; findings that add tests raise it. If a change is behavior-preserving, the existing suite must pass *unchanged*.

- **Safe for an unsupervised cheap model (mechanical):** COST/OBS-4 (log usage only, no control-flow change), PERF-9 (client singleton), DUP-8 (hoist fixture to `conftest.py`), OPS-11 (Docker/deps), DOC-12 (docs + generic error), DEADCODE-10 (grep-verify then remove). Each is one file or a tightly-scoped set; each ends with the green-bar check.
- **Judgment + human review, own PR each:**
  - **SEC-1** — write the negative tests first (traversal/absolute/unknown-id all rejected), then change `/images` + `/download_pdf` + the frontend path plumbing together. Security-sensitive; do not batch with anything else.
  - **ARCH-6** — extract `story_service.generate_book`; the current `test_app_generate.py` route tests are the behavior pin and must pass unchanged.
  - **PERF-7** — only after ARCH-6; add the ordering-under-concurrency test before parallelizing; cap the thread pool for rate limits.
  - **CORR-5** — encode the error taxonomy (transient → retry; safety-block → raise) in tests first.
- **Ops/config (operator applies in GCP console, not code):** SEC-2 budget alert + key quota + Cloud Run auth flag; PERF/OPS-3 interim timeout/instance settings.

**Suggested new test files/areas:** `tests/conftest.py` (DUP-8), `tests/test_images_security.py` (SEC-1), `tests/test_provider_usage.py` (COST/OBS-4), `tests/test_provider_retry.py` (CORR-5), `tests/test_story_service.py` (ARCH-6). Keep using the established patterns: local fake/recording providers, `tmp_path` + `monkeypatch.setattr(app_module, "OUTPUT_DIR", ...)`, no real API calls in the suite.
