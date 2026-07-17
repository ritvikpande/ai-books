# Next.js Web Design — Migration Architecture

**Author:** Claude Fable 5 · **Date:** 2026-07-17 · **Branch:** `feat/face-swap`
**Status:** Design only — *no code changed.*
**Decision locked by owner:** **keep the Python pipeline** as a private API service behind the Next.js frontend (not a TypeScript rewrite).

> Companions: [FableSuggestions.md](FableSuggestions.md) (SEC-1, SEC-2, PERF/OPS-3, ARCH-6 are *permanently* fixed here) and [BookCostOptimization.md](BookCostOptimization.md) (the character library lives in this architecture).

---

## 1. Decision & rationale

**Architecture: Next.js frontend (Vercel) + the existing Python pipeline as a private FastAPI service on Cloud Run.**

The project's real asset is the **Python pipeline**, not the web layer: prompt assembly and the reference-ordering invariant, the PIL caption burn, the just-fixed mixed-media/no-border aesthetics, the Pillow PDF output, and **90 passing pytest tests**. A full TypeScript rewrite (`@google/genai` in Next.js) would re-implement all of that, re-litigate solved visual bugs in `sharp`/`pdf-lib`, and orphan the test suite — for zero user-visible benefit. The `@google/genai` SDK has parity, but the SDK was never the hard part.

| | **Option A — Keep Python (chosen)** | Option B — TS rewrite |
|---|---|---|
| Pipeline logic | Reused as-is | Re-implemented |
| 90 pytest tests | ~All stay valid (some relocate under ARCH-6) | Orphaned → rewrite in Vitest + re-golden images/PDF |
| Visual bugs (border, drift) | Stay fixed | Re-risk |
| Job runner | Cloud Run worker | Still need Inngest/Trigger.dev/QStash + GCS/R2 |
| Net moving parts | Fewer | Same-or-more, minus the tests |

**Option B would only win** if the long-term team is TypeScript-only *and* the Python pipeline is considered disposable — not the case here.

**Target topology:**

```
Browser ── Next.js (Vercel)  ── BFF: /api/* (auth, quota, signing)
                │  OIDC service-to-service token
                ▼
        FastAPI + worker (Cloud Run, PRIVATE --no-allow-unauthenticated)
            • wraps the existing story_service.generate_book pipeline
            • writes per-step job status
                │
                ├─ Firestore/Cloud SQL  (jobs, users, character library)
                └─ GCS  books/{book_id}/…, uploads/{user}/…, characters/{user}/…
```

If single-cloud ops matter more than Vercel's frontend DX, run Next.js standalone on Cloud Run instead — the rest of the architecture is unchanged.

---

## 2. Async job pattern (fixes the 2-min blocking request — PERF/OPS-3)

A book takes 1–2+ min; **no HTTP request should block that long.**

- `POST /api/books` → validate + create a job record → **return `book_id` immediately (202).**
- A worker runs the pipeline (`story → refs → scenes → PDF`), writing a **per-step status document** (`queued → story → refs(2/2) → scene(3/5) → pdf → done|error`).
- Frontend **polls** `GET /api/books/{book_id}` every 2–3s and renders progress; on `done`, it fetches signed asset URLs.

**Polling over SSE:** the pipeline emits only ~8 coarse events over 60–120s; SSE's proxy/buffering/reconnect complexity across Vercel ↔ Cloud Run buys nothing here. The status document can back an SSE or WebSocket stream later with no data-model change if smoother progress is ever wanted.

This also removes the gunicorn-120s-timeout double-spend (PERF/OPS-3): the request no longer waits, and a per-scene retry (CORR-5) means a late flake costs one image, not a whole book.

---

## 3. File & asset serving redesign (permanently fixes SEC-1)

Today `/images?path=<absolute path>` is an arbitrary-file-read hole and `/download_pdf` writes to a client-chosen dir ([FableSuggestions.md](FableSuggestions.md) SEC-1). The migration removes the class of bug:

- **Move `outputs/` to GCS:** `books/{book_id}/{story.json, refs/*.png, scene_*.png, book.pdf}`. (Also a correctness fix: Cloud Run's per-instance in-memory FS can't reliably serve local files across instances.)
- **Client never sends paths — only `book_id`.** The server resolves assets from its own job record.
- **Serve via V4 signed URLs** minted *after* an ownership check (`job.user_id == session.user`), or proxy through the Next.js BFF. TTL-limited, per-object.
- **PDF:** the worker builds it from its own record into `books/{book_id}/book.pdf`; the client just receives a signed URL. No client paths, no write primitive.

---

## 4. Photo upload flow

