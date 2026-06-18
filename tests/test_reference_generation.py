import os

from image_generator import generate_reference_images

# Reference images are written verbatim (no caption), so the fake bytes need not
# be a valid PNG — nothing opens them in this path.
FAKE_PNG = b"\x89PNG\r\n\x1a\nFAKE-REFERENCE-DATA"

STYLE = "watercolor storybook illustration"


class FakeProvider:
    def __init__(self):
        self.calls = []

    def generate_image(self, prompt, context_images, model):
        self.calls.append({"prompt": prompt, "context_images": context_images, "model": model})
        return FAKE_PNG


def test_one_image_per_character_photoreal_then_cartoon(tmp_path):
    provider = FakeProvider()
    records = generate_reference_images(
        [{"name": "Dad"}, {"name": "Mom"}], [{"name": "Lily"}],
        STYLE, str(tmp_path), provider, "model-x",
    )
    assert [r["kind"] for r in records] == ["photoreal", "photoreal", "cartoon"]
    assert [r["name"] for r in records] == ["Dad", "Mom", "Lily"]
    assert [r["index"] for r in records] == [1, 2, 1]
    assert len(provider.calls) == 3


def test_saved_under_refs_dir(tmp_path):
    provider = FakeProvider()
    records = generate_reference_images(
        [{"name": "Dad"}], [], STYLE, str(tmp_path), provider, "m",
    )
    path = records[0]["path"]
    assert os.path.exists(path)
    assert os.path.basename(os.path.dirname(path)) == "refs"
    assert os.path.basename(path) == "photoreal_1.png"


def test_no_context_images_passed(tmp_path):
    provider = FakeProvider()
    records = generate_reference_images([{"name": "Dad"}], [], STYLE, str(tmp_path), provider, "m")
    assert provider.calls[0]["context_images"] == []
    assert records[0]["from_photo"] is False
    assert records[0]["upload_path"] is None


def test_cartoon_skipped_when_empty(tmp_path):
    provider = FakeProvider()
    records = generate_reference_images([{"name": "Dad"}], [], STYLE, str(tmp_path), provider, "m")
    assert all(r["kind"] == "photoreal" for r in records)
    assert len(provider.calls) == 1


def test_no_caption_burned_into_reference(tmp_path):
    provider = FakeProvider()
    records = generate_reference_images([{"name": "Dad"}], [], STYLE, str(tmp_path), provider, "m")
    with open(records[0]["path"], "rb") as f:
        assert f.read() == FAKE_PNG  # unchanged — no caption overlay


def test_prompt_routing_by_kind(tmp_path):
    provider = FakeProvider()
    generate_reference_images(
        [{"name": "Dad"}], [{"name": "Lily"}], STYLE, str(tmp_path), provider, "m",
    )
    assert "real person" in provider.calls[0]["prompt"]          # photoreal
    assert "2D watercolor storybook illustration" in provider.calls[1]["prompt"]  # cartoon


def test_photo_path_passed_as_context_images(tmp_path):
    photo_path = tmp_path / "upload.png"
    photo_path.write_bytes(b"FAKE-UPLOADED-PHOTO-BYTES")
    provider = FakeProvider()
    generate_reference_images(
        [{"name": "Dad", "photo_path": str(photo_path)}], [], STYLE, str(tmp_path), provider, "m",
    )
    assert provider.calls[0]["context_images"] == [b"FAKE-UPLOADED-PHOTO-BYTES"]


def test_photo_based_prompt_differs_from_no_photo(tmp_path):
    photo_path = tmp_path / "upload.png"
    photo_path.write_bytes(b"FAKE-UPLOADED-PHOTO-BYTES")
    provider = FakeProvider()
    generate_reference_images(
        [{"name": "Dad", "photo_path": str(photo_path)}], [], STYLE, str(tmp_path), provider, "m",
    )
    generate_reference_images([{"name": "Dad"}], [], STYLE, str(tmp_path), provider, "m")
    assert provider.calls[0]["prompt"] != provider.calls[1]["prompt"]
    assert "attached" in provider.calls[0]["prompt"].lower()


def test_upload_copy_saved_alongside_reference(tmp_path):
    photo_path = tmp_path / "upload.png"
    photo_path.write_bytes(b"FAKE-UPLOADED-PHOTO-BYTES")
    provider = FakeProvider()
    records = generate_reference_images(
        [{"name": "Dad", "photo_path": str(photo_path)}], [], STYLE, str(tmp_path), provider, "m",
    )
    refs_dir = os.path.dirname(records[0]["path"])
    upload_copy = os.path.join(refs_dir, "photoreal_1_upload.png")
    assert os.path.exists(upload_copy)
    with open(upload_copy, "rb") as f:
        assert f.read() == b"FAKE-UPLOADED-PHOTO-BYTES"
    # The copy's path is exposed on the record so the UI can show input vs output.
    assert records[0]["upload_path"] == upload_copy


def test_from_photo_field_in_records(tmp_path):
    photo_path = tmp_path / "upload.png"
    photo_path.write_bytes(b"FAKE-UPLOADED-PHOTO-BYTES")
    provider = FakeProvider()
    records = generate_reference_images(
        [{"name": "Dad", "photo_path": str(photo_path)}, {"name": "Mom"}], [],
        STYLE, str(tmp_path), provider, "m",
    )
    assert records[0]["from_photo"] is True
    assert records[1]["from_photo"] is False


def test_missing_photo_path_falls_back_to_no_context(tmp_path):
    provider = FakeProvider()
    records = generate_reference_images(
        [{"name": "Dad", "photo_path": str(tmp_path / "does_not_exist.png")}], [],
        STYLE, str(tmp_path), provider, "m",
    )
    assert provider.calls[0]["context_images"] == []
    assert records[0]["from_photo"] is False


def test_cartoon_character_with_photo_path_ignored(tmp_path):
    photo_path = tmp_path / "upload.png"
    photo_path.write_bytes(b"FAKE-UPLOADED-PHOTO-BYTES")
    provider = FakeProvider()
    records = generate_reference_images(
        [], [{"name": "Lily", "photo_path": str(photo_path)}],
        STYLE, str(tmp_path), provider, "m",
    )
    assert provider.calls[0]["context_images"] == []
    assert records[0]["from_photo"] is False
