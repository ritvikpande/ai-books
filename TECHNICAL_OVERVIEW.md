# AI Storybook Generator — Technical Overview

## Project Summary

A Python-based proof of concept that generates illustrated children's storybooks for toddlers (ages 2–5). The user provides keywords, characters, setting, story type, and art style via a **Flask web app** (`templates/index.html`, Bootstrap + vanilla JS). The system generates a 5-scene story with consistent illustrations using the Google Gemini API, and offers a downloadable PDF of the final storybook. A **mixed-media mode** supports photorealistic characters (including optional face-swap from an uploaded photo) alongside a cartoon world, anchored by a per-character reference image attached to every scene.

**Repository:** https://github.com/ritvikpande/ai-books
**Live demo:** https://storybook-app-802321863547.northamerica-northeast1.run.app
**Stage:** Deployed to GCP Cloud Run (Flask + Docker + Cloud Run, region `northamerica-northeast1`)

---

## Technical Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.x |
| AI Text Generation | Gemini (`gemini-3-flash-preview`) |
| AI Image Generation | Gemini (`gemini-2.5-flash-image` default; `gemini-3-pro-image-preview` for mixed-media/face-swap) |
| API SDK | `google-genai` |
| Image Processing | Pillow (PIL) |
| Web Framework | Flask + Gunicorn |
| Frontend | HTML + Bootstrap + vanilla JS (`templates/index.html`) |
| Containerization | Docker (non-root user, pinned dependencies) |
| Hosting | Google Cloud Run (northamerica-northeast1) |
| Environment Management | `python-dotenv`, venv |
| Testing | pytest (155+ tests, no real API calls in the suite) |
| Version Control | Git + GitHub |

---

## Project Structure

```
ai-books/
├── .env                       # GEMINI_API_KEY (gitignored)
├── .env.example                # Template for required env vars
├── .gitignore / .dockerignore  # Excludes venv/, .env, outputs/, tests/, __pycache__
├── Dockerfile                  # non-root user, pinned deps, gunicorn
├── requirements.txt            # Pinned dependencies
├── README.md                    # Setup & usage docs
├── TECHNICAL_OVERVIEW.md        # This file
├── FableSuggestions.md          # Codebase analysis: findings + priorities
├── BookCostOptimization.md      # Cost-reduction levers (the open problem)
├── NextJSWebDesign.md           # Planned frontend migration architecture
├── Test_Results.md              # Manual E2E test logs
├── config.py                   # API client + model constants
├── providers.py                # ImageProvider abstraction (GeminiProvider): retry/backoff,
│                                  client reuse, usage-token logging
├── model_routing.py            # Resolves which model each pipeline step uses (cost experiment)
├── rate_limit.py                # Minimal per-IP rate limiter (interim, /generate only)
├── prompt_assembly.py           # Pure functions: builds reference + mixed-media prompts
├── story_generator.py           # Gemini text API → structured story JSON
├── image_generator.py           # Gemini image API: reference images, sliding-window scenes,
│                                   caption overlay, PDF stitching
├── story_service.py             # Orchestrates story → references → scenes → persistence;
│                                   no Flask import, callable standalone
├── app.py                       # Flask routes (thin HTTP layer over story_service)
├── templates/index.html         # Frontend: form, character cards, photo upload, results
├── docs/superpowers/            # Design specs, implementation plans, CHECKPOINT.md
├── tests/                       # pytest suite (fakes/monkeypatches — no real API calls)
├── venv/                        # Local Python environment (gitignored)
└── outputs/                     # Generated storybooks (gitignored)
    └── story_<timestamp>/
        ├── story.json
        ├── refs/                # Mixed-media only: one reference image per character
        ├── scene_1.png ... scene_5.png
        └── <title>.pdf
```

**Design principle:** `app.py` only parses HTTP requests and translates results to JSON — all generation logic lives in `story_service.py`, which has no Flask dependency and is directly unit-testable (and reusable from a future worker/CLI/FastAPI service, see `NextJSWebDesign.md`).

---

## Module Breakdown

### 1. [config.py](config.py) — Configuration
- Loads `GEMINI_API_KEY` from `.env` via `python-dotenv`
- Defines `TEXT_MODEL`, `DEFAULT_PROVIDER`, `DEFAULT_IMAGE_MODEL`, `OUTPUT_DIR`
- `get_client()` builds and returns a `genai.Client`; raises a clear error if the key is missing or still the placeholder