- Next.js requests a **signed upload URL** (or proxies the bytes, keeping the current 8MB cap) → object stored at `uploads/{user}/{uuid}.png`.
- Keep the existing **Pillow normalization** server-side (decode → RGB → 1536px cap → re-encode PNG): it strips metadata and doubles as a **decompression-bomb / content guard**. Do not skip it just because storage is now remote.
- A **GCS lifecycle rule auto-deletes raw uploaded face photos** after N days. Generation requests reference an `upload_id`, never a path.

---

## 5. Character library (home for cost Lever #2)

The reference-reuse cost lever ([BookCostOptimization.md](BookCostOptimization.md) #2) lives here:

- **Owned by the Python service** — references are pipeline artifacts consumed as context bytes.
- **DB row** per character: `user_id`, the structured fields (name, skin_tone, …), `ref_object_path`, `from_photo`, `created_at`. **Ref PNG** at `characters/{user}/{char_id}/ref.png`.
- Next.js only **lists/attaches by id**; a book request passes `character_ids` and the service attaches stored reference bytes instead of regenerating (saving ~29% of image cost on repeat characters).
- **Sensitive-PII requirements (children's faces), not optional:** per-user isolation, explicit consent copy at upload, and a working **delete** endpoint that removes both the DB row and the objects.

---

## 6. Auth & spend control (permanently fixes SEC-2)

- **User auth at the Next.js layer** (Auth.js / Clerk / Firebase Auth).
- **Python service goes private** (`--no-allow-unauthenticated`); Next.js server code calls it with an **OIDC service-to-service token**. The pay-per-call public endpoint is closed.
- **Per-user quotas** (N books/day) and **spend metering** — fed by the `usage_metadata` logging from [FableSuggestions.md](FableSuggestions.md) COST/OBS-4 / [BookCostOptimization.md](BookCostOptimization.md) Lever #4 — enforced at the BFF, plus GCP budget alerts as a backstop.

---

## 7. What happens to the 90 pytest tests

- **Under Option A: ~all stay valid.** The pure-function tests (`prompt_assembly`, `story` validation, reference generation via fake providers) are untouched. The Flask route tests (`test_app_generate.py`, `test_upload_photo.py`) get thinner as `/generate` becomes a FastAPI endpoint over `story_service.generate_book` (ARCH-6), but the *service-level* tests carry the behavior. New tests cover the job lifecycle, signed-URL access control, and the SEC-1 negative cases.
- **Under Option B they'd be orphaned** — the single biggest reason Option A wins.

---

## 8. How the current code maps forward

| Today | Next.js-era |
|---|---|
| `app.py` `/generate` view (orchestration) | `story_service.generate_book()` (ARCH-6) called by a FastAPI route + worker |
| `story_generator.py`, `image_generator.py`, `prompt_assembly.py` | **Unchanged** — the pipeline core |
| `providers.py` / `config.py` | Unchanged + the instrumentation/retry/client-reuse from FableSuggestions (COST/OBS-4, CORR-5, PERF-9) |
| `/images?path=…` | `GET /api/books/{id}/assets/{name}` → signed URL (SEC-1) |
| `/download_pdf` (client paths) | worker-built PDF in GCS → signed URL |
| `/upload_photo` → local `outputs/_uploads` | signed upload → `uploads/{user}/…` + lifecycle delete |
| `templates/index.html` (Bootstrap + vanilla JS) | Next.js React UI; retired after cutover |
| local `outputs/` | GCS `books/{book_id}/…` |
| Docker (root, unpinned, broken healthcheck) | fix during containerization (FableSuggestions OPS-11) |

---

## 9. Recommended sequencing

1. **In the current Python app first (benefits today's Flask UI too):** ARCH-6 service extraction, then the job model (status doc + background worker), plus the FableSuggestions quick wins (COST/OBS-4, CORR-5, PERF-9, OPS-11).
2. **FastAPI surface** with pydantic request/response contracts → generate an **OpenAPI schema → typed TS client** for Next.js (keeps the two languages in contract-sync).
3. **Build the Next.js frontend** against that API (this is where the "much better front end" effort goes — component library, polling progress UI, character-library management, upload UX).
4. **Cut over** GCS + auth + private service; **retire** `templates/index.html`.
5. Fold the **cost levers** in as they land: hybrid routing behind the API, character library in the DB/storage introduced here.

**Guiding principle:** the pipeline is the product; the migration wraps it in a job API, replaces path-based file access with id-based signed access, and puts auth + quotas in front of the money-spending path — which is exactly the set of things the security/perf/cost analysis said to fix anyway.
