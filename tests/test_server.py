"""Server: MU envelope base64 round-trip and plain /ocr, against rapidocr."""

from __future__ import annotations

import base64

import pytest

from doc_cli.config import Config
from doc_cli.server import build_app

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient


def _client():
    return TestClient(build_app(Config(), engine_name="rapidocr"))


def test_health():
    resp = _client().get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_mu_envelope_roundtrip(text_image_bytes):
    """POST the MU envelope with a base64 image, expect COMPLETED + markdown."""
    b64 = base64.b64encode(text_image_bytes).decode("ascii")
    resp = _client().post("/runsync", json={"input": {"file_content": b64, "filename": "x.png"}})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "COMPLETED"
    assert "HELLO" in data["output"]["markdown"].upper()


def test_mu_root_path(text_image_bytes):
    b64 = base64.b64encode(text_image_bytes).decode("ascii")
    resp = _client().post("/", json={"input": {"file_content": b64, "filename": "x.png"}})
    assert resp.json()["status"] == "COMPLETED"


def test_mu_missing_content():
    resp = _client().post("/runsync", json={"input": {}})
    assert resp.status_code == 400


def test_plain_ocr_json(text_image_bytes):
    b64 = base64.b64encode(text_image_bytes).decode("ascii")
    resp = _client().post("/ocr", json={"file_content": b64, "filename": "x.png"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["engine"] == "rapidocr"
    assert "HELLO" in data["markdown"].upper()


def test_plain_ocr_multipart(text_image):
    with open(text_image, "rb") as fh:
        resp = _client().post("/ocr", files={"file": ("x.png", fh, "image/png")})
    assert resp.status_code == 200
    assert "HELLO" in resp.json()["markdown"].upper()
