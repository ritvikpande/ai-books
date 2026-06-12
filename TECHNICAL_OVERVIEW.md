# AI Storybook Generator — Technical Overview

## Project Summary

A Python-based proof of concept that generates illustrated children's storybooks for toddlers (ages 2–5). The user provides keywords, characters, setting, story type, and art style via a Streamlit web interface. The system generates a 5-scene story with consistent illustrations using the Google Gemini API, and offers a downloadable PDF of the final storybook.

**Repository:** https://github.com/ritvikpande/ai-books
**Live demo:** https://storybook-app-802321863547.northamerica-northeast1.run.app
**Stage:** Deployed to GCP Cloud Run (Flask + Docker + Cloud Run, region `northamerica-northeast1`)

---

## Technical Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.x |
| AI Text Generation | Gemini (`gemini-3-flash-preview`) |
| AI Image Generation | Gemini (`gemini-2.5-flash-image`) |
| API SDK | `google-genai` |
| Image Processing | Pillow (PIL) |
| Web Framework | Flask + Gunicorn |
| Frontend | HTML + Bootstrap (templates/index.html) |
| Containerization | Docker |
| Hosting | Google Cloud Run (northamerica-northeast1) |
| Environment Management | `python-dotenv`, venv |
| Version Control | Git + GitHub |

---

## Project Structure

```
ai-books/
├── .env                    # GEMINI_API_KEY (gitignored)
├── .env.example            # Template for required env vars
├── .gitignore              # Excludes venv/, .env, outputs/, __pycache__
├── README.md               # Setup & usage docs
├── requirements.txt        # Dependencies
├── config.py               # API client + constants
├── story_generator.py      # Gemini text API → structured story JSON
├── image_generator.py      # Gemini image API + caption overlay + PDF stitching
├── app.py                  # Streamlit frontend (thin UI layer)
├── venv/                   # Local Python environment (gitignored)
└── outputs/                # Generated storybooks (gitignored)
    └── story_<timestamp>/
        ├── story.json
        ├── scene_1.png ... scene_5.png
        └── <title>.pdf
```

**Design principle:** Only `app.py` imports Streamlit. Business logic lives in pure Python modules, making the eventual Flask migration a clean UI-layer swap.

---

## Module Breakdown

### 1. [config.py](config.py) — Configuration

- Loads `GEMINI_API_KEY` from `.env` via `python-dotenv`
- Defines model constants: `TEXT_MODEL`, `IMAGE_MODEL`, `OUTPUT_DIR`
- Exposes `get_client()` which initializes and returns a `genai.Client`
- Raises a clear error if the API key is missing or is still the placeholder

### 2. [story_generator.py](story_generator.py) — Story + Prompt Generation

- **Function:** `generate_story(keywords, characters, setting, story_type, art_style) → dict`
- Calls the Gemini text model with:
  - A carefully crafted **system prompt** instructing the model to act as a toddler picture-book author
  - A **user prompt** containing the five inputs
- Enforces structured JSON output: `{ "title": str, "scenes": [ {scene_number, text, image_prompt} × 5 ] }`
- Strips any stray markdown code-fences (`` ```json ... ``` ``) the model wraps the response in
- Validates the response: title present, exactly 5 scenes, all required keys on each scene
- Each `image_prompt` includes consistent character descriptions (same hair, clothing, etc.) to minimize visual drift across scenes

### 3. [image_generator.py](image_generator.py) — Image Generation + PDF

**Core generation helpers:**
- `_build_contents(prompt, context_paths)` — builds a multimodal payload: previous images as `types.Part.from_bytes()` first, then the scene's text prompt as `types.Part.from_text()`. This is what enables the sliding window.
- `_generate_with_context(prompt, context_paths, output_path, caption_text)` — the single API-calling workhorse. Logs per-request timing, extracts image bytes from the response, writes PNG to disk, and optionally burns in the caption.

**Public API:**
- `generate_single_image(prompt, output_path, caption_text)` — generates one image from text only (kept for standalone testing).
- `generate_all_images(story, output_dir) → list[str]` — loops through all 5 scenes with the sliding window logic.

**Sliding Window Logic:**
```
Scene 1 → context: []                    (no prior images)
Scene 2 → context: [scene_1]
Scene 3 → context: [scene_1, scene_2]
Scene 4 → context: [scene_2, scene_3]
Scene 5 → context: [scene_3, scene_4]
```
This keeps character appearance and art style consistent across the book by continuously feeding the two most recent generated images back into the next generation call.

**Caption Overlay — `add_caption(image_path, caption_text)`:**
- Opens the generated PNG as RGBA
- Wraps scene text to fit ~55% of image width using a helper that measures pixel width with Pillow
- Positions text anchored 10% from the right edge, 10% from the top
- Renders **white text with a thick black stroke** (`stroke_width=2`) — no background box, pure text-on-image
- Saves back as RGB PNG in-place

**PDF Generation — `generate_pdf(image_paths, story_title, output_dir) → bytes`:**
- Uses Pillow's built-in PDF writer (`first.save(format="PDF", save_all=True, append_images=rest)`)
- One scene per page
- Writes the PDF to disk alongside the PNGs and returns the bytes for Streamlit's download button

