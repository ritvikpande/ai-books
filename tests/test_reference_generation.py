import os
import threading
import time

from image_generator import generate_reference_images

# Reference images are written verbatim (no caption), so the fake bytes need not
# be a valid PNG — nothing opens them in this path.
FAKE_PNG = b"\x89PNG\r\n\x1a\nFAKE-REFERENCE-DATA"

STYLE = "watercolor storybook illustration"


class FakeProvider:
    """Thread-safe: generate_reference_images calls this concurrently (PERF-7)."""

    def __init__(self):
        self.calls = []
        self._lock = threading.Lock()

    def generate_image(self, prompt, context_images, model):
        with self._lock:
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
    # Jobs run concurrently (PERF-7), so provider.calls isn't guaranteed to be
    # in submission order — find each prompt by content, not by index.
    prompts = [c["prompt"] for c in provider.calls]
    assert any("real person" in p for p in prompts)                           # photoreal
    assert any("2D watercolor storybook illustration" in p for p in prompts)  # cartoon


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


# --- PERF-7: concurrent reference generation ---------------------------------

class _IntervalRecordingProvider:
    """Records each call's [start, end) wall-clock window (thread-safe) so
    tests can prove calls actually overlapped in time, not just that the
    right number of calls happened."""

    def __init__(self, delay=0.05):
        self.delay = delay
        self.intervals = []
        self._lock = threading.Lock()

    def generate_image(self, prompt, context_images, model):
        start = time.monotonic()
        time.sleep(self.delay)
        end = time.monotonic()
        with self._lock:
            self.intervals.append((start, end))
        return FAKE_PNG


def _any_overlap(intervals) -> bool:
    for i in range(len(intervals)):
        for j in range(i + 1, len(intervals)):
            s1, e1 = intervals[i]
            s2, e2 = intervals[j]
            if s1 < e2 and s2 < e1:
                return True
    return False


def test_reference_images_generate_concurrently(tmp_path):
    provider = _IntervalRecordingProvider(delay=0.05)

    generate_reference_images(
        [{"name": "Dad"}, {"name": "Mom"}], [{"name": "Lily"}],
        STYLE, str(tmp_path), provider, "model-x",
    )

    assert len(provider.intervals) == 3
    assert _any_overlap(provider.intervals)


class _NameKeyedDelayProvider:
    """Delays by a name found in the prompt, so the first-submitted job can
    be made the slowest — proving returned order reflects submission order,
    not completion order."""

    def __init__(self, delays_by_name, default_delay=0.01):
        self.delays_by_name = delays_by_name
        self.default_delay = default_delay

    def generate_image(self, prompt, context_images, model):
        delay = next((d for name, d in self.delays_by_name.items() if name in prompt),
                     self.default_delay)
        time.sleep(delay)
        return FAKE_PNG


def test_reference_order_preserved_under_concurrency(tmp_path):
    # "Dad" is submitted first but finishes last; the reference-ordering
    # invariant (photoreal first, in list order) must hold regardless.
    provider = _NameKeyedDelayProvider({"Dad": 0.08, "Mom": 0.01, "Lily": 0.01})

    records = generate_reference_images(
        [{"name": "Dad"}, {"name": "Mom"}], [{"name": "Lily"}],
        STYLE, str(tmp_path), provider, "model-x",
    )

    assert [r["name"] for r in records] == ["Dad", "Mom", "Lily"]
    assert [r["kind"] for r in records] == ["photoreal", "photoreal", "cartoon"]


# --- Cost Lever #1 enabler: per-kind model routing ---------------------------

def test_cartoon_model_defaults_to_main_model_when_not_given(tmp_path):
    provider = FakeProvider()
    generate_reference_images(
        [{"name": "Dad"}], [{"name": "Lily"}], STYLE, str(tmp_path), provider, "pro-model",
    )
    assert all(c["model"] == "pro-model" for c in provider.calls)


def test_cartoon_model_overrides_only_cartoon_jobs(tmp_path):
    provider = FakeProvider()
    generate_reference_images(
        [{"name": "Dad"}], [{"name": "Lily"}], STYLE, str(tmp_path), provider, "pro-model",
        cartoon_model="flash-model",
    )
    photoreal_call = next(c for c in provider.calls if "real person" in c["prompt"])
    cartoon_call = next(c for c in provider.calls if "2D watercolor storybook illustration" in c["prompt"])
    assert photoreal_call["model"] == "pro-model"
    assert cartoon_call["model"] == "flash-model"
