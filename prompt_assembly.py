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


def _norm(value) -> str:
    """Normalize a character field: trim, treat None/'unspecified' as empty."""
    text = (value or "").strip()
    return "" if text.lower() == "unspecified" else text


def _join_and(items: list) -> str:
    """Join non-empty items with commas and a trailing 'and' (Oxford-free)."""
    items = [i for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + f" and {items[-1]}"


# Structured character fields, in the order they read best in a prompt.
_TRAIT_FIELDS = (
    ("height", "{} height"),
    ("skin_tone", "{} skin tone"),
    ("hair_color", "{} hair"),
    ("body_type", "{} build"),
)


def compose_character_description(char: dict) -> str:
    """Turn one structured character object into a single prose description.

    Name leads (as a label), then physical traits from the dropdowns, then the
    free-text description. Empty / 'unspecified' fields are skipped. The only
    place a character object becomes prose, so the reference-image prompt, the
    LLM context, and the scene prompt all agree. Returns "" for an empty object.
    """
    name = _norm(char.get("name"))
    traits = [
        fmt.format(_norm(char.get(key)))
        for key, fmt in _TRAIT_FIELDS
        if _norm(char.get(key))
    ]
    description = _norm(char.get("description"))
    if description:
        traits.append(description)

    trait_str = ", ".join(traits)
    if name and trait_str:
        return f"{name}: {trait_str}"
    return name or trait_str


def character_label(char: dict) -> str:
    """Short identifier for a character: its name, else its free text, else generic."""
    return _norm(char.get("name")) or _norm(char.get("description")) or "the character"


def join_labels(chars: list) -> str:
    """Join several characters' labels into one phrase, e.g. 'Dad and Mom'."""
    return _join_and([character_label(c) for c in chars])


def _reference_instruction(photoreal_characters: list, cartoon_characters: list) -> str:
    """Tell the model which attached reference image is which character.

    Enumeration order is the reference-ordering invariant: photoreal first, then
    cartoon — matching how image_generator prepends the reference bytes.
    """
    labels = (
        [character_label(c) for c in photoreal_characters]
        + [character_label(c) for c in cartoon_characters]
    )
    if not labels:
        return ""
    mapping = ", ".join(f"reference {i} is {label}" for i, label in enumerate(labels, 1))
    return (
        "Use the attached character reference images to keep each character's face, "
        f"hair, and clothing identical to their reference: {mapping}. "
        "Only the pose, expression, and action change in this scene. "
        "Any additional attached images are previous pages of this same book; "
        "match their overall style."
    )


def assemble_reference_prompt(char: dict, kind: str, art_style: str, has_photo: bool = False) -> str:
    """Build a standalone reference-image prompt for one character.

    kind="photoreal": reads as a real studio photograph — deliberately carries
    NO art-style words so the person never picks up a 2D/cartoon look.
    kind="cartoon": a flat 2D character sheet in the chosen STYLE_PHRASES look.
    The reference is generated with no context images so characters never blend.
    has_photo=True (photoreal only): an uploaded photo is being passed as a
    context image, so the prompt asks Gemini to preserve that face/identity
    instead of inventing one from the description.
    """
    description = _clause(compose_character_description(char))

    if kind == "photoreal":
        if has_photo:
            return (
                "Using the exact face and identity of the person in the attached "
                "photo — same facial features, skin tone, and likeness, face "
                "unchanged from the photo — generate a photorealistic, "
                f"high-resolution full-body studio photograph of {description}. "
                "Natural lighting, plain neutral background, sharp focus, "
                "neutral friendly expression, looking at the camera. "
                "This is a real photograph of a real person. "
                "No text or words in the image."
            )
        return (
            "A photorealistic, high-resolution full-body studio photograph of "
            f"{description}. Natural lighting, plain neutral background, sharp focus, "
            "neutral friendly expression, looking at the camera. "
            "This is a real photograph of a real person. "
            "No text or words in the image."
        )

    phrases = STYLE_PHRASES.get(art_style.lower().strip(), STYLE_PHRASES[DEFAULT_STYLE])
    return (
        f"A {phrases['world_phrase']} character reference of {description}. "
        "Full body, front view, plain background. "
        f"{phrases['style_closer']}. "
        "No text or words in the image."
    )


def assemble_mixed_media_prompt(
    scene: dict,
    photoreal_characters: list,
    cartoon_characters: list,
    art_style: str,
) -> str:
    """Wrap the scene's visual fields in the validated mixed-media boilerplate.

    photoreal_characters / cartoon_characters are lists of structured character
    objects (see compose_character_description). The scene's photoreal_action and
    cartoon_elements describe ACTION only; each character's fixed appearance comes
    from the attached reference images, which this prompt instructs the model to
    follow. Preconditions: scene has passed story_generator._validate_story
    (non-empty photoreal_action and background); cartoon_elements may be empty.
    """
    phrases = STYLE_PHRASES.get(art_style.lower().strip(), STYLE_PHRASES[DEFAULT_STYLE])
    photoreal_characters = photoreal_characters or []
    cartoon_characters = cartoon_characters or []

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
        f"{join_labels(photoreal_characters)} and the completely 2D cartoon world"
    )
    if cartoon_characters:
        contrast += f" and cartoon {join_labels(cartoon_characters)}"
    sentences.append(contrast + ".")

    reference_sentence = _reference_instruction(photoreal_characters, cartoon_characters)
    if reference_sentence:
        sentences.append(reference_sentence)

    sentences.append(f"{phrases['style_closer']}.")
    sentences.append("No text or words in the image.")

    return " ".join(sentences)
