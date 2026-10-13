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


def _clear_cloud_keys(monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


def test_resolve_auto_linux(monkeypatch):
    _clear_cloud_keys(monkeypatch)
    cfg = Config(default_engine="auto")
    monkeypatch.setattr("platform.system", lambda: "Linux")
    assert resolve_engine_name("auto", cfg) == "rapidocr"


def test_resolve_auto_macos(monkeypatch):
    _clear_cloud_keys(monkeypatch)
    cfg = Config(default_engine="auto")
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    assert resolve_engine_name("auto", cfg) == "glm"


def test_resolve_auto_prefers_mistral(monkeypatch):
    """With MISTRAL_API_KEY set, auto picks mistral over local and gemini."""
    _clear_cloud_keys(monkeypatch)
    monkeypatch.setenv("MISTRAL_API_KEY", "sk-test")
    monkeypatch.setenv("GEMINI_API_KEY", "g-test")
    monkeypatch.setattr("platform.system", lambda: "Linux")
    assert resolve_engine_name("auto", Config(default_engine="auto")) == "mistral"


def test_resolve_auto_falls_back_to_gemini(monkeypatch):
    """Only GEMINI_API_KEY set: auto picks gemini over the local engine."""
    _clear_cloud_keys(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "g-test")
    monkeypatch.setattr("platform.system", lambda: "Linux")
    assert resolve_engine_name("auto", Config(default_engine="auto")) == "gemini"


def test_resolve_auto_falls_back_to_local(monkeypatch):
    """No cloud key: auto stays on the local platform engine."""
    _clear_cloud_keys(monkeypatch)
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    assert resolve_engine_name("auto", Config(default_engine="auto")) == "glm"


def test_resolve_auto_key_from_config(monkeypatch):
    """A cloud key present only in config (not env) still drives auto."""
    _clear_cloud_keys(monkeypatch)
    cfg = Config(default_engine="auto")
    cfg.raw = {"MISTRAL_API_KEY": "sk-cfg"}
    monkeypatch.setattr("platform.system", lambda: "Linux")
    assert resolve_engine_name("auto", cfg) == "mistral"


def test_resolve_prefer_cloud_false_stays_local(monkeypatch):
    """Server path: cloud keys in env do not override the local engine."""
    _clear_cloud_keys(monkeypatch)
    monkeypatch.setenv("MISTRAL_API_KEY", "sk-test")
    monkeypatch.setattr("platform.system", lambda: "Linux")
    cfg = Config(default_engine="auto")
    assert resolve_engine_name("auto", cfg, prefer_cloud=False) == "rapidocr"


def test_resolve_prefer_cloud_false_honors_config_cloud(monkeypatch):
    """Server path: an explicit cloud default_engine is still honored."""
    _clear_cloud_keys(monkeypatch)
    cfg = Config(default_engine="mistral")
    assert resolve_engine_name("auto", cfg, prefer_cloud=False) == "mistral"


def test_resolve_explicit_overrides_cloud_keys(monkeypatch):
    """An explicit --engine wins even when a cloud key is set."""
    monkeypatch.setenv("MISTRAL_API_KEY", "sk-test")
    monkeypatch.setattr("platform.system", lambda: "Linux")
    assert resolve_engine_name("rapidocr", Config(default_engine="auto")) == "rapidocr"


def test_resolve_auto_config_cloud_default(monkeypatch):
    _clear_cloud_keys(monkeypatch)
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


def test_gemini_key_from_config(monkeypatch):
    """With no env var, the engine reads the key stored in the config file."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    cfg = Config()
    cfg.raw = {"GEMINI_API_KEY": "g-cfg"}
    eng = GeminiEngine(cfg)
    eng.check()  # no raise
    _, headers, _ = eng.build_request(b"png")
    assert headers["x-goog-api-key"] == "g-cfg"


def test_gemini_env_overrides_config(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g-env")
    cfg = Config()
    cfg.raw = {"GEMINI_API_KEY": "g-cfg"}
    _, headers, _ = GeminiEngine(cfg).build_request(b"png")
    assert headers["x-goog-api-key"] == "g-env"


def test_gemini_parse_response():
    data = {"candidates": [{"content": {"parts": [{"text": "# Title"}, {"text": " body"}]}}]}
    assert GeminiEngine.parse_response(data) == "# Title body"


def test_mistral_image_request(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "sk-test")
    eng = MistralEngine(Config())
    url, headers, body = eng.build_image_request(b"imgbytes", mime="image/png")
    assert url.endswith("/v1/ocr")
    assert headers["Authorization"] == "Bearer sk-test"
    assert body["model"] == "mistral-ocr-4-1"
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


def test_mistral_key_from_config(monkeypatch):
    """With no env var, the engine reads the key stored in the config file."""
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    cfg = Config()
    cfg.raw = {"MISTRAL_API_KEY": "sk-cfg"}
    eng = MistralEngine(cfg)
    eng.check()  # no raise
    _, headers, _ = eng.build_image_request(b"img")
    assert headers["Authorization"] == "Bearer sk-cfg"


def test_mistral_env_overrides_config(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "sk-env")
    cfg = Config()
    cfg.raw = {"MISTRAL_API_KEY": "sk-cfg"}
    _, headers, _ = MistralEngine(cfg).build_image_request(b"img")
    assert headers["Authorization"] == "Bearer sk-env"
