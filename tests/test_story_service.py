"""Direct unit tests of story_service, with no Flask/HTTP involved at all —
proves the extracted pipeline works standalone (ARCH-6)."""
import inspect
import json
import os
import threading
import time

import pytest

import story_service


class _RecordingFakes:
    """Stand-ins for generate_story/generate_reference_images/generate_all_images,
    recording their call arguments so tests can assert on what the service
    actually passed through."""

    def __init__(self):
        self.story_calls = []
        self.ref_calls = []
        self.ref_return = []
        self.image_calls = []

    def story_fn(self, **kwargs):
        self.story_calls.append(kwargs)
        return {
            "title": "T",
            "scenes": [{"scene_number": n, "text": "t", "image_prompt": "p"} for n in range(1, 6)],
        }

    def refs_fn(self, photoreal, cartoon, art_style, output_dir, provider, model):
        self.ref_calls.append({
            "photoreal": photoreal, "cartoon": cartoon,
            "art_style": art_style, "output_dir": output_dir, "model": model,
        })
        self.ref_return = [
            {
                "kind": "photoreal", "index": i, "name": char.get("name", ""),
                "path": os.path.join(output_dir, "refs", f"photoreal_{i}.png"),
                "from_photo": False, "upload_path": None,
            }
            for i, char in enumerate(photoreal, start=1)
        ]
        return self.ref_return

    def images_fn(self, story, output_dir, provider, model, reference_paths=None):
        self.image_calls.append({
            "output_dir": output_dir, "model": model, "reference_paths": reference_paths,
        })
        return [os.path.join(output_dir, f"scene_{n}.png") for n in range(1, 6)]


# --- architectural constraint -------------------------------------------

def test_story_service_has_no_flask_import():
    # A substring check on the whole source would false-positive on this
    # module's own docstring, which explains the constraint in English —
    # check for an actual import statement instead.
    source = inspect.getsource(story_service)
    for line in source.splitlines():
        stripped = line.strip().lower()
        assert not stripped.startswith("import flask")
        assert not stripped.startswith("from flask")


# --- validate_inputs ------------------------------------------------------

def test_validate_inputs_mixed_media_requires_photoreal():
    with pytest.raises(story_service.GenerationError, match="photorealistic character"):
        story_service.validate_inputs(
            keywords="x", characters="", setting="y", mixed_media=True,
            photoreal_characters=[], cartoon_characters=[],
        )


def test_validate_inputs_mixed_media_too_many_characters():
    with pytest.raises(story_service.GenerationError, match="Too many characters"):
        story_service.validate_inputs(
            keywords="x", characters="", setting="y", mixed_media=True,
            photoreal_characters=[{"name": f"C{i}"} for i in range(7)],
            cartoon_characters=[],
        )


def test_validate_inputs_mixed_media_requires_keywords_and_setting():
    with pytest.raises(story_service.GenerationError, match="Keywords and Setting"):
        story_service.validate_inputs(
            keywords="", characters="", setting="", mixed_media=True,
            photoreal_characters=[{"name": "Dad"}], cartoon_characters=[],
        )


def test_validate_inputs_classic_requires_all_fields():
    with pytest.raises(story_service.GenerationError, match="Keywords, Characters, and Setting"):
        story_service.validate_inputs(
            keywords="x", characters="", setting="y", mixed_media=False,
            photoreal_characters=[], cartoon_characters=[],
        )


def test_validate_inputs_accepts_valid_mixed_media():
    story_service.validate_inputs(
        keywords="x", characters="", setting="y", mixed_media=True,
        photoreal_characters=[{"name": "Dad"}], cartoon_characters=[],
    )  # no exception


def test_validate_inputs_accepts_valid_classic():
    story_service.validate_inputs(
        keywords="x", characters="Mia", setting="y", mixed_media=False,
        photoreal_characters=[], cartoon_characters=[],
    )  # no exception


# --- generate_book ----------------------------------------------------------

def test_generate_book_classic_mode_skips_references(tmp_path):
    fakes = _RecordingFakes()

    result = story_service.generate_book(
        keywords="ice cream", characters="Mia", setting="a forest",
        story_type="adventure", art_style="watercolor storybook illustration",
        mixed_media=False,
        photoreal_characters=[], cartoon_characters=[],
        provider_id="google", image_model="gemini-2.5-flash-image",
        output_dir=str(tmp_path),
        generate_story_fn=fakes.story_fn,
        generate_reference_images_fn=fakes.refs_fn,
        generate_all_images_fn=fakes.images_fn,
    )

    assert len(fakes.ref_calls) == 0
    assert fakes.image_calls[0]["reference_paths"] is None
    assert "character_refs" not in result["story"]
    assert result["image_filenames"] == [f"scene_{n}.png" for n in range(1, 6)]
    assert result["story_id"].startswith("story_")
    assert result["message"] == "Success"


def test_generate_book_mixed_media_threads_reference_paths(tmp_path):
    fakes = _RecordingFakes()

    result = story_service.generate_book(
        keywords="playground", characters="", setting="a park",
        story_type="adventure", art_style="2D flat vector cartoon (pastel)",
        mixed_media=True,
        photoreal_characters=[{"name": "Dad"}],
        cartoon_characters=[{"name": "Lily"}],
        provider_id="google", image_model="gemini-3-pro-image-preview",
        output_dir=str(tmp_path),
        generate_story_fn=fakes.story_fn,
        generate_reference_images_fn=fakes.refs_fn,
        generate_all_images_fn=fakes.images_fn,
    )

    assert len(fakes.ref_calls) == 1
    assert fakes.ref_calls[0]["photoreal"][0]["name"] == "Dad"
    assert fakes.image_calls[0]["reference_paths"] == [r["path"] for r in fakes.ref_return]
    assert result["story"]["character_refs"][0]["filename"] == "refs/photoreal_1.png"
    assert result["story"]["character_refs"][0]["from_photo"] is False
    assert result["story"]["character_refs"][0]["upload_filename"] is None


