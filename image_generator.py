import os
import io
import shutil
import time
import logging
from PIL import Image, ImageDraw, ImageFont
from config import OUTPUT_DIR
from prompt_assembly import assemble_reference_prompt, character_label

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

def _load_context_bytes(context_paths: list) -> list:
    """Read sliding-window context images from disk as PNG bytes."""
    images = []
    for path in context_paths:
        with open(path, "rb") as f:
            images.append(f.read())
    return images


def _generate_with_context(
    prompt: str,
    context_paths: list,
    output_path: str,
    provider,
    model: str,
    caption_text: str = "",
    reference_paths: list = None
) -> str:
    """
    Generate one image with optional context images.

    Context order: character reference images FIRST (stable appearance anchor),
    then the sliding window of previous pages. Saves to output_path, applies
    caption if provided. Returns output_path.
    """
    reference_paths = reference_paths or []
    logger.info(f"Generating image: {os.path.basename(output_path)} "
                f"(model: {model}, refs: {len(reference_paths)}, "
                f"context: {len(context_paths)} previous image(s))")
    start = time.time()

    context_images = (
        _load_context_bytes(reference_paths) + _load_context_bytes(context_paths)
    )
    image_data = provider.generate_image(
        prompt=prompt,
        context_images=context_images,
        model=model,
    )

    elapsed = time.time() - start
    logger.info(f"Image response received in {elapsed:.1f}s")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
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

def generate_single_image(prompt: str, output_path: str, provider, model: str,
                          caption_text: str = "") -> str:
    """
    Generate a single image from a text prompt (no context).
    Kept for standalone testing.
    """
    return _generate_with_context(prompt, [], output_path, provider, model, caption_text)


def generate_reference_images(
    photoreal_characters: list,
    cartoon_characters: list,
    art_style: str,
    output_dir: str,
    provider,
    model: str,
) -> list:
    """Generate one standalone reference image per character.

    Order is the reference-ordering invariant shared with the prompt assembler and
    generate_all_images: photoreal characters first, then cartoon. Saved under
    <output_dir>/refs/ as <kind>_<index>.png with NO caption (these anchor the
    characters' appearance and must stay clean). Cartoon characters are skipped
    entirely when that list is empty.

    Photoreal characters with a usable photo_path (photoreal only — cartoon never
    has upload UI) pass that photo's bytes as context_images and get a
    face-preservation prompt; the original photo is copied alongside the
    generated reference as <kind>_<index>_upload.png. A missing/stale photo_path
    degrades gracefully to the no-photo path.

    Returns ordered records: [{"kind", "index", "name", "path", "from_photo"}, ...].
    """
    refs_dir = os.path.join(output_dir, "refs")
    os.makedirs(refs_dir, exist_ok=True)

    records = []
    groups = (
        ("photoreal", photoreal_characters or []),
        ("cartoon", cartoon_characters or []),
    )
    for kind, chars in groups:
        for index, char in enumerate(chars, start=1):
            photo_path = char.get("photo_path") if kind == "photoreal" else None
            has_photo = bool(photo_path) and os.path.exists(photo_path)

            prompt = assemble_reference_prompt(char, kind, art_style, has_photo=has_photo)
            label = character_label(char)
            logger.info(f"Generating {kind} reference {index} ({label})"
                        f"{' from uploaded photo' if has_photo else ''}")
            start = time.time()

            context_images = _load_context_bytes([photo_path]) if has_photo else []
            image_data = provider.generate_image(
                prompt=prompt, context_images=context_images, model=model
            )

            logger.info(f"Reference image received in {time.time() - start:.1f}s")
            path = os.path.join(refs_dir, f"{kind}_{index}.png")
            with open(path, "wb") as f:
                f.write(image_data)

            if has_photo:
                upload_copy_path = os.path.join(refs_dir, f"{kind}_{index}_upload.png")
                shutil.copyfile(photo_path, upload_copy_path)

            records.append({
                "kind": kind, "index": index, "name": label,
                "path": path, "from_photo": has_photo,
            })

    logger.info(f"{len(records)} character reference image(s) generated.")
    return records


def generate_all_images(story: dict, output_dir: str, provider, model: str,
                        reference_paths: list = None) -> list:
    """
    Generate all 5 scene images using a sliding window of previous images.

    Window:
      Scene 1: no context
      Scene 2: [scene_1]
      Scene 3: [scene_1, scene_2]
      Scene 4: [scene_2, scene_3]
      Scene 5: [scene_3, scene_4]

    reference_paths (mixed-media): character reference images attached to EVERY
    scene before the window, so characters re-anchor to a stable likeness each
    page. None/[] (classic mode) keeps the original window-only behavior.

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
            provider=provider,
            model=model,
            caption_text=scene["text"],
            reference_paths=reference_paths,
        )
        saved_paths.append(output_path)

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
    from providers import get_provider
    from config import DEFAULT_PROVIDER, DEFAULT_IMAGE_MODEL

    output_path = os.path.join(OUTPUT_DIR, "test", "scene_1.png")
    saved = generate_single_image(
        test_prompt,
        output_path,
        provider=get_provider(DEFAULT_PROVIDER),
        model=DEFAULT_IMAGE_MODEL,
        caption_text="Mia and Biscuit walk into the candy forest!",
    )
    print(f"\nImage saved to: {saved}")
    Image.open(saved).show()
