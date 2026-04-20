import os
import logging
from PIL import Image
from google.genai import types
from config import get_client, IMAGE_MODEL, OUTPUT_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)


def generate_single_image(prompt: str, output_path: str) -> str:
    """
    Generate a single image from a text prompt and save it to disk.

    Args:
        prompt: The image generation prompt
        output_path: Full path where the PNG will be saved

    Returns:
        The output_path where the image was saved
    """
    client = get_client()

    logger.info(f"Generating image: {os.path.basename(output_path)}")

    response = client.models.generate_content(
        model=IMAGE_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"]
        )
    )

    # Extract the image from the response
    image_data = None
    for part in response.candidates[0].content.parts:
        if part.inline_data is not None:
            image_data = part.inline_data.data
            break

    if image_data is None:
        raise ValueError("No image returned in response")

    # Save to disk
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(image_data)

    logger.info(f"Image saved: {output_path}")
    return output_path


if __name__ == "__main__":
    # Quick test — generate scene 1 from the sample story
    test_prompt = (
        "Children's storybook illustration: Mia and Biscuit stand at the entrance "
        "of a forest where trees have chocolate trunks and lollipop leaves. "
        "Mia is a small girl with curly brown hair, a yellow sun hat, blue overalls, "
        "and red sneakers. Biscuit is a fluffy orange cat with white paws and a blue bowtie. "
        "Setting: A bright forest with giant candy canes. Mood: Playful. "
        "Style: watercolor storybook illustration. No text or words in the image."
    )

    output_path = os.path.join(OUTPUT_DIR, "test", "scene_1.png")
    saved_path = generate_single_image(test_prompt, output_path)
    print(f"\nImage saved to: {saved_path}")
    print("Open the file to review it.")

    # Open the image for a quick preview
    img = Image.open(saved_path)
    img.show()
