"""OcrEngine abstraction and engine selection.

Every engine implements one method, ``ocr(images) -> OcrResult``, taking a list
of page images (bytes, PNG/JPEG encoded) and returning markdown or plain text.
Engines that cannot run in the current environment raise ``EngineUnavailable``
from ``ocr`` (or from a lightweight ``check()``), never a bare import error.
"""

from __future__ import annotations

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


def resolve_engine_name(requested: str, config: "Config") -> str:
    """Resolve 'auto' to a concrete engine name based on platform and config.

    auto -> local engine for the platform (Linux: rapidocr, macOS: glm),
    unless the config names a cloud engine as the default, in which case that
    cloud engine is used. Cloud engines are only chosen when explicitly asked
    for or configured as default; auto never silently reaches the network.
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
