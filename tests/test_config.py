"""Config loading: defaults, file override, unknown-key tolerance."""

from __future__ import annotations

import json

from doc_cli.config import Config


def test_defaults():
    cfg = Config()
    assert cfg.default_engine == "auto"
    assert cfg.gemini_model == "gemini-3.5-flash-lite"
    assert cfg.mistral_model == "mistral-ocr-4-0"
    assert cfg.spill_threshold == 30_000


def test_load_override(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"default_engine": "gemini", "ollama_url": "http://x:1", "unknown": 1})
    )
    monkeypatch.setenv("DOC_CONFIG", str(path))
    cfg = Config.load()
    assert cfg.default_engine == "gemini"
    assert cfg.ollama_url == "http://x:1"
    # Unknown keys are ignored for typed fields but preserved in raw.
    assert cfg.raw["unknown"] == 1


def test_load_missing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("DOC_CONFIG", str(tmp_path / "nope.json"))
    cfg = Config.load()
    assert cfg.default_engine == "auto"
