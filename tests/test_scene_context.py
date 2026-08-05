import io

from PIL import Image

from image_generator import generate_all_images


def _png_bytes(color, size=(200, 200)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


class RecordingProvider:
    """Records the context_images passed on each call; returns a valid PNG so the
    caption overlay and the sliding-window re-reads work."""

    def __init__(self):
        self.calls = []

    def generate_image(self, prompt, context_images, model):
        self.calls.append(list(context_images))
        return _png_bytes((0, 200, 0))


def _story():
    return {
        "title": "T",
        "scenes": [
            {"scene_number": n, "text": f"Scene {n} text", "image_prompt": f"prompt {n}"}
            for n in range(1, 6)
        ],
    }


# Sliding window sizes per scene: 0, 1, 2, 2, 2
EXPECTED_WINDOW = [0, 1, 2, 2, 2]


def test_references_prepended_and_window_sizes(tmp_path):
    refs_dir = tmp_path / "refs"
    refs_dir.mkdir()
    ref1 = refs_dir / "photoreal_1.png"
    ref2 = refs_dir / "cartoon_1.png"
    ref1.write_bytes(_png_bytes((200, 0, 0)))
    ref2.write_bytes(_png_bytes((0, 0, 200)))
    ref_bytes = [ref1.read_bytes(), ref2.read_bytes()]

    provider = RecordingProvider()
    generate_all_images(
        _story(), str(tmp_path), provider, "m",
        reference_paths=[str(ref1), str(ref2)],
    )

    for i, call in enumerate(provider.calls):
        # references come FIRST and unchanged, then the sliding window
        assert call[0] == ref_bytes[0]
        assert call[1] == ref_bytes[1]
        assert len(call) == 2 + EXPECTED_WINDOW[i]


def test_classic_mode_without_references_is_window_only(tmp_path):
    provider = RecordingProvider()
    generate_all_images(_story(), str(tmp_path), provider, "m")  # reference_paths default
    for i, call in enumerate(provider.calls):
        assert len(call) == EXPECTED_WINDOW[i]
