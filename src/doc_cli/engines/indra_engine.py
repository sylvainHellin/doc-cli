"""Indra OCR engine (datalab-to/indra-ocr): local CPU OCR with markdown output.

Indra detects lines, recognizes them with a 1M-parameter CTC model and orders
them into markdown with headings, paragraphs and HTML tables, on ONNX Runtime.
It is opt-in (``--engine indra``) and never chosen by ``auto``.

doc-cli only hands Indra the page images pdf-inspector flagged for OCR, so the
engine always runs Indra's OCR path and never reads a PDF text layer itself.
Two settings follow the 2026-10-19 benchmark:

- Page headers and footers are kept (Indra's ``--keep-furniture``); Indra's
  default drops them, which removed the sender, address and date of a letter.
- Indra's orientation model is off by default (``indra_auto_rotate``), since it
  turned an upright mixed-orientation page by 270 degrees and lost half of it
  (1.1.2 still does, and flips an upright floor plan by 180).
  Rendered PDF pages already honour the page /Rotate entry.

The models (about 76 MB since 1.1) download from Hugging Face on first use and are cached
by huggingface_hub; ``INDRA_OCR_MODEL_DIR`` points at a local copy instead.
The code is Apache-2.0, the weights are OpenRAIL-M (modified): free for research
and for companies under 20M USD revenue and funding, not for products that
compete with Datalab.
"""

from __future__ import annotations

from .base import EngineUnavailable, OcrEngine, OcrResult


class IndraEngine(OcrEngine):
    name = "indra"
    structured = True

    def __init__(self, config) -> None:
        super().__init__(config)
        self._converter = None

    def check(self) -> None:
        try:
            import indra_ocr  # noqa: F401
        except ImportError as exc:
            raise EngineUnavailable(
                "indra-ocr is not installed; install the [indra] extra "
                "(uv sync --extra indra)"
            ) from exc

    def _threads(self) -> int:
        threads = self.config.indra_threads
        if threads and threads > 0:
            return threads
        from indra_ocr import usable_cores

        return usable_cores()

    def _load(self):
        """Load the models once per engine instance; every page reuses them."""
        if self._converter is None:
            self.check()
            import indra_ocr
            from indra_ocr import ModelError

            try:
                self._converter = indra_ocr.load(
                    threads=self._threads(), mode="ocr", furniture=True
                )
            except (ModelError, FileNotFoundError) as exc:
                raise EngineUnavailable(f"Indra OCR models unavailable: {exc}") from exc
        return self._converter

    @staticmethod
    def _to_gray(image: bytes):
        """Decode an encoded page image into the grayscale array Indra reads."""
        import cv2
        import numpy as np

        gray = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_GRAYSCALE)
        if gray is None:
            raise ValueError("indra: could not decode the page image")
        return np.ascontiguousarray(gray)

    @staticmethod
    def page_markdown(page) -> str:
        """Indra's markdown for a page, or its plain lines when it has none."""
        return page.markdown if page.markdown is not None else page.text

    def ocr(self, images: list[bytes]) -> OcrResult:
        converter = self._load()
        turn = bool(self.config.indra_auto_rotate)
        pages: list[str] = []
        for image in images:
            page = converter.ocr(self._to_gray(image), turn=turn)
            pages.append(self.page_markdown(page).strip())
        markdown = "\n\n".join(pages)
        return OcrResult(
            markdown=markdown, pages=pages, engine=self.name, structured=True
        )
