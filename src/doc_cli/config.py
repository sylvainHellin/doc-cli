"""Configuration loading for doc-cli.

Config lives at ~/.config/doc/config.json (override with DOC_CONFIG).
All keys are optional; sane defaults are baked in. Secrets are read from the
environment (GEMINI_API_KEY, MISTRAL_API_KEY), never from the config file.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def config_path() -> Path:
    override = os.environ.get("DOC_CONFIG")
    if override:
        return Path(override).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base).expanduser() if base else Path.home() / ".config"
    return root / "doc" / "config.json"


@dataclass
class Config:
    # Engine selection: rapidocr | glm | gemini | mistral | auto
    default_engine: str = "auto"
    # Optional cloud engine to use when auto is asked to go to the cloud.
    default_cloud_engine: str = "gemini"
    # Ollama HTTP endpoint used by the GLM engine on Linux.
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "glm-ocr"
    # Cloud model ids (overridable, but defaults match the approved design).
    gemini_model: str = "gemini-3.5-flash-lite"
    mistral_model: str = "mistral-ocr-4-0"
    # MLX model id used by the GLM engine on macOS arm64.
    mlx_model: str = "mlx-community/GLM-OCR-bf16"
    # Threshold (chars) above which CLI output is spilled to a temp file.
    spill_threshold: int = 30_000
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls) -> "Config":
        path = config_path()
        data: dict[str, Any] = {}
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                raise SystemExit(f"failed to read config {path}: {exc}") from exc
        known = {f for f in cls.__dataclass_fields__ if f != "raw"}
        kwargs = {k: v for k, v in data.items() if k in known}
        cfg = cls(**kwargs)
        cfg.raw = data
        return cfg
