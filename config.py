import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

# Model used for story/text generation (image models live in providers.py)
TEXT_MODEL = "gemini-3-flash-preview"

# Defaults for image generation; must exist in providers.PROVIDERS
DEFAULT_PROVIDER = "google"
DEFAULT_IMAGE_MODEL = "gemini-2.5-flash-image"

# Output directory for generated storybooks
OUTPUT_DIR = "outputs"


def get_client():
    """Initialize and return the Gemini client."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "your_api_key_here":
        raise ValueError(
            "GEMINI_API_KEY not set. Add your API key to the .env file."
        )
    return genai.Client(api_key=api_key)
