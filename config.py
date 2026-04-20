import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

# Model to use for both text and image generation
TEXT_MODEL = "gemini-2.5-flash-preview-05-20"
IMAGE_MODEL = "gemini-2.0-flash-preview-image-generation"

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
