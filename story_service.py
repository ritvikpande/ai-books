"""Core storybook generation pipeline (ARCH-6).

Extracted from app.py's /generate view: validates generation inputs and
runs story -> character references -> scene images -> persistence,
returning a JSON-serializable result. Deliberately has no Flask import so
it's callable from a worker, CLI, or test without an HTTP request context.

The three generation-step functions (story / reference images / scene
images) are accepted as parameters with the real implementations as
defaults, rather than being called as free functions here, so callers can
swap them out via ordinary dependency injection instead of monkeypatching
this module's internals.
"""
import os
import json
import time
import logging
import datetime

from story_generator import generate_story as _default_generate_story
from image_generator import (
    generate_all_images as _default_generate_all_images,
    generate_reference_images as _default_generate_reference_images,
)
from providers import get_provider

logger = logging.getLogger(__name__)

MAX_CHARACTERS = 6  # soft cap to bound request size / cost across refs + window


class GenerationError(ValueError):
    """A user-facing problem with the generation request (maps to HTTP 400)."""


def validate_inputs(*, keywords, characters, setting, mixed_media,
                     photoreal_characters, cartoon_characters) -> None:
    """Raise GenerationError with a user-facing message if inputs are invalid."""
    if mixed_media:
        if not keywords or not setting:
            raise GenerationError("Please fill in Keywords and Setting.")
        if not photoreal_characters:
            raise GenerationError("Add at least one photorealistic character.")
        if len(photoreal_characters) + len(cartoon_characters) > MAX_CHARACTERS:
            raise GenerationError(f"Too many characters (max {MAX_CHARACTERS}).")
    else:
        if not keywords or not characters or not setting:
            raise GenerationError("Please fill in Keywords, Characters, and Setting.")


def _relative_filename(path: str, story_dir: str) -> str:
    """POSIX-style ('/'-separated) path of `path` relative to `story_dir`,
    for embedding in results instead of an absolute filesystem path."""
    return os.path.relpath(path, story_dir).replace(os.sep, "/")


def generate_book(
    *,
    keywords: str,
    characters: str,
    setting: str,
    story_type: str,
    art_style: str,
    mixed_media: bool,
    photoreal_characters: list,
    cartoon_characters: list,
    provider_id: str,
    image_model: str,
    output_dir: str,
    generate_story_fn=_default_generate_story,
    generate_reference_images_fn=_default_generate_reference_images,
    generate_all_images_fn=_default_generate_all_images,
) -> dict:
    """Run the full story -> references -> scenes pipeline and persist it.

    Returns a JSON-serializable dict: message, story, story_id,
    image_filenames, story_title, time_elapsed. Never contains an absolute
    filesystem path — only a story_id and filenames relative to it (SEC-1).
    Callers should call validate_inputs first; this function doesn't
    re-validate.
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    story_dir = os.path.join(output_dir, f"story_{timestamp}")
    os.makedirs(story_dir, exist_ok=True)

    total_start = time.time()
    provider = get_provider(provider_id)

    story = generate_story_fn(
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
        refs = generate_reference_images_fn(
            photoreal_characters, cartoon_characters, art_style,
            story_dir, provider, image_model,
        )
        reference_paths = [r["path"] for r in refs]
        story["character_refs"] = refs

    with open(os.path.join(story_dir, "story.json"), "w") as f:
        json.dump(story, f, indent=2)

    image_paths = generate_all_images_fn(
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

    return {
        "message": "Success",
        "story": response_story,
        "story_id": story_id,
        "image_filenames": [_relative_filename(p, story_dir) for p in image_paths],
        "story_title": story["title"],
        "time_elapsed": round(total_elapsed, 1),
    }
