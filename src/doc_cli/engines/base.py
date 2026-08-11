"""OcrEngine abstraction and engine selection.

Every engine implements one method, ``ocr(images) -> OcrResult``, taking a list
of page images (bytes, PNG/JPEG encoded) and returning markdown or plain text.
Engines that cannot run in the current environment raise ``EngineUnavailable``
from ``ocr`` (or from a lightweight ``check()``), never a bare import error.
"""

from __future__ import annotations

import os
import platform
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from doc_cli.config import Config

ENGINE_NAMES = ("rapidocr", "glm", "gemini", "mistral")
CLOUD_ENGINES = frozenset({"gemini", "mistral"})


class EngineUnavailable(RuntimeError):
    """Raised when an engine cannot run here (missing dep, server, or key)."""


@dataclass
class OcrResult:
    """Result of an OCR run over one or more page images."""

    markdown: str
    # Per-page text, aligned with the input image order.
    pages: list[str] = field(default_factory=list)
    engine: str = ""
    # True when the engine emits structured markdown, False for plain text.
    structured: bool = False


class OcrEngine(ABC):
    name: str = ""
    # Whether this engine produces markdown structure (tables/headings) or
    # plain text lines. rapidocr is plain text; the VLM/cloud engines are markdown.
    structured: bool = False

    def __init__(self, config: "Config") -> None:
        self.config = config

    def check(self) -> None:
        """Raise EngineUnavailable if the engine cannot run. Default: no-op."""

    @abstractmethod
    def ocr(self, images: list[bytes]) -> OcrResult:
        """OCR a list of encoded page images into an OcrResult."""


def cloud_key(env_name: str, config: "Config") -> str | None:
    """Resolve a cloud API key from the environment, then the config file.

    The environment wins so a shell export always overrides a stored key, but a
    key written into ~/.config/doc/config.json (via ``doc config set-key``) is a
    valid home too, mirroring how ``zot`` stores its key. This lets a globally
    installed ``doc`` reach a cloud engine with nothing in the environment.
    """
    env = os.environ.get(env_name)
    if env:
        return env
    stored = config.raw.get(env_name)
    return stored if isinstance(stored, str) and stored else None


def _cloud_key_present(env_name: str, config: "Config") -> bool:
    """True if a cloud API key is available in the environment or config."""
    return cloud_key(env_name, config) is not None


def resolve_engine_name(
    requested: str, config: "Config", *, prefer_cloud: bool = True
) -> str:
    """Resolve 'auto' to a concrete engine name based on keys, platform, config.

    Precedence: an explicit ``requested`` engine wins, then a ``default_engine``
    named in the config. Otherwise ``auto`` resolves by cost-aware preference:
    Mistral OCR if MISTRAL_API_KEY is available, else Gemini if GEMINI_API_KEY
    is available, else the local engine for the platform (Linux: rapidocr,
    macOS: glm).

    ``prefer_cloud=False`` disables the cloud preference so ``auto`` stays local
    unless the config explicitly names a cloud ``default_engine``. The server
    uses this so that a stray cloud key in its environment never silently sends
    Firecrawl traffic to a paid endpoint.
    """
    if requested != "auto":
        if requested not in ENGINE_NAMES:
            raise ValueError(f"unknown engine: {requested}")
        return requested

    configured = config.default_engine
    if configured and configured != "auto":
        if configured not in ENGINE_NAMES:
            raise ValueError(f"unknown default_engine in config: {configured}")
        return configured

    if prefer_cloud:
        if _cloud_key_present("MISTRAL_API_KEY", config):
            return "mistral"
        if _cloud_key_present("GEMINI_API_KEY", config):
            return "gemini"

    system = platform.system()
    if system == "Darwin":
        return "glm"
    return "rapidocr"


def get_engine(name: str, config: "Config") -> OcrEngine:
    """Instantiate an engine by name (after resolving 'auto')."""
    resolved = resolve_engine_name(name, config)
    if resolved == "rapidocr":
        from .rapidocr_engine import RapidOcrEngine

        return RapidOcrEngine(config)
    if resolved == "glm":
        from .glm_engine import GlmEngine

        return GlmEngine(config)
    if resolved == "gemini":
        from .gemini_engine import GeminiEngine

        return GeminiEngine(config)
    if resolved == "mistral":
        from .mistral_engine import MistralEngine

        return MistralEngine(config)
    raise ValueError(f"unknown engine: {resolved}")
