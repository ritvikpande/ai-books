from model_routing import model_for_step


def test_photoreal_reference_always_uses_image_model():
    # The face-bearing step is where Pro quality is validated — never
    # overridden by scene_image_model, even when one is given.
    assert model_for_step("photoreal_reference", "pro", "flash") == "pro"
    assert model_for_step("photoreal_reference", "pro", None) == "pro"


def test_cartoon_reference_uses_scene_image_model_when_given():
    assert model_for_step("cartoon_reference", "pro", "flash") == "flash"


def test_scene_uses_scene_image_model_when_given():
    assert model_for_step("scene", "pro", "flash") == "flash"


def test_cartoon_reference_falls_back_to_image_model_when_not_given():
    assert model_for_step("cartoon_reference", "pro", None) == "pro"
    assert model_for_step("cartoon_reference", "pro", "") == "pro"


def test_scene_falls_back_to_image_model_when_not_given():
    assert model_for_step("scene", "pro", None) == "pro"
    assert model_for_step("scene", "pro", "") == "pro"
