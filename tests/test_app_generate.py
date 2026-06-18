import pytest

import app as app_module


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def _story():
    return {
        "title": "T",
        "scenes": [
            {"scene_number": n, "text": "t", "image_prompt": "p"} for n in range(1, 6)
        ],
    }


# --- index renders the structured-character UI ------------------------------

def test_index_renders_character_ui(client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    for token in ("photorealCharacterList", "cartoonCharacterList",
                  "addPhotorealBtn", "addCartoonBtn", "proHint",
                  "field-photo-input", "/upload_photo",
                  "referencesContainer", "renderReferences"):
        assert token in body


# --- _normalize_characters (pure) -------------------------------------------

def test_normalize_drops_empty_and_trims():
    out = app_module._normalize_characters([
        {"name": "  Dad  ", "hair_color": "brown"},
        {"name": "", "description": "   "},   # fully empty -> dropped
        "not-a-dict",                          # ignored
    ])
    assert out == [{"name": "Dad", "skin_tone": "", "hair_color": "brown",
                    "body_type": "", "height": "", "description": "", "photo_path": ""}]


def test_normalize_non_list_returns_empty():
    assert app_module._normalize_characters(None) == []
    assert app_module._normalize_characters("Dad") == []


def test_normalize_carries_photo_path_through():
    out = app_module._normalize_characters([
        {"name": "Dad", "photo_path": "outputs/_uploads/abc123.png"},
    ])
    assert out == [{"name": "Dad", "skin_tone": "", "hair_color": "",
                    "body_type": "", "height": "", "description": "",
                    "photo_path": "outputs/_uploads/abc123.png"}]


def test_normalize_keeps_photo_only_character():
    out = app_module._normalize_characters([
        {"name": "", "photo_path": "outputs/_uploads/abc123.png"},
    ])
    assert len(out) == 1
    assert out[0]["photo_path"] == "outputs/_uploads/abc123.png"
    assert out[0]["name"] == ""


# --- validation -------------------------------------------------------------

def test_mixed_media_requires_a_photoreal_character(client):
    resp = client.post("/generate", json={
        "keywords": "playground", "setting": "a park", "mixed_media": True,
        "photoreal_characters": [], "cartoon_characters": [],
        "provider": "google", "image_model": "gemini-3-pro-image-preview",
    })
    assert resp.status_code == 400


def test_unknown_provider_returns_400(client):
    resp = client.post("/generate", json={
        "keywords": "x", "setting": "y", "mixed_media": True,
        "photoreal_characters": [{"name": "Dad"}], "provider": "openai",
    })
    assert resp.status_code == 400
    assert "openai" in resp.get_json()["error"]


def test_too_many_characters_returns_400(client):
    resp = client.post("/generate", json={
        "keywords": "x", "setting": "y", "mixed_media": True,
        "photoreal_characters": [{"name": f"C{i}"} for i in range(7)],
        "provider": "google", "image_model": "gemini-3-pro-image-preview",
    })
    assert resp.status_code == 400


# --- orchestration (monkeypatched generators, no API) -----------------------

def test_mixed_media_threads_arrays_and_reference_paths(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    captured = {}

    def fake_story(**kwargs):
        captured["story_kwargs"] = kwargs
        return _story()

    def fake_refs(photoreal, cartoon, art_style, output_dir, provider, model):
        captured["ref_call"] = (photoreal, cartoon, art_style, model)
        return [{"kind": "photoreal", "index": 1, "name": "Dad",
                 "path": f"{output_dir}/refs/photoreal_1.png"}]

    def fake_images(story, output_dir, provider, model, reference_paths=None):
        captured["reference_paths"] = reference_paths
        captured["story_has_refs"] = "character_refs" in story
        return [f"{output_dir}/scene_{n}.png" for n in range(1, 6)]

    monkeypatch.setattr(app_module, "generate_story", fake_story)
    monkeypatch.setattr(app_module, "generate_reference_images", fake_refs)
    monkeypatch.setattr(app_module, "generate_all_images", fake_images)

    resp = client.post("/generate", json={
        "keywords": "playground", "setting": "a park", "story_type": "adventure",
        "art_style": "2D flat vector cartoon (pastel)", "mixed_media": True,
        "photoreal_characters": [{"name": "Dad", "hair_color": "brown"}],
        "cartoon_characters": [{"name": "Lily"}],
        "provider": "google", "image_model": "gemini-3-pro-image-preview",
    })

    assert resp.status_code == 200
    pr = captured["story_kwargs"]["photoreal_characters"]
    assert isinstance(pr, list) and pr[0]["name"] == "Dad"
    assert captured["ref_call"][0][0]["name"] == "Dad"  # photoreal list reached refs
    assert len(captured["reference_paths"]) == 1
    assert captured["reference_paths"][0].endswith("photoreal_1.png")
    assert captured["story_has_refs"] is True


def test_classic_mode_does_not_generate_references(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    captured = {}

    monkeypatch.setattr(app_module, "generate_story", lambda **k: _story())

    def fake_images(story, output_dir, provider, model, reference_paths=None):
        captured["reference_paths"] = reference_paths
        return [f"{output_dir}/scene_{n}.png" for n in range(1, 6)]

    def boom(*a, **k):
        raise AssertionError("references must not be generated in classic mode")

    monkeypatch.setattr(app_module, "generate_all_images", fake_images)
    monkeypatch.setattr(app_module, "generate_reference_images", boom)

    resp = client.post("/generate", json={
        "keywords": "ice cream", "characters": "Mia", "setting": "a forest",
        "provider": "google", "image_model": "gemini-2.5-flash-image",
    })

    assert resp.status_code == 200
    assert captured["reference_paths"] is None
