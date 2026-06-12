"""Assemble mixed-media image prompts from LLM-written scene fields.

The boilerplate skeleton below was validated manually and must appear verbatim
in every scene's prompt — the LLM only supplies the scene-specific middle.
Keys of STYLE_PHRASES are lowercase because app.py lowercases art_style.
"""

STYLE_PHRASES = {
    "2d flat vector cartoon (pastel)": {
        "world_phrase": "2D flat vector cartoon",
        "style_closer": "Clean lines, pastel colors for the background, collage art style",
    },
    "watercolor storybook illustration": {
        "world_phrase": "2D watercolor storybook illustration",
        "style_closer": "Soft watercolor washes for the background, collage art style",
    },
    "cartoon illustration": {
        "world_phrase": "2D cartoon illustration",
        "style_closer": "Bold clean outlines, bright friendly colors for the background, collage art style",
    },
    "pencil sketch illustration": {
        "world_phrase": "2D pencil sketch illustration",
        "style_closer": "Soft graphite shading for the background, collage art style",
    },
    "pixel art illustration": {
        "world_phrase": "2D pixel art illustration",
        "style_closer": "Retro pixel detail for the background, collage art style",
    },
}

DEFAULT_STYLE = "2d flat vector cartoon (pastel)"


def _clause(text: str) -> str:
    """Trim whitespace and any trailing period so sentence joins stay clean."""
    return text.strip().rstrip(".")


def assemble_mixed_media_prompt(
    scene: dict,
    photoreal_characters: str,
    cartoon_characters: str,
    art_style: str,
) -> str:
    """Wrap the scene's visual fields in the validated mixed-media boilerplate.

    Preconditions: all string args must be non-None, and scene must have passed
    story_generator._validate_story (guarantees non-empty photoreal_action and
    background). Only cartoon_elements is optional and may be missing/None/empty.
    """
    phrases = STYLE_PHRASES.get(art_style.lower().strip(), STYLE_PHRASES[DEFAULT_STYLE])

    sentences = [
        "A mixed media children's book illustration collage.",
        (
            "In the center, a photorealistic, high-resolution photograph of "
            f"{_clause(scene['photoreal_action'])}."
        ),
    ]

    cartoon_elements = _clause(scene.get("cartoon_elements") or "")
    if cartoon_elements:
        sentences.append(f"{cartoon_elements}.")

    sentences.append(
        f"The background is a purely {phrases['world_phrase']}: "
        f"{_clause(scene['background'])}."
    )

    contrast = (
        "There is a distinct, sharp contrast between the photographic real "
        f"{_clause(photoreal_characters)} and the completely 2D cartoon world"
    )
    if cartoon_characters.strip():
        contrast += f" and cartoon {_clause(cartoon_characters)}"
    sentences.append(contrast + ".")

    sentences.append(f"{phrases['style_closer']}.")
    sentences.append("No text or words in the image.")

    return " ".join(sentences)
