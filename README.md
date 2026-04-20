# AI Storybook Generator

A Python proof-of-concept that generates illustrated children's storybooks using the Gemini API. The system takes user inputs (keywords, characters, setting, story type) and produces a 5-image storybook with narrative coherence using a sliding-window approach.

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
   streamlit run app.py
   ```

## Project Structure

- `config.py` — API client setup, constants
- `story_generator.py` — Story text and image prompt generation via Gemini
- `image_generator.py` — Image generation with sliding-window context
- `app.py` — Streamlit frontend
- `outputs/` — Generated storybooks (gitignored)
