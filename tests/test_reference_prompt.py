import pytest

from prompt_assembly import assemble_reference_prompt, DEFAULT_STYLE, STYLE_PHRASES

CHAR = {
    "name": "Dad",
    "skin_tone": "medium",
    "hair_color": "dark brown",
    "body_type": "average",
    "height": "tall",
    "description": "green sweater, blue jeans",
}


# --- photoreal --------------------------------------------------------------

def test_photoreal_reads_as_real_photo():
    p = assemble_reference_prompt(CHAR, "photoreal", "watercolor storybook illustration")
    low = p.lower()
    assert "photorealistic" in low
    assert "photograph" in low
    assert "real person" in low
    assert p.endswith("No text or words in the image.")


def test_photoreal_includes_character_description():
    p = assemble_reference_prompt(CHAR, "photoreal", "2d flat vector cartoon (pastel)")
    assert "Dad" in p
    assert "dark brown hair" in p


def test_photoreal_has_no_cartoon_style_words():
    # The photorealistic reference must not inherit any 2D/cartoon style wording,
    # whatever art_style was selected for the book.
    p = assemble_reference_prompt(CHAR, "photoreal", "watercolor storybook illustration")
    for style in STYLE_PHRASES.values():
        assert style["style_closer"] not in p
        assert style["world_phrase"] not in p


# --- cartoon ----------------------------------------------------------------

def test_cartoon_uses_style_phrases():
    style = "watercolor storybook illustration"
    p = assemble_reference_prompt(CHAR, "cartoon", style)
    assert STYLE_PHRASES[style]["world_phrase"] in p
    assert STYLE_PHRASES[style]["style_closer"] in p
    assert "Dad" in p
    assert p.endswith("No text or words in the image.")


def test_cartoon_unknown_style_falls_back_to_default():
    p = assemble_reference_prompt(CHAR, "cartoon", "some future style")
    default = STYLE_PHRASES[DEFAULT_STYLE]
    assert default["world_phrase"] in p
    assert default["style_closer"] in p


@pytest.mark.parametrize("style_key", list(STYLE_PHRASES.keys()))
def test_cartoon_every_style_produces_its_phrases(style_key):
    p = assemble_reference_prompt(CHAR, "cartoon", style_key)
    assert STYLE_PHRASES[style_key]["world_phrase"] in p
    assert STYLE_PHRASES[style_key]["style_closer"] in p


# --- shared -----------------------------------------------------------------

def test_no_double_period_when_description_ends_with_period():
    char = dict(CHAR, description="wears a green sweater.")
    for kind in ("photoreal", "cartoon"):
        p = assemble_reference_prompt(char, kind, "watercolor storybook illustration")
        assert ".." not in p
