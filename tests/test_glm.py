"""GLM engine: Ollama request shape and graceful unavailability (offline)."""

from __future__ import annotations

import base64

import httpx
import pytest

from doc_cli.config import Config
from doc_cli.engines import EngineUnavailable
from doc_cli.engines.glm_engine import GlmEngine


def test_ollama_unreachable_raises(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr(httpx, "post", boom)
    with pytest.raises(EngineUnavailable):
        GlmEngine(Config()).ocr([b"imgbytes"])


def test_ollama_request_and_parse(monkeypatch):
    captured = {}

    class FakeResp:
        status_code = 200

        def json(self):
            return {"response": "# ocr markdown"}

    def fake_post(url, json, timeout):  # noqa: A002
        captured["url"] = url
        captured["json"] = json
        return FakeResp()

    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr(httpx, "post", fake_post)
    result = GlmEngine(Config()).ocr([b"imgbytes"])
    assert result.markdown == "# ocr markdown"
    assert captured["url"].endswith("/api/generate")
    assert captured["json"]["model"] == "glm-ocr"
    assert base64.b64decode(captured["json"]["images"][0]) == b"imgbytes"
