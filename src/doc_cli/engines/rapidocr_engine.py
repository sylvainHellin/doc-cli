"""RapidOCR-ONNX engine: local CPU default on Linux.

RapidOCR (PP-OCRv6 default in v3.9.x) returns text lines with boxes and
confidences. It is not a layout/markdown parser, so we assemble the recognized
lines into plain text in reading order (top-to-bottom by box y) and emit that
without inventing markdown structure.
"""

from __future__ import annotations

import io

from .base import EngineUnavailable, OcrEngine, OcrResult


class RapidOcrEngine(OcrEngine):
    name = "rapidocr"
    structured = False

    def __init__(self, config) -> None:
        super().__init__(config)
        self._engine = None

    def check(self) -> None:
        try:
            import rapidocr  # noqa: F401
        except ImportError as exc:  # pragma: no cover - env dependent
            raise EngineUnavailable(
                "rapidocr is not installed; install the base dependencies"
            ) from exc

    def _load(self):
        if self._engine is None:
            self.check()
            from rapidocr import RapidOCR

            self._engine = RapidOCR()
        return self._engine

    @staticmethod
    def _to_ndarray(image: bytes):
        from PIL import Image
        import numpy as np

        with Image.open(io.BytesIO(image)) as img:
            return np.array(img.convert("RGB"))

    @staticmethod
    def _assemble(result) -> str:
        """Assemble RapidOCR output into plain text in top-to-bottom order."""
        txts = getattr(result, "txts", None)
        boxes = getattr(result, "boxes", None)
        if txts is None:
            return ""
        lines = list(txts)
        if boxes is not None and len(boxes) == len(lines):
            # Sort by the top y-coordinate of each quad box for reading order.
            order = sorted(
                range(len(lines)),
                key=lambda i: min(pt[1] for pt in boxes[i]),
            )
            lines = [lines[i] for i in order]
        return "\n".join(t for t in lines if t)

    def ocr(self, images: list[bytes]) -> OcrResult:
        engine = self._load()
        pages: list[str] = []
        for image in images:
            arr = self._to_ndarray(image)
            result = engine(arr)
            pages.append(self._assemble(result))
        markdown = "\n\n".join(pages)
        return OcrResult(
            markdown=markdown, pages=pages, engine=self.name, structured=False
        )