### 2. [providers.py](providers.py) — Image Provider Abstraction
- `ImageProvider` (abstract) / `GeminiProvider` — `generate_image(prompt, context_images, model) → bytes`
- Builds its `genai.Client` lazily once per provider instance and reuses it (thread-safe via double-checked locking)
- Bounded retry with backoff on transient failures (Gemini 5xx / 429), never on deterministic 4xx or a safety-blocked empty response
- Validates returned bytes actually decode as an image before accepting them
- Logs `usage_metadata` (prompt/candidates/total tokens) per call — the basis for the cost analysis in `BookCostOptimization.md`

### 3. [model_routing.py](model_routing.py) — Cost Experiment Routing
- `model_for_step(step, image_model, scene_image_model)` resolves which model a pipeline step uses. The photoreal (face-bearing) reference always stays on `image_model`; the cartoon reference and all scenes can optionally route to a cheaper `scene_image_model`. Infrastructure only — the actual quality verdict needs a human-judged manual run (see `BookCostOptimization.md` Lever #1)

### 4. [rate_limit.py](rate_limit.py) — Interim Rate Limiting
- `RateLimiter(limit, window_seconds).allow(key)` — minimal in-memory fixed-window limiter, applied per client IP to `/generate` (unauthenticated + costs real money per call). In-process only; the durable fix is real auth in the planned Next.js migration

### 5. [prompt_assembly.py](prompt_assembly.py) — Pure Prompt Builders
- `compose_character_description`, `character_label`, `join_labels` — structured character fields → prose
- `assemble_reference_prompt(char, kind, art_style, has_photo)` — the one-time per-character reference image prompt; `has_photo=True` switches to face-preservation language for the uploaded-photo (face-swap) case
- `assemble_mixed_media_prompt(scene, photoreal_characters, cartoon_characters, art_style)` — wraps the LLM's per-scene action fields in a validated boilerplate template
- No filesystem/network access — pure string assembly, directly unit-tested

### 6. [story_generator.py](story_generator.py) — Story + Prompt Generation
- `generate_story(keywords, characters, setting, story_type, art_style, mixed_media, photoreal_characters, cartoon_characters) → dict`
- Classic mode: the LLM writes a complete `image_prompt` per scene. Mixed-media mode: the LLM writes action-only fields (`photoreal_action`, `cartoon_elements`, `background`); `prompt_assembly` builds the final prompt deterministically
- Strips stray markdown code-fences, validates the response (5 scenes, required keys per mode)

### 7. [image_generator.py](image_generator.py) — Image Generation + PDF
- `generate_reference_images(...)` — one reference image per character (mixed-media only), generated **concurrently** (bounded thread pool) since each character is independent; preserves photoreal-first-then-cartoon ordering regardless of completion order. Face-swap: an uploaded photo's bytes are passed as context and the original is copied alongside the generated reference for visual comparison
- `generate_all_images(story, output_dir, provider, model, reference_paths)` — sequential sliding window (up to 2 previous pages) plus, in mixed-media mode, every character reference attached to every scene as a stable appearance anchor
- `add_caption(image_path, caption_text)` — burns scene text onto the top-right of each image
- `generate_pdf(image_paths, story_title, output_dir) → bytes` — one scene per page

### 8. [story_service.py](story_service.py) — Orchestration (no Flask import)
- `validate_inputs(...)` — raises `GenerationError` (maps to HTTP 400) for invalid combinations
- `generate_book(...) → dict` — runs story generation and reference generation **concurrently** (neither depends on the other), waits for both, then generates scenes; persists `story.json`; returns `story_id` + filenames relative to it — never an absolute filesystem path (assets are served back through `/images/<story_id>/<filename>`, resolved and jailed to `OUTPUT_DIR`)
- The three generation steps are dependency-injected parameters (default to the real implementations) so callers/tests can substitute fakes without monkeypatching internals

### 9. [app.py](app.py) — Flask Routes
- `GET /` — renders `templates/index.html`
- `POST /upload_photo` — validates + normalizes an uploaded character photo (Pillow, RGB, capped dimension, UUID filename)
- `POST /generate` — rate-limited (SEC-2 interim); parses the request, validates, delegates to `story_service.generate_book`, returns its result as-is
- `GET /images/<story_id>/<path:filename>` — serves a story asset by id, never a client-supplied path
- `POST /download_pdf` — takes only `story_id`; rebuilds the image list and title from that story's own `story.json` on disk (never from client-supplied paths)

### 10. [templates/index.html](templates/index.html) — Frontend
- Classic mode: single keywords/characters/setting/style form
- Mixed-media mode: structured per-character cards (photoreal + cartoon), each with dropdown traits + free text; photoreal cards get a photo-upload widget (face-swap) and, when mixed-media is on, an experimental "Scene Image Model" override (see `model_routing.py`)
- After generation: renders the 5 scenes, the character reference images (with the original uploaded photo shown alongside a face-swapped reference for comparison), and a PDF download button

---

## User Flow

```
1. User fills the form (classic: keywords/characters/setting/style;
   mixed-media: + structured character cards, optional photo upload)
                                 │
                                 ▼
2. POST /generate (rate-limited per IP)
   → story_service.generate_book:
       a. story generation + reference-image generation run CONCURRENTLY
          (mixed-media only; classic mode has no references)
       b. story.json persisted
       c. 5 scene images generated sequentially (sliding window + refs)
                                 │
                                 ▼
3. Response: story_id + filenames (never filesystem paths) + story text
                                 │
                                 ▼
4. UI renders scenes + character references via
   GET /images/<story_id>/<filename>
                                 │
                                 ▼
5. [Optional] POST /download_pdf {story_id} → PDF built server-side
   from that story's own story.json, returned as a download
```

---

## What Works

| Feature | Status | Notes |
|---------|--------|-------|
| Gemini text → structured JSON story | ✅ Working | Classic + mixed-media modes |
| Sliding-window + per-character reference images | ✅ Working | Reference anchors tame style drift observed in early testing |
| Mixed-media (photoreal + cartoon world) | ✅ Working | Structured multi-character UI |
| Face-swap from an uploaded photo | ✅ Working | Manually E2E-validated — quality "excellent" |
| PDF generation on-demand | ✅ Working | Server rebuilds from `story.json`, not client input |
| Automated test suite | ✅ Working | 155+ pytest tests, no real API calls in the suite |
| Path-traversal-safe asset serving | ✅ Fixed | `/images` and `/download_pdf` take only an id, never a path |
| Response/retry hardening on the Gemini call | ✅ Fixed | Bounded retry, image-byte validation, correct error on safety-block |
| Concurrent reference + story generation | ✅ Working | Independent steps no longer run needlessly sequentially |
| Per-request cost visibility | ✅ Working | `usage_metadata` token counts logged per call |
| Per-IP rate limiting on `/generate` | ⚠️ Interim | In-process only; durable fix is real auth (Next.js migration) |

---

## What's Not Yet Done

- **Per-book cost does not scale** — a 5-page mixed-media/face-swap book measured ~CAD 3.5–3.8, over the original $3 POC ceiling. This is the project's main open problem; see `BookCostOptimization.md` for the ranked levers (hybrid model routing is built as infrastructure but not yet quality-verified; reference reuse and draft/approve flows need the Next.js-era persistence layer)
- **Real per-user auth** — `/generate` is currently protected only by an interim per-IP rate limit, not real authentication; planned for the Next.js migration (`NextJSWebDesign.md`)
- **Async job model** — generation is still a single ~1–3 minute synchronous HTTP request; a request killed mid-generation forces a full-cost retry. Planned as part of the Next.js migration
- **Character library / reference reuse** — regenerating a returning character's reference from scratch every book; needs persistence, out of scope for the current Flask app
- **Parent photo upload for the *user's own family*** — the face-swap feature exists for POC testing under current privacy assumptions (developer's own/consenting test photos); broader consumer-facing photo upload still needs a privacy/child-safety review
- **Multi-language support** — out of scope for POC

---

## Cost Profile

Cost is the project's central open problem, not a settled fact worth restating in detail here — see **`BookCostOptimization.md`** for the current numbers, the measured-vs-list-price anomaly, and the ranked reduction levers, and **`Test_Results.md`** for raw per-run metrics (API call counts, token counts, measured CAD cost). In short: the original ~$0.90 CAD/book estimate (classic mode, Flash) held for the simple case, but a mixed-media/face-swap book on Pro measured **~CAD 3.5–3.8** — over the original $3 POC ceiling.

---

## How to Run Locally

```bash
# 1. Clone repo and enter folder
git clone https://github.com/ritvikpande/ai-books.git
cd ai-books

# 2. Create + activate virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create .env with your API key
cp .env.example .env
# Then edit .env and paste your GEMINI_API_KEY

# 5. Run the app
python app.py
# Open http://localhost:5000

# Run the test suite (no API key needed — no real Gemini calls in tests)
python -m pytest -q
```
