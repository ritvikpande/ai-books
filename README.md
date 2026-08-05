# AI Storybook Generator

A Python proof-of-concept that generates illustrated children's storybooks using the Gemini API. The system takes user inputs (keywords, characters, setting, story type) and produces a 5-image storybook with narrative coherence using a sliding-window approach.

**Live demo:** https://storybook-app-802321863547.northamerica-northeast1.run.app

## Setup

1. Clone the repo:
   ```bash
   git clone https://github.com/ritvikpande/ai-books.git
   cd ai-books
   ```

2. Create and activate virtual environment:
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # macOS/Linux
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create a `.env` file from the template:
   ```bash
   cp .env.example .env
   ```
   Then add your Gemini API key to `.env`.

5. Run the app:
   ```bash
   python app.py
   ```
   Then open http://localhost:5000

## Run with Docker

```bash
docker build -t ai-books .
docker run -p 5000:5000 --env-file .env ai-books
```

## Deploy to Cloud Run

```bash
gcloud run deploy storybook-app \
  --source . \
  --region northamerica-northeast1 \
  --allow-unauthenticated \
  --set-env-vars GEMINI_API_KEY=your_key_here \
  --memory 1Gi \
  --timeout 300
```

## Project Structure

- `config.py` - API client setup, constants
- `providers.py` - Gemini image-provider abstraction: retry/backoff, client reuse, usage-token logging
- `model_routing.py` - Resolves which model each pipeline step uses (cost-experiment routing)
- `rate_limit.py` - Interim per-IP rate limiter for `/generate`
- `prompt_assembly.py` - Pure helpers that assemble mixed-media and character-reference image prompts
- `story_generator.py` - Story text and image prompt generation via Gemini
- `image_generator.py` - Image generation with sliding-window context + per-character reference images
- `story_service.py` - Generation pipeline orchestration (no Flask dependency)
- `app.py` - Flask backend (routes: `/`, `/generate`, `/upload_photo`, `/images/<story_id>/<filename>`, `/download_pdf`)
- `templates/index.html` - Frontend UI
- `Dockerfile` - Container image (gunicorn on port 5000)

> **Cost note (measured 2026-06-17):** a 5-page mixed-media book with face-swap on Gemini 3 Pro Image cost ~CAD 3.5–3.8 (8 API calls, 0 errors; 7 Pro image requests + 1 Flash text request) — over the POC's $3 ceiling. The per-book cost on Pro does not scale; cost reduction is the main open problem before scaling. See [`BookCostOptimization.md`](BookCostOptimization.md) for the ranked reduction levers.
