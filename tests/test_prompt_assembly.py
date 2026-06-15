import pytest

from prompt_assembly import DEFAULT_STYLE, STYLE_PHRASES, assemble_mixed_media_prompt

# photoreal_action / cartoon_elements now describe ACTION only; fixed appearance
# comes from the attached reference images.
SCENE = {
    "scene_number": 1,
    "text": "Dad and Lily go to the playground.",
    "photoreal_action": "Dad pushing Lily on the swing, both laughing",
    "cartoon_elements": "Lily kicks her feet up high",
    "background": "a kids playground with beautiful trees and other cartoon children playing",
}

PHOTOREAL = [{
    "name": "Dad", "skin_tone": "medium", "hair_color": "dark brown",
    "body_type": "average", "height": "tall", "description": "green sweater",
}]
CARTOON = [{"name": "Lily", "description": "a toddler in a yellow shirt"}]


def _assemble(scene=SCENE, photoreal=PHOTOREAL, cartoon=CARTOON,
              style="2D flat vector cartoon (pastel)"):
    return assemble_mixed_media_prompt(scene, photoreal, cartoon, style)


def test_boilerplate_opener_and_closers_present_verbatim():
    prompt = _assemble()
    assert prompt.startswith("A mixed media children's book illustration collage.")
    assert "Clean lines, pastel colors for the background, collage art style." in prompt
    assert prompt.endswith("No text or words in the image.")


def test_photoreal_sentence_uses_scene_action():
    prompt = _assemble()
    assert (
        "In the center, a photorealistic, high-resolution photograph of "
        "Dad pushing Lily on the swing, both laughing." in prompt
    )


def test_contrast_sentence_names_both_character_sets():
    prompt = _assemble()
    assert (
        "There is a distinct, sharp contrast between the photographic real Dad "
        "and the completely 2D cartoon world and cartoon Lily." in prompt
    )


def test_contrast_sentence_with_two_photoreal_characters():
    prompt = _assemble(photoreal=[{"name": "Dad"}, {"name": "Mom"}], cartoon=[])
    assert (
        "the photographic real Dad and Mom and the completely 2D cartoon world."
        in prompt
    )


def test_contrast_sentence_without_cartoon_characters():
    prompt = _assemble(cartoon=[])
    assert "and the completely 2D cartoon world." in prompt
    assert "cartoon world and cartoon" not in prompt


def test_reference_instruction_present_and_enumerates_characters():
    prompt = _assemble()
    assert "Use the attached character reference images" in prompt
    assert "reference 1 is Dad" in prompt
    assert "reference 2 is Lily" in prompt


def test_reference_enumeration_photoreal_before_cartoon():
    prompt = _assemble(
        photoreal=[{"name": "Dad"}, {"name": "Mom"}],
        cartoon=[{"name": "Lily"}],
    )
    assert "reference 1 is Dad" in prompt
    assert "reference 2 is Mom" in prompt
    assert "reference 3 is Lily" in prompt


def test_empty_cartoon_elements_skipped():
    scene = dict(SCENE, cartoon_elements="")
    prompt = _assemble(scene=scene)
    assert "  " not in prompt  # no double spaces from a dropped empty sentence


def test_none_cartoon_elements_skipped():
    scene = dict(SCENE, cartoon_elements=None)  # JSON null from the LLM
    prompt = _assemble(scene=scene)
    assert "  " not in prompt
    assert "None" not in prompt


def test_background_uses_world_phrase():
    prompt = _assemble()
    assert (
        "The background is a purely 2D flat vector cartoon: "
        "a kids playground with beautiful trees and other cartoon children playing."
        in prompt
    )


def test_unknown_style_falls_back_to_default():
    prompt = _assemble(style="some future style")
    default = STYLE_PHRASES[DEFAULT_STYLE]
    assert default["world_phrase"] in prompt
    assert default["style_closer"] in prompt


@pytest.mark.parametrize("style_key", list(STYLE_PHRASES.keys()))
def test_every_style_produces_its_phrases(style_key):
    prompt = _assemble(style=style_key)
    assert STYLE_PHRASES[style_key]["world_phrase"] in prompt
    assert STYLE_PHRASES[style_key]["style_closer"] in prompt


def test_trailing_periods_in_inputs_do_not_double_up():
    scene = dict(SCENE, photoreal_action=SCENE["photoreal_action"] + ".")
    prompt = _assemble(scene=scene)
    assert ".." not in prompt
