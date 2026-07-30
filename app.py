import os
import json
import re
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

# Story asset serving (SEC-1): stories are looked up by id, never by a
# client-supplied filesystem path. story_dir names are always "story_<ts>".
STORY_ID_RE = re.compile(r'^story_[0-9_]+$')


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


def _resolve_story_dir(story_id: str) -> str:
    """Resolve a story_id to its real directory inside OUTPUT_DIR.

    Never trusts the caller with a filesystem path directly — only an id
    matching STORY_ID_RE, then confined to OUTPUT_DIR via a realpath
    containment check (also defends against escaping through a symlink).
    Raises ValueError for anything invalid or not found.
    """
    if not STORY_ID_RE.match(story_id or ""):
        raise ValueError("Invalid story id.")
    base_dir = os.path.realpath(OUTPUT_DIR)
    story_dir = os.path.realpath(os.path.join(base_dir, story_id))
    if story_dir != base_dir and not story_dir.startswith(base_dir + os.sep):
        raise ValueError("Invalid story id.")
    if not os.path.isdir(story_dir):
        raise ValueError("Story not found.")
    return story_dir


def _resolve_story_asset(story_id: str, filename: str) -> str:
    """Resolve a story_id + '/'-separated relative filename to a real file
    path confined to that story's directory. Raises ValueError for anything
    absolute, containing '..'/'.' segments, or resolving outside the dir.
    """
    story_dir = _resolve_story_dir(story_id)
    if not filename or "\\" in filename or filename.startswith("/"):
        raise ValueError("Invalid filename.")
    segments = filename.split("/")
    if any(seg in ("", ".", "..") for seg in segments):
        raise ValueError("Invalid filename.")

    full_path = os.path.realpath(os.path.join(story_dir, *segments))
    if full_path != story_dir and not full_path.startswith(story_dir + os.sep):
        raise ValueError("Invalid filename.")
    if not os.path.isfile(full_path):
        raise ValueError("Asset not found.")
    return full_path


def _relative_filename(path: str, story_dir: str) -> str:
    """POSIX-style ('/'-separated) path of `path` relative to `story_dir`,
    for embedding in API responses instead of an absolute filesystem path."""
    return os.path.relpath(path, story_dir).replace(os.sep, "/")


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

        # Never send filesystem paths to the browser — only a story_id and
        # filenames relative to it, resolved back through /images (SEC-1).
        story_id = os.path.basename(story_dir)
        response_story = dict(story)
        if response_story.get("character_refs"):
            response_story["character_refs"] = [
                {
                    "kind": ref["kind"],
                    "index": ref["index"],
                    "name": ref["name"],
                    "from_photo": ref.get("from_photo", False),
                    "filename": _relative_filename(ref["path"], story_dir),
                    "upload_filename": (
                        _relative_filename(ref["upload_path"], story_dir)
                        if ref.get("upload_path") else None
                    ),
                }
                for ref in response_story["character_refs"]
            ]

        return jsonify({
            "message": "Success",
            "story": response_story,
            "story_id": story_id,
            "image_filenames": [_relative_filename(p, story_dir) for p in image_paths],
            "story_title": story["title"],
            "time_elapsed": round(total_elapsed, 1)
        })

    except Exception as e:
        logger.error(f"Generation error: {e}")
        return jsonify({"error": str(e)}), 500

# Endpoint to serve generated images to the frontend. Assets are looked up
# by story_id + filename (never a client-supplied filesystem path) and
# confined to that story's directory inside OUTPUT_DIR — see
# _resolve_story_asset (SEC-1).
@app.route('/images/<story_id>/<path:filename>', methods=['GET'])
def get_image(story_id, filename):
    try:
        full_path = _resolve_story_asset(story_id, filename)
    except ValueError:
        return "Image not found", 404
    return send_from_directory(os.path.dirname(full_path), os.path.basename(full_path))

# Endpoint to generate and download the PDF. The client sends only a
# story_id; the image list and title are rebuilt from that story's own
# story.json on disk, never from client-supplied paths (SEC-1).
@app.route('/download_pdf', methods=['POST'])
def download_pdf():
    data = request.json or {}
    try:
        story_dir = _resolve_story_dir(data.get('story_id'))
        story_json_path = os.path.join(story_dir, "story.json")
        if not os.path.isfile(story_json_path):
            raise ValueError("Story not found.")
        with open(story_json_path) as f:
            story = json.load(f)
        image_paths = [
            os.path.join(story_dir, f"scene_{s['scene_number']}.png")
            for s in story["scenes"]
        ]
        pdf_bytes = generate_pdf(image_paths, story["title"], story_dir)
        return send_file(
            BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"{story['title'].replace(' ', '_')}.pdf"
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"PDF error: {e}")
        return jsonify({"error": "Could not generate PDF."}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)