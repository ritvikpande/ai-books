import pytest

from prompt_assembly import (
    compose_character_description,
    character_label,
    join_labels,
)

FULL = {
    "name": "Dad",
    "skin_tone": "medium",
    "hair_color": "dark brown",
    "body_type": "average",
    "height": "tall",
    "description": "short beard, green sweater, blue jeans",
}


# --- compose_character_description ------------------------------------------

def test_full_object_has_name_and_all_traits():
    out = compose_character_description(FULL)
    assert out.startswith("Dad:")
    for token in (
        "tall",
        "medium skin tone",
        "dark brown hair",
        "average build",
        "short beard, green sweater, blue jeans",
    ):
        assert token in out


def test_empty_fields_skipped_no_stray_punctuation():
    out = compose_character_description({"name": "Dad", "hair_color": "brown"})
    assert out == "Dad: brown hair"
    assert "  " not in out
    assert ",," not in out
    assert "with  " not in out


def test_unspecified_dropdown_values_are_skipped():
    out = compose_character_description({
        "name": "Mia",
        "skin_tone": "unspecified",
        "hair_color": "blonde",
        "body_type": "",
        "height": "unspecified",
        "description": "",
    })
    assert out == "Mia: blonde hair"


def test_empty_dict_returns_empty_string():
    assert compose_character_description({}) == ""


def test_name_only():
    assert compose_character_description({"name": "Dad"}) == "Dad"


def test_description_only_no_name():
    out = compose_character_description({"description": "a fluffy orange cat"})
    assert out == "a fluffy orange cat"


def test_traits_without_name_omit_label_colon():
    out = compose_character_description({"skin_tone": "tan", "hair_color": "black"})
    assert ":" not in out
    assert out == "tan skin tone, black hair"


def test_none_values_do_not_crash():
    out = compose_character_description({
        "name": None, "skin_tone": None, "hair_color": "red/ginger",
        "body_type": None, "height": None, "description": None,
    })
    assert out == "red/ginger hair"


# --- character_label --------------------------------------------------------

def test_character_label_prefers_name():
    assert character_label({"name": "Dad", "description": "a man"}) == "Dad"


def test_character_label_falls_back_to_description():
    assert character_label({"description": "a fluffy cat"}) == "a fluffy cat"


def test_character_label_generic_fallback():
    assert character_label({}) == "the character"


# --- join_labels ------------------------------------------------------------

def test_join_labels_empty():
    assert join_labels([]) == ""


def test_join_labels_single():
    assert join_labels([{"name": "Dad"}]) == "Dad"


def test_join_labels_two_uses_and():
    assert join_labels([{"name": "Dad"}, {"name": "Mom"}]) == "Dad and Mom"


def test_join_labels_three_uses_serial_and():
    out = join_labels([{"name": "Dad"}, {"name": "Mom"}, {"description": "a cat"}])
    assert out == "Dad, Mom and a cat"