### 4. [app.py](app.py) — Streamlit Frontend

**Sidebar inputs:**
- Text fields: Keywords, Characters, Setting
- Dropdowns: Story Type (Adventure / Bedtime / Funny / Learning), Art Style (Watercolor / Cartoon / Pencil / Pixel)
- "Generate Story" primary button

**Main area workflow:**
1. Validates that required fields are filled
2. Creates a per-run folder: `outputs/story_<YYYYMMDD_HHMMSS>/`
3. Calls `generate_story()` with a spinner → saves `story.json`
4. Calls `generate_all_images()` with a spinner (takes ~1–2 min) → 5 captioned PNGs
5. Renders scenes in a **2-column grid** (2 images per row) with the scene text captioned underneath
6. Logs total generation time both to the console and on screen
7. Stashes results in `st.session_state` so the PDF button can use them without re-running generation

**PDF download (on-demand):**
- Button appears only after a story has been generated
- On click → shows a spinner while `generate_pdf()` runs → presents a second `st.download_button` to actually download the file
- This lazy approach avoids wasting compute on users who just want to view the book

---

## User Flow

```
┌────────────────────────────────────────────────────────────────────┐
│ 1. User opens Streamlit app: `streamlit run app.py`                │
└────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌────────────────────────────────────────────────────────────────────┐
│ 2. User fills sidebar inputs:                                      │
│    • Keywords: "ice cream, rainbows"                               │
│    • Characters: "Mia, a curious girl, and Biscuit, a cat"         │
│    • Setting: "a candy forest"                                     │
│    • Story Type: Adventure                                         │
│    • Art Style: Watercolor storybook illustration                  │
└────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌────────────────────────────────────────────────────────────────────┐
│ 3. User clicks "Generate Story"                                    │
└────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌────────────────────────────────────────────────────────────────────┐
│ 4. [Backend] Story Generation (~5–10s)                             │
│    • Gemini text model called with system + user prompts           │
│    • Returns JSON with title + 5 scenes (text + image_prompt)      │
│    • Validated and saved to `story.json`                           │
│    • "Story written: <title>" shown in UI                          │
└────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌────────────────────────────────────────────────────────────────────┐
│ 5. [Backend] Image Generation — sequential, ~1–2 min total         │
│    For each scene 1..5:                                            │
│      a. Build multimodal payload: [prev images] + [text prompt]    │
│      b. Call Gemini image API                                      │
│      c. Extract image bytes, save as scene_N.png                   │
│      d. Open PNG, burn caption text top-right                      │
│      e. Timing logged per scene                                    │
└────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌────────────────────────────────────────────────────────────────────┐
│ 6. [UI] Storybook displayed                                        │
│    • Title as header                                               │
│    • Scenes in 2-column grid (scenes 1&2, 3&4, 5)                  │
│    • Each image shown with its caption underneath                  │
│    • Total generation time shown                                   │
└────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌────────────────────────────────────────────────────────────────────┐
│ 7. [Optional] User clicks "Download PDF"                           │
│    • Spinner shown while Pillow stitches PNGs into a PDF           │
│    • "Click here to download" button appears                       │
│    • User downloads <story_title>.pdf                              │
└────────────────────────────────────────────────────────────────────┘
```

---

## What Works

| Feature | Status | Notes |
|---------|--------|-------|
| Gemini text → structured JSON story | ✅ Working | Robust JSON parsing with markdown-fence stripping |
| Validation of story response | ✅ Working | Asserts 5 scenes + required keys |
| Gemini image generation (single) | ✅ Working | `generate_single_image()` for testing |
| Sliding window image generation | ✅ Working | Up to 2 previous images fed as context |
| Character/style consistency across scenes | ✅ Good | Much improved vs. text-only prompts |
| Caption overlay (white text + black stroke) | ✅ Working | Top-right position, auto-wraps text |
| 2-column responsive grid in UI | ✅ Working | Clean, readable layout |
| PDF generation on-demand | ✅ Working | Lazy — only runs when user clicks |
| Per-request + total timing logs | ✅ Working | Both console and UI |
| Per-run output folders | ✅ Working | `outputs/story_<timestamp>/` |
| `.env` + `.gitignore` hygiene | ✅ Working | API key never committed |

---

## What's Not Yet Done

- **Automated tests** — manual verification only for POC
- **Auth / endpoint security** — deferred until after POC
- **Rate-limit retry/backoff** — not needed on paid tier but will matter later
- ~~**Flask migration**~~ ✅ Done
- ~~**Docker containerization**~~ ✅ Done
- ~~**GCP deployment**~~ ✅ Done — live at https://storybook-app-802321863547.northamerica-northeast1.run.app
- **Parent photo upload / photorealistic family characters** — out of scope for POC (privacy/child-safety review needed first)
- **Multi-language support** — out of scope for POC

---

## Cost Profile

- Text generation: fractions of a cent per run
- Image generation: ~$0.18 CAD per image × 5 = ~$0.90 CAD per storybook
- POC-level testing comfortably fits within the $20 USD credits already on the billing account
- A $4 USD monthly budget alert is configured in GCP

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
streamlit run app.py
```