def test_generate_book_computes_upload_filename_when_from_photo(tmp_path):
    fakes = _RecordingFakes()

    def refs_with_photo(photoreal, cartoon, art_style, output_dir, provider, model):
        fakes.ref_return = [{
            "kind": "photoreal", "index": 1, "name": "Dad",
            "path": os.path.join(output_dir, "refs", "photoreal_1.png"),
            "from_photo": True,
            "upload_path": os.path.join(output_dir, "refs", "photoreal_1_upload.png"),
        }]
        return fakes.ref_return

    result = story_service.generate_book(
        keywords="playground", characters="", setting="a park",
        story_type="adventure", art_style="2D flat vector cartoon (pastel)",
        mixed_media=True,
        photoreal_characters=[{"name": "Dad"}], cartoon_characters=[],
        provider_id="google", image_model="gemini-3-pro-image-preview",
        output_dir=str(tmp_path),
        generate_story_fn=fakes.story_fn,
        generate_reference_images_fn=refs_with_photo,
        generate_all_images_fn=fakes.images_fn,
    )

    ref = result["story"]["character_refs"][0]
    assert ref["from_photo"] is True
    assert ref["filename"] == "refs/photoreal_1.png"
    assert ref["upload_filename"] == "refs/photoreal_1_upload.png"


def test_generate_book_persists_story_json(tmp_path):
    fakes = _RecordingFakes()

    result = story_service.generate_book(
        keywords="x", characters="Mia", setting="y",
        story_type="adventure", art_style="watercolor storybook illustration",
        mixed_media=False,
        photoreal_characters=[], cartoon_characters=[],
        provider_id="google", image_model="gemini-2.5-flash-image",
        output_dir=str(tmp_path),
        generate_story_fn=fakes.story_fn,
        generate_reference_images_fn=fakes.refs_fn,
        generate_all_images_fn=fakes.images_fn,
    )

    story_json_path = os.path.join(str(tmp_path), result["story_id"], "story.json")
    assert os.path.isfile(story_json_path)
    with open(story_json_path) as f:
        saved = json.load(f)
    assert saved["title"] == "T"


# --- PERF-7: overlap story generation with reference generation -------------

def test_generate_book_overlaps_story_and_reference_generation(tmp_path):
    # Neither generation step needs the other's output (refs need only the
    # form characters; the story text doesn't depend on refs at all), so
    # they should run concurrently in mixed-media mode. Prove it by
    # recording each step's [start, end) window and asserting they overlap.
    intervals = []
    lock = threading.Lock()

    def slow_story_fn(**kwargs):
        start = time.monotonic()
        time.sleep(0.05)
        with lock:
            intervals.append(("story", start, time.monotonic()))
        return {
            "title": "T",
            "scenes": [{"scene_number": n, "text": "t", "image_prompt": "p"} for n in range(1, 6)],
        }

    def slow_refs_fn(photoreal, cartoon, art_style, output_dir, provider, model):
        start = time.monotonic()
        time.sleep(0.05)
        with lock:
            intervals.append(("refs", start, time.monotonic()))
        return [{
            "kind": "photoreal", "index": 1, "name": "Dad",
            "path": os.path.join(output_dir, "refs", "photoreal_1.png"),
            "from_photo": False, "upload_path": None,
        }]

    def images_fn(story, output_dir, provider, model, reference_paths=None):
        return [os.path.join(output_dir, f"scene_{n}.png") for n in range(1, 6)]

    story_service.generate_book(
        keywords="x", characters="", setting="y",
        story_type="adventure", art_style="2D flat vector cartoon (pastel)",
        mixed_media=True,
        photoreal_characters=[{"name": "Dad"}], cartoon_characters=[],
        provider_id="google", image_model="gemini-3-pro-image-preview",
        output_dir=str(tmp_path),
        generate_story_fn=slow_story_fn,
        generate_reference_images_fn=slow_refs_fn,
        generate_all_images_fn=images_fn,
    )

    assert len(intervals) == 2
    (_, s1, e1), (_, s2, e2) = intervals
    assert s1 < e2 and s2 < e1  # overlapping windows -> ran concurrently


def test_generate_book_classic_mode_does_not_overlap_anything(tmp_path):
    # Classic mode has no references to generate, so there's nothing to
    # overlap with — story generation should just run normally, unchanged.
    fakes = _RecordingFakes()

    result = story_service.generate_book(
        keywords="x", characters="Mia", setting="y",
        story_type="adventure", art_style="watercolor storybook illustration",
        mixed_media=False,
        photoreal_characters=[], cartoon_characters=[],
        provider_id="google", image_model="gemini-2.5-flash-image",
        output_dir=str(tmp_path),
        generate_story_fn=fakes.story_fn,
        generate_reference_images_fn=fakes.refs_fn,
        generate_all_images_fn=fakes.images_fn,
    )

    assert len(fakes.story_calls) == 1
    assert len(fakes.ref_calls) == 0
    assert result["story"]["title"] == "T"
