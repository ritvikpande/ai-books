import pytest

from prompt_assembly import DEFAULT_STYLE, STYLE_PHRASES, assemble_mixed_media_prompt

SCENE = {
    "scene_number": 1,
    "text": "Dad and Lily go to the playground.",
    "photoreal_action": "a happy adult man (Dad) with short dark hair, jeans and a green sweater, walking breezily and holding hands",
    "cartoon_elements": "a flat 2D cartoon toddler in a yellow shirt holding Dad's hand",
    "background": "a kids playground with beautiful trees and other cartoon children playing",
}


def _assemble(scene=SCENE, photoreal="a happy adult man (Dad)", cartoon="a toddler",
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
        "a happy adult man (Dad) with short dark hair, jeans and a green sweater, "
        "walking breezily and holding hands." in prompt
    )


def test_contrast_sentence_names_both_character_sets():
    prompt = _assemble()
    assert (
        "There is a distinct, sharp contrast between the photographic real "
        "a happy adult man (Dad) and the completely 2D cartoon world and cartoon a toddler."
        in prompt
    )


def test_contrast_sentence_without_cartoon_characters():
    prompt = _assemble(cartoon="")
    assert "and the completely 2D cartoon world." in prompt
    assert "and cartoon ." not in prompt


def test_empty_cartoon_elements_skipped():
    scene = dict(SCENE, cartoon_elements="")
    prompt = _assemble(scene=scene)
    assert "  " not in prompt  # no double spaces from a dropped empty sentence


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
