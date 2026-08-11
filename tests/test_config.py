"""Config loading: defaults, file override, unknown-key tolerance."""

from __future__ import annotations

import json

import pytest

from doc_cli.config import Config, set_cloud_key


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


def test_set_cloud_key_writes_and_preserves(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"default_engine": "mistral"}))
    monkeypatch.setenv("DOC_CONFIG", str(path))
    written = set_cloud_key("mistral", "sk-secret")
    assert written == path
    data = json.loads(path.read_text())
    assert data["MISTRAL_API_KEY"] == "sk-secret"
    assert data["default_engine"] == "mistral"  # existing settings preserved
    assert path.stat().st_mode & 0o777 == 0o600  # secret file is owner-only
    # And Config.load surfaces it so the engine can read it.
    assert Config.load().raw["MISTRAL_API_KEY"] == "sk-secret"


def test_set_cloud_key_rejects_unknown_engine(tmp_path, monkeypatch):
    monkeypatch.setenv("DOC_CONFIG", str(tmp_path / "config.json"))
    with pytest.raises(ValueError):
        set_cloud_key("rapidocr", "x")
