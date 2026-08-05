from story_generator import _describe_characters, MIXED_MEDIA_SYSTEM_PROMPT


def test_describe_characters_uses_composed_descriptions():
    lines = _describe_characters([
        {"name": "Dad", "hair_color": "brown"},
        {"name": "Mom"},
    ])
    assert lines == ["Dad: brown hair", "Mom"]


def test_describe_characters_handles_empty_and_none():
    assert _describe_characters([]) == []
    assert _describe_characters(None) == []


def test_describe_characters_drops_empty_objects():
    assert _describe_characters([{}, {"name": "Lily"}]) == ["Lily"]


def test_mixed_system_prompt_is_action_by_name_not_appearance():
    p = MIXED_MEDIA_SYSTEM_PROMPT
    assert "by name" in p.lower()
    assert "reference image" in p.lower()
    # the old "repeat the SAME physical details every scene" rule must be gone
    assert "SAME physical details" not in p
