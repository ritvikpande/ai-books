"""Hybrid model routing (Cost Lever #1 enabler — see BookCostOptimization.md).

Infrastructure only, not a verified savings claim: lets the mixed-media
pipeline use a cheaper model for the cartoon reference and all scene
images while keeping the photoreal reference (the face-bearing step,
where Pro quality is validated) on the model the caller chose for it.
Whether the cheaper model actually holds up for face-anchored scenes is
an open question that needs a human to judge the output — this module
only resolves *which* model each step should use, given the caller's
choice; it makes no quality claim.
"""


def model_for_step(step: str, image_model: str, scene_image_model: str = None) -> str:
    """Resolve which image model a pipeline step should use.

    step: "photoreal_reference" | "cartoon_reference" | "scene"
    image_model: the model used for the photoreal reference — always
        returned for that step, regardless of scene_image_model.
    scene_image_model: optional override for "cartoon_reference" and
        "scene". Falsy (None or "") means "same as image_model" — i.e.
        today's single-model behavior, unchanged when this isn't set.
    """
    if step == "photoreal_reference":
        return image_model
    return scene_image_model or image_model
