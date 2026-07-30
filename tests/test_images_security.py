import io
import json

import pytest
from PIL import Image

import app as app_module


def _valid_png_bytes(size=(2, 2), color=(10, 20, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="PNG")
    return buf.getvalue()


def _make_story_dir(tmp_path, story_id="story_20260101_000000"):
    story_dir = tmp_path / story_id
    story_dir.mkdir()
    (story_dir / "scene_1.png").write_bytes(_valid_png_bytes())
    refs_dir = story_dir / "refs"
    refs_dir.mkdir()
    (refs_dir / "photoreal_1.png").write_bytes(_valid_png_bytes())
    return story_dir


# --- /images: positive cases --------------------------------------------

def test_images_serves_valid_scene_asset(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    story_id = "story_20260101_000000"
    _make_story_dir(tmp_path, story_id)

    resp = client.get(f"/images/{story_id}/scene_1.png")

    assert resp.status_code == 200
    assert resp.data == _valid_png_bytes()


def test_images_serves_nested_ref_asset(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    story_id = "story_20260101_000000"
    _make_story_dir(tmp_path, story_id)

    resp = client.get(f"/images/{story_id}/refs/photoreal_1.png")

    assert resp.status_code == 200


# --- /images: negative cases ---------------------------------------------

def test_images_rejects_unknown_story_id(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    _make_story_dir(tmp_path)

    resp = client.get("/images/story_99999999_999999/scene_1.png")

    assert resp.status_code == 404


def test_images_rejects_story_id_not_matching_pattern(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    # A real directory under OUTPUT_DIR that just isn't a "story_*" id
    # (e.g. the _uploads dir) must never be reachable through this route.
    (tmp_path / "_uploads").mkdir()
    (tmp_path / "_uploads" / "secret.png").write_bytes(_valid_png_bytes())

    resp = client.get("/images/_uploads/secret.png")

    assert resp.status_code == 404


def test_images_rejects_traversal_via_filename(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    story_id = "story_20260101_000000"
    _make_story_dir(tmp_path, story_id)
    (tmp_path / "secret.txt").write_text("do not leak")

    resp = client.get(f"/images/{story_id}/../secret.txt")

    assert resp.status_code == 404


def test_images_rejects_reaching_a_sibling_story_dir(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    story_id = "story_20260101_000000"
    _make_story_dir(tmp_path, story_id)
    other_id = "story_20260101_000001"
    _make_story_dir(tmp_path, other_id)

    resp = client.get(f"/images/{story_id}/../{other_id}/scene_1.png")

    assert resp.status_code == 404


# Werkzeug's router normalizes a literal "//" in the URL itself (redirecting
# to the single-slash form) before any view code runs, so a leading-slash
# filename can't be reproduced through the HTTP layer alone. Test the guard
# directly against the resolver instead — this is the real code path that
# would matter if the helper were ever called from somewhere other than this
# one Flask route.
def test_resolve_story_asset_rejects_leading_slash(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    story_id = "story_20260101_000000"
    _make_story_dir(tmp_path, story_id)

    with pytest.raises(ValueError):
        app_module._resolve_story_asset(story_id, "/etc/passwd")


def test_resolve_story_asset_rejects_backslash(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    story_id = "story_20260101_000000"
    _make_story_dir(tmp_path, story_id)

    with pytest.raises(ValueError):
        app_module._resolve_story_asset(story_id, "..\\secret.txt")


def test_images_rejects_nonexistent_file_in_valid_story(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    story_id = "story_20260101_000000"
    _make_story_dir(tmp_path, story_id)

    resp = client.get(f"/images/{story_id}/scene_99.png")

    assert resp.status_code == 404


# --- /download_pdf: positive case ----------------------------------------

def test_download_pdf_builds_from_server_side_story_json(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    story_id = "story_20260101_000000"
    story_dir = _make_story_dir(tmp_path, story_id)
    story = {"title": "My Book", "scenes": [{"scene_number": 1}]}
    (story_dir / "story.json").write_text(json.dumps(story))

    resp = client.post("/download_pdf", json={
        "story_id": story_id,
        # attacker-supplied extras must be ignored entirely, not just unused
        "image_paths": ["C:/Windows/win.ini"],
        "story_title": "ignored-title",
        "story_dir": "C:/some/other/path",
    })

    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
    assert "My_Book" in resp.headers.get("Content-Disposition", "")


# --- /download_pdf: negative cases ----------------------------------------

def test_download_pdf_rejects_malformed_story_id(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))

    resp = client.post("/download_pdf", json={"story_id": "../../etc"})

    assert resp.status_code == 400


def test_download_pdf_rejects_unknown_story_id(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))

    resp = client.post("/download_pdf", json={"story_id": "story_99999999_999999"})

    assert resp.status_code == 400


def test_download_pdf_rejects_story_missing_story_json(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    story_id = "story_20260101_000000"
    _make_story_dir(tmp_path, story_id)  # no story.json written

    resp = client.post("/download_pdf", json={"story_id": story_id})

    assert resp.status_code == 400
