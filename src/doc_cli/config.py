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
    # Ollama HTTP endpoint used by the GLM engine on Linux.
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "glm-ocr"
    # GLM-OCR context window: a page image tokenizes to ~4k vision tokens, so the
    # 4096 Ollama default leaves almost no room for the answer. Size it for image
    # + output. num_predict caps generation to bound latency and stop the small
    # quant's occasional degenerate repetition loops from running to the ceiling.
    ollama_num_ctx: int = 8192
    ollama_num_predict: int = 2048
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


# Maps the engine name a user types to the env var / config key holding its secret.
CLOUD_KEY_NAMES = {
    "mistral": "MISTRAL_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


def set_cloud_key(engine: str, key: str) -> Path:
    """Store a cloud API key in the config file, mirroring ``zot config set-key``.

    Merges into the existing config so other settings are preserved, writes with
    owner-only permissions since the file now holds a secret, and returns the
    path written. The environment still overrides this at read time.
    """
    env_name = CLOUD_KEY_NAMES.get(engine)
    if env_name is None:
        raise ValueError(f"unknown cloud engine: {engine} (expected one of {sorted(CLOUD_KEY_NAMES)})")
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise SystemExit(f"failed to read config {path}: {exc}") from exc
    data[env_name] = key
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path
