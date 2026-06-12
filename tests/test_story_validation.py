import pytest

from story_generator import _validate_story


def _classic_story():
    return {
        "title": "A Day Out",
        "scenes": [
            {"scene_number": n, "text": "Some text.", "image_prompt": "A prompt."}
            for n in range(1, 6)
        ],
    }


def _mixed_story():
    return {
        "title": "A Day Out",
        "scenes": [
            {
                "scene_number": n,
                "text": "Some text.",
                "photoreal_action": "Dad waving",
                "cartoon_elements": "a cartoon toddler",
                "background": "a playground",
            }
            for n in range(1, 6)
        ],
    }


def test_classic_story_valid():
    _validate_story(_classic_story(), mixed_media=False)


def test_mixed_story_valid():
    _validate_story(_mixed_story(), mixed_media=True)


def test_missing_title_rejected():
    story = _classic_story()
    del story["title"]
    with pytest.raises(AssertionError):
        _validate_story(story, mixed_media=False)


def test_wrong_scene_count_rejected():
    story = _classic_story()
    story["scenes"] = story["scenes"][:4]
    with pytest.raises(AssertionError):
        _validate_story(story, mixed_media=False)


def test_classic_scene_missing_image_prompt_rejected():
    story = _classic_story()
    del story["scenes"][2]["image_prompt"]
    with pytest.raises(AssertionError):
        _validate_story(story, mixed_media=False)


def test_mixed_scene_missing_photoreal_action_rejected():
    story = _mixed_story()
    del story["scenes"][0]["photoreal_action"]
    with pytest.raises(AssertionError):
        _validate_story(story, mixed_media=True)


def test_mixed_scene_empty_background_rejected():
    story = _mixed_story()
    story["scenes"][4]["background"] = "  "
    with pytest.raises(AssertionError):
        _validate_story(story, mixed_media=True)


def test_mixed_scene_empty_cartoon_elements_allowed():
    story = _mixed_story()
    story["scenes"][1]["cartoon_elements"] = ""
    _validate_story(story, mixed_media=True)


def test_mixed_scene_null_photoreal_action_rejected():
    story = _mixed_story()
    story["scenes"][0]["photoreal_action"] = None  # JSON null from the LLM
    with pytest.raises(AssertionError):
        _validate_story(story, mixed_media=True)


def test_mixed_scene_null_cartoon_elements_allowed():
    story = _mixed_story()
    story["scenes"][2]["cartoon_elements"] = None  # JSON null from the LLM
    _validate_story(story, mixed_media=True)
