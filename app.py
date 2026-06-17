import os
import json
import time
import uuid
import datetime
import logging
from io import BytesIO
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
from PIL import Image

from story_generator import generate_story
from image_generator import generate_all_images, generate_reference_images, generate_pdf
from config import OUTPUT_DIR, DEFAULT_PROVIDER, DEFAULT_IMAGE_MODEL
from providers import get_provider, validate_model, providers_meta

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8MB cap on uploaded photos

# Structured-character handling (mixed-media mode)
CHARACTER_FIELDS = ("name", "skin_tone", "hair_color", "body_type", "height",
                    "description", "photo_path")
MAX_CHARACTERS = 6  # soft cap to bound request size / cost across refs + window

# Photo upload handling (face-swap reference photos)
ALLOWED_PHOTO_EXTENSIONS = {".png", ".jpg", ".jpeg"}
MAX_PHOTO_DIMENSION = 1536


def _normalize_characters(raw) -> list:
    """Coerce a raw JSON character list into clean dicts, dropping empty entries.

    Each result has every CHARACTER_FIELDS key (trimmed string). Non-dict items
    and characters with no content at all are dropped. Non-list input -> [].
    """
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        char = {f: str(item.get(f) or "").strip() for f in CHARACTER_FIELDS}
        if any(char.values()):
            result.append(char)
    return result


def _save_uploaded_photo(file_storage) -> str:
    """Validate, normalize, and persist an uploaded character photo.

    Validates the extension before attempting to decode (cheap rejection for
    obviously-wrong files), normalizes via Pillow to RGB and a max 1536px
    dimension, and saves as PNG under a UUID filename — filenames are never
    user-derived, which sidesteps path traversal entirely. Raises ValueError
    for any client-caused problem (caught by the route and turned into a 400).
    The upload directory is computed fresh from OUTPUT_DIR on every call (not
    cached as a module-level constant) so tests that monkeypatch OUTPUT_DIR
    affect it correctly.
    """
    filename = file_storage.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_PHOTO_EXTENSIONS:
        raise ValueError("Photo must be a PNG or JPG file.")

    try:
        img = Image.open(file_storage.stream).convert("RGB")
    except Exception:
        raise ValueError("Could not read photo file.")

    img.thumbnail((MAX_PHOTO_DIMENSION, MAX_PHOTO_DIMENSION))

    upload_dir = os.path.join(OUTPUT_DIR, "_uploads")
    os.makedirs(upload_dir, exist_ok=True)
    path = os.path.join(upload_dir, f"{uuid.uuid4().hex}.png")
    img.save(path, "PNG")
    return path


@app.route('/upload_photo', methods=['POST'])
def upload_photo():
    file = request.files.get('photo')
    if not file or not file.filename:
        return jsonify({"error": "No photo file provided."}), 400
    try:
        path = _save_uploaded_photo(file)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Photo upload error: {e}")
        return jsonify({"error": "Could not process photo."}), 500
    return jsonify({"photo_path": path})


@app.route('/', methods=['GET'])
def index():
    return render_template(
        'index.html',
        providers=providers_meta(),
        default_provider=DEFAULT_PROVIDER,
        default_image_model=DEFAULT_IMAGE_MODEL,
    )

@app.route('/generate', methods=['POST'])
def generate():
    data = request.json
    keywords = data.get('keywords')
    characters = data.get('characters')
    setting = data.get('setting')
    story_type = data.get('story_type', 'Adventure').lower()
    art_style = data.get('art_style', 'Watercolor storybook illustration').lower()

    provider_id = data.get('provider', DEFAULT_PROVIDER)
    image_model = data.get('image_model', DEFAULT_IMAGE_MODEL)
    try:
        validate_model(provider_id, image_model)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    mixed_media = bool(data.get('mixed_media'))
    photoreal_characters = _normalize_characters(data.get('photoreal_characters'))
    cartoon_characters = _normalize_characters(data.get('cartoon_characters'))

    if mixed_media:
        if not keywords or not setting:
            return jsonify({"error": "Please fill in Keywords and Setting."}), 400
        if not photoreal_characters:
            return jsonify({"error": "Add at least one photorealistic character."}), 400
        if len(photoreal_characters) + len(cartoon_characters) > MAX_CHARACTERS:
            return jsonify({"error": f"Too many characters (max {MAX_CHARACTERS})."}), 400
    else:
        if not keywords or not characters or not setting:
            return jsonify({"error": "Please fill in Keywords, Characters, and Setting."}), 400

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    story_dir = os.path.join(OUTPUT_DIR, f"story_{timestamp}")
    os.makedirs(story_dir, exist_ok=True)

    try:
        total_start = time.time()
        provider = get_provider(provider_id)

        # Generate story
        story = generate_story(
            keywords=keywords,
            characters=characters or "",
            setting=setting,
            story_type=story_type,
            art_style=art_style,
            mixed_media=mixed_media,
            photoreal_characters=photoreal_characters,
            cartoon_characters=cartoon_characters,
        )

        # Mixed-media: generate one reference image per character first, then
        # attach them to every scene so characters stay consistent.
        reference_paths = None
        if mixed_media:
            refs = generate_reference_images(
                photoreal_characters, cartoon_characters, art_style,
                story_dir, provider, image_model,
            )
            reference_paths = [r["path"] for r in refs]
            story["character_refs"] = refs

        with open(os.path.join(story_dir, "story.json"), "w") as f:
            json.dump(story, f, indent=2)

        # Generate all images
        image_paths = generate_all_images(
            story, story_dir, provider, image_model,
            reference_paths=reference_paths,
        )

        total_elapsed = time.time() - total_start
        logger.info(f"Total generation time: {total_elapsed:.1f}s")

        return jsonify({
            "message": "Success",
            "story": story,
            "image_paths": image_paths, 
            "story_title": story["title"],
            "story_dir": story_dir,
            "time_elapsed": round(total_elapsed, 1)
        })

    except Exception as e:
        logger.error(f"Generation error: {e}")
        return jsonify({"error": str(e)}), 500

# Endpoint to serve generated images to the frontend
@app.route('/images', methods=['GET'])
def get_image():
    filepath = request.args.get('path')
    if not filepath or not os.path.exists(filepath):
        return "Image not found", 404
    
    directory = os.path.dirname(filepath)
    filename = os.path.basename(filepath)
    return send_from_directory(directory, filename)

# Endpoint to generate and download the PDF
@app.route('/download_pdf', methods=['POST'])
def download_pdf():
    data = request.json
    try:
        pdf_bytes = generate_pdf(
            data['image_paths'],
            data['story_title'],
            data['story_dir']
        )
        return send_file(
            BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"{data['story_title'].replace(' ', '_')}.pdf"
        )
    except Exception as e:
        logger.error(f"PDF error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)