"""PDF handling via pdf-inspector plus page rasterization via pypdfium2.

pdf-inspector classifies each page and extracts born-digital text pages to
markdown locally (no OCR). Scanned pages are flagged in ``pages_needing_ocr``
(0-indexed); we rasterize only those pages for the OCR engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class PdfInspection:
    pdf_type: str
    page_count: int
    confidence: float
    pages_needing_ocr: list[int]

    def to_dict(self) -> dict:
        return {
            "pdf_type": self.pdf_type,
            "page_count": self.page_count,
            "confidence": self.confidence,
            "pages_needing_ocr": self.pages_needing_ocr,
        }


@dataclass
class PdfPage:
    index: int  # 0-indexed page number
    markdown: str
    needs_ocr: bool
    ocr_reason: str | None


def classify(path: str | Path) -> PdfInspection:
    """Lightweight classification report for a PDF."""
    import pdf_inspector

    c = pdf_inspector.classify_pdf(str(path))
    return PdfInspection(
        pdf_type=str(c.pdf_type),
        page_count=int(c.page_count),
        confidence=float(c.confidence),
        pages_needing_ocr=list(c.pages_needing_ocr),
    )


def extract_pages(path: str | Path) -> list[PdfPage]:
    """Per-page markdown plus OCR-need metadata, in document order."""
    import pdf_inspector

    result = pdf_inspector.extract_pages_markdown(str(path))
    pages: list[PdfPage] = []
    for pm in result.pages:
        pages.append(
            PdfPage(
                index=int(pm.page),
                markdown=pm.markdown or "",
                needs_ocr=bool(pm.needs_ocr),
                ocr_reason=str(pm.ocr_reason) if pm.ocr_reason else None,
            )
        )
    return pages


def render_pages(path: str | Path, indices: list[int], scale: float = 2.5) -> dict[int, bytes]:
    """Rasterize the given 0-indexed pages to PNG bytes with pypdfium2.

    scale ~2.5 gives roughly 180 DPI, a reasonable OCR input resolution.
    """
    import io

    import pypdfium2 as pdfium

    out: dict[int, bytes] = {}
    doc = pdfium.PdfDocument(str(path))
    try:
        for i in indices:
            page = doc[i]
            bitmap = page.render(scale=scale)
            pil = bitmap.to_pil()
            buf = io.BytesIO()
            pil.save(buf, format="PNG")
            out[i] = buf.getvalue()
    finally:
        doc.close()
    return out
