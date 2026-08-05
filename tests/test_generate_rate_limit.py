"""Integration test for the SEC-2 interim rate limit on /generate.

Deliberately does NOT use the shared `client` fixture from conftest.py:
that fixture sets app.config["TESTING"] = True, which /generate treats as
"skip rate limiting" specifically so the rest of the suite — which posts
to /generate many times across many test files sharing one Flask app
instance — doesn't become flaky from accumulated hits. This file turns
TESTING back off to exercise the real enforcement path, and restores it
afterward via monkeypatch.setitem so a failure can't leak broken state
into later tests.
"""
import app as app_module
from rate_limit import RateLimiter


def _fake_story(**kwargs):
    return {
        "title": "T",
        "scenes": [{"scene_number": n, "text": "t", "image_prompt": "p"} for n in range(1, 6)],
    }


def _fake_images(story, output_dir, provider, model, reference_paths=None):
    return [f"{output_dir}/scene_{n}.png" for n in range(1, 6)]


def test_generate_returns_429_when_rate_limit_exceeded(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(app_module, "generate_story", _fake_story)
    monkeypatch.setattr(app_module, "generate_all_images", _fake_images)
    monkeypatch.setattr(app_module, "_generate_limiter", RateLimiter(limit=1, window_seconds=60))
    monkeypatch.setitem(app_module.app.config, "TESTING", False)
    client = app_module.app.test_client()

    payload = {
        "keywords": "x", "characters": "Mia", "setting": "y",
        "provider": "google", "image_model": "gemini-2.5-flash-image",
    }
    first = client.post("/generate", json=payload)
    second = client.post("/generate", json=payload)

    assert first.status_code == 200
    assert second.status_code == 429


def test_generate_rate_limit_is_skipped_under_testing_config(monkeypatch, tmp_path):
    # This is the behavior every other /generate test in the suite relies
    # on implicitly via the shared `client` fixture (TESTING=True).
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(app_module, "generate_story", _fake_story)
    monkeypatch.setattr(app_module, "generate_all_images", _fake_images)
    monkeypatch.setattr(app_module, "_generate_limiter", RateLimiter(limit=1, window_seconds=60))
    monkeypatch.setitem(app_module.app.config, "TESTING", True)
    client = app_module.app.test_client()

    payload = {
        "keywords": "x", "characters": "Mia", "setting": "y",
        "provider": "google", "image_model": "gemini-2.5-flash-image",
    }
    first = client.post("/generate", json=payload)
    second = client.post("/generate", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
