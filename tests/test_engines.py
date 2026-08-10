"""Engine selection and cloud request construction (offline, no live calls)."""

from __future__ import annotations

import base64
import json

import pytest

from doc_cli.config import Config
from doc_cli.engines import EngineUnavailable, resolve_engine_name
from doc_cli.engines.gemini_engine import GeminiEngine
from doc_cli.engines.mistral_engine import MistralEngine


def test_resolve_explicit():
    cfg = Config()
    assert resolve_engine_name("rapidocr", cfg) == "rapidocr"
    assert resolve_engine_name("gemini", cfg) == "gemini"


def test_resolve_auto_linux(monkeypatch):
    cfg = Config(default_engine="auto")
    monkeypatch.setattr("platform.system", lambda: "Linux")
    assert resolve_engine_name("auto", cfg) == "rapidocr"


def test_resolve_auto_macos(monkeypatch):
    cfg = Config(default_engine="auto")
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    assert resolve_engine_name("auto", cfg) == "glm"


def test_resolve_auto_config_cloud_default():
    cfg = Config(default_engine="gemini")
    assert resolve_engine_name("auto", cfg) == "gemini"


def test_resolve_unknown():
    with pytest.raises(ValueError):
        resolve_engine_name("nope", Config())


def test_gemini_request(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    eng = GeminiEngine(Config())
    url, headers, body = eng.build_request(b"\x89PNG-bytes", mime="image/png")
    assert url.endswith("models/gemini-3.5-flash-lite:generateContent")
    assert headers["x-goog-api-key"] == "test-key"
    part = body["contents"][0]["parts"][1]["inline_data"]
    assert part["mime_type"] == "image/png"
    assert base64.b64decode(part["data"]) == b"\x89PNG-bytes"


def test_gemini_requires_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(EngineUnavailable):
        GeminiEngine(Config()).check()


def test_gemini_parse_response():
    data = {"candidates": [{"content": {"parts": [{"text": "# Title"}, {"text": " body"}]}}]}
    assert GeminiEngine.parse_response(data) == "# Title body"


def test_mistral_image_request(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "sk-test")
    eng = MistralEngine(Config())
    url, headers, body = eng.build_image_request(b"imgbytes", mime="image/png")
    assert url.endswith("/v1/ocr")
    assert headers["Authorization"] == "Bearer sk-test"
    assert body["model"] == "mistral-ocr-4-0"
    assert body["document"]["type"] == "image_url"
    assert body["document"]["image_url"].startswith("data:image/png;base64,")


def test_mistral_pdf_request(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "sk-test")
    eng = MistralEngine(Config())
    url, headers, body = eng.build_pdf_request(b"%PDF-1.7")
    assert body["document"]["type"] == "document_url"
    assert body["document"]["document_url"].startswith("data:application/pdf;base64,")


def test_mistral_parse_response():
    data = {"pages": [{"markdown": "p1"}, {"markdown": "p2"}]}
    assert MistralEngine.parse_response(data) == ["p1", "p2"]


def test_mistral_requires_key(monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    with pytest.raises(EngineUnavailable):
        MistralEngine(Config()).check()
