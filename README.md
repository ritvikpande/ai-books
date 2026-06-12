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
- `story_generator.py` - Story text and image prompt generation via Gemini
- `image_generator.py` - Image generation with sliding-window context
- `app.py` - Flask backend (routes: `/`, `/generate`, `/images`, `/download_pdf`)
- `templates/index.html` - Frontend UI
- `Dockerfile` - Container image (gunicorn on port 5000)
