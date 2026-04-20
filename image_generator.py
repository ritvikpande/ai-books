import os
import io
import time
import logging
from PIL import Image, ImageDraw, ImageFont
from google.genai import types
from config import get_client, IMAGE_MODEL, OUTPUT_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Caption overlay
# ---------------------------------------------------------------------------

def _wrap_text(text: str, font, max_width: int, draw: ImageDraw.Draw) -> str:
    """Wrap text to fit within max_width pixels."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        if draw.textlength(test, font=font) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return "\n".join(lines)


def add_caption(image_path: str, caption_text: str) -> None:
    """
    Burn caption text onto the image at top-right area (10% from top, right-anchored at 10% from right).
    Semi-transparent dark background box behind white text.
    Modifies the image in-place.
    """
    img = Image.open(image_path).convert("RGBA")
    W, H = img.size

    max_text_width = int(W * 0.55)
    font = ImageFont.load_default(size=20)

    # Measure wrapped text
    dummy_draw = ImageDraw.Draw(img)
    wrapped = _wrap_text(caption_text, font, max_text_width, dummy_draw)
    bbox = dummy_draw.textbbox((0, 0), wrapped, font=font)
    text_w = bbox[2] - bbox[0]

    padding = 10

    # Position: right-anchored at 10% from right, top at 10% from top
    box_x = W - int(W * 0.10) - text_w - padding
    box_y = int(H * 0.10)

    # Draw white text with black border directly on image
    draw = ImageDraw.Draw(img)
    draw.text(
        (box_x + padding, box_y + padding),
        wrapped,
        font=font,
        fill=(255, 255, 255, 255),
        stroke_width=2,
        stroke_fill=(0, 0, 0, 255)
    )

    img.convert("RGB").save(image_path, "PNG")


# ---------------------------------------------------------------------------
# Core image generation helpers
# ---------------------------------------------------------------------------

def _build_contents(prompt: str, context_paths: list) -> list:
    """Build multimodal contents list: previous images first, then text prompt."""
    parts = []
    for path in context_paths:
        with open(path, "rb") as f:
            parts.append(types.Part.from_bytes(data=f.read(), mime_type="image/png"))
    parts.append(types.Part.from_text(text=prompt))
    return parts


def _generate_with_context(
    prompt: str,
    context_paths: list,
    output_path: str,
    caption_text: str = ""
) -> str:
    """
    Generate one image with optional context images (sliding window).
    Saves to output_path, applies caption if provided.
    Returns output_path.
    """
    client = get_client()
    contents = _build_contents(prompt, context_paths)

    logger.info(f"Generating image: {os.path.basename(output_path)} "
                f"(context: {len(context_paths)} previous image(s))")
    start = time.time()

    response = client.models.generate_content(
        model=IMAGE_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"]
        )
    )

    elapsed = time.time() - start
    logger.info(f"Image response received in {elapsed:.1f}s")

    # Extract image bytes
    image_data = None
    for part in response.candidates[0].content.parts:
        if part.inline_data is not None:
            image_data = part.inline_data.data
            break

    if image_data is None:
        raise ValueError("No image returned in response")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(image_data)

    # Burn caption onto image
    if caption_text:
        add_caption(output_path, caption_text)

    logger.info(f"Image saved: {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_single_image(prompt: str, output_path: str, caption_text: str = "") -> str:
    """
    Generate a single image from a text prompt (no context).
    Kept for standalone testing.
    """
    return _generate_with_context(prompt, [], output_path, caption_text)


def generate_all_images(story: dict, output_dir: str) -> list:
    """
    Generate all 5 scene images using a sliding window of previous images.

    Window:
      Scene 1: no context
      Scene 2: [scene_1]
      Scene 3: [scene_1, scene_2]
      Scene 4: [scene_2, scene_3]
      Scene 5: [scene_3, scene_4]

    Returns list of saved image paths.
    """
    scenes = story["scenes"]
    saved_paths = []

    for i, scene in enumerate(scenes):
        n = scene["scene_number"]

        # Build sliding window: up to 2 previous images
        window_start = max(0, i - 2)
        context = saved_paths[window_start:i]

        output_path = os.path.join(output_dir, f"scene_{n}.png")
        _generate_with_context(
            prompt=scene["image_prompt"],
            context_paths=context,
            output_path=output_path,
            caption_text=scene["text"]
        )
        saved_paths.append(output_path)

        # # Sleep between requests to respect rate limits (skip after last scene)
        # if i < len(scenes) - 1:
        #     logger.info("Waiting 12s before next image (rate limit)...")
        #     time.sleep(12)

    logger.info(f"All {len(saved_paths)} images generated.")
    return saved_paths


def generate_pdf(image_paths: list, story_title: str, output_dir: str) -> bytes:
    """
    Stitch all scene images into a single PDF (one image per page).
    Saves to disk and returns PDF bytes for download.
    """
    images = [Image.open(p).convert("RGB") for p in image_paths]
    first = images[0]
    rest = images[1:]

    buf = io.BytesIO()
    first.save(buf, format="PDF", save_all=True, append_images=rest)
    pdf_bytes = buf.getvalue()

    safe_title = story_title.replace(" ", "_").replace("/", "-")
    pdf_path = os.path.join(output_dir, f"{safe_title}.pdf")
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    logger.info(f"PDF saved: {pdf_path}")
    return pdf_bytes


# ---------------------------------------------------------------------------
# Quick test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_prompt = (
        "Children's storybook illustration: Mia and Biscuit stand at the entrance "
        "of a forest where trees have chocolate trunks and lollipop leaves. "
        "Mia is a small girl with curly brown hair, a yellow sun hat, blue overalls, "
        "and red sneakers. Biscuit is a fluffy orange cat with white paws and a blue bowtie. "
        "Setting: A bright forest with giant candy canes. Mood: Playful. "
        "Style: watercolor storybook illustration. No text or words in the image."
    )
    output_path = os.path.join(OUTPUT_DIR, "test", "scene_1.png")
    saved = generate_single_image(test_prompt, output_path, caption_text="Mia and Biscuit walk into the candy forest!")
    print(f"\nImage saved to: {saved}")
    Image.open(saved).show()
