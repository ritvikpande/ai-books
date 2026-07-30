import io
import os

from PIL import Image

import app as app_module


def _image_bytes(fmt: str, size=(100, 100)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=(200, 50, 50)).save(buf, format=fmt)
    return buf.getvalue()


def test_valid_png_upload_returns_path(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    data = {"photo": (io.BytesIO(_image_bytes("PNG")), "me.png")}
    resp = client.post("/upload_photo", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    path = resp.get_json()["photo_path"]
    assert os.path.exists(path)
    assert path.endswith(".png")


def test_valid_jpeg_upload_converted_to_png(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    data = {"photo": (io.BytesIO(_image_bytes("JPEG")), "me.jpg")}
    resp = client.post("/upload_photo", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    path = resp.get_json()["photo_path"]
    assert path.endswith(".png")
    with Image.open(path) as img:
        assert img.format == "PNG"


def test_missing_photo_field_returns_400(client):
    resp = client.post("/upload_photo", data={}, content_type="multipart/form-data")
    assert resp.status_code == 400


def test_disallowed_extension_returns_400(client):
    data = {"photo": (io.BytesIO(b"not an image"), "me.gif")}
    resp = client.post("/upload_photo", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400


def test_corrupt_bytes_with_allowed_extension_returns_400(client):
    data = {"photo": (io.BytesIO(b"this is not a real png"), "me.png")}
    resp = client.post("/upload_photo", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400


def test_oversized_payload_returns_413(client):
    oversized = b"\x00" * (9 * 1024 * 1024)  # over the 8MB cap; never decoded
    data = {"photo": (io.BytesIO(oversized), "me.png")}
    resp = client.post("/upload_photo", data=data, content_type="multipart/form-data")
    assert resp.status_code == 413


def test_oversized_dimensions_capped(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    data = {"photo": (io.BytesIO(_image_bytes("PNG", size=(2000, 2000))), "big.png")}
    resp = client.post("/upload_photo", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    path = resp.get_json()["photo_path"]
    with Image.open(path) as img:
        assert img.size == (1536, 1536)
