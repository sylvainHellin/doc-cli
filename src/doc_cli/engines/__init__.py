"""OCR engines behind a single interface. See base.OcrEngine."""

from .base import EngineUnavailable, OcrEngine, OcrResult, get_engine, resolve_engine_name

__all__ = [
    "EngineUnavailable",
    "OcrEngine",
    "OcrResult",
    "get_engine",
    "resolve_engine_name",
]
