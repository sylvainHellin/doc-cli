"""Integration: pdf-inspector classify/parse and rapidocr on a rendered image."""

from __future__ import annotations

from pathlib import Path

import pypdfium2 as pdfium
import pytest

from doc_cli import pdf, pipeline
from doc_cli.config import Config
from doc_cli.engines.base import OcrEngine, OcrResult
from doc_cli.engines.mistral_engine import MistralEngine
from doc_cli.engines.rapidocr_engine import RapidOcrEngine
from doc_cli.pipeline import _run_pdf_ocr, kind_of, ocr_files, parse


def test_kind_of(text_pdf, text_image):
    assert kind_of(text_pdf) == "pdf"
    assert kind_of(text_image) == "image"
    assert kind_of("x.docx") == "office"


def test_classify_text_pdf(text_pdf):
    report = pdf.classify(text_pdf)
    assert report.page_count == 1
    # A born-digital text PDF should need no OCR.
    assert report.pages_needing_ocr == []


def test_parse_text_pdf_no_ocr(text_pdf, config):
    result = parse(text_pdf, "rapidocr", config)
    assert result["kind"] == "pdf"
    assert "doc-cli" in result["markdown"] or "Hello" in result["markdown"]
    # No OCR engine should have been invoked for a text PDF.
    assert result["engine"] is None
    assert result["pages_needing_ocr"] == []


def test_rapidocr_on_image(text_image_bytes, config):
    result = RapidOcrEngine(config).ocr([text_image_bytes])
    assert result.engine == "rapidocr"
    assert not result.structured
    # RapidOCR should recover the text (allow OCR noise; check a substring).
    assert "HELLO" in result.markdown.upper()


def test_ocr_files_image(text_image, config):
    result = ocr_files([text_image], "rapidocr", config)
    assert result["engine"] == "rapidocr"
    assert "HELLO" in result["markdown"].upper()


# --- Mistral native-PDF path (offline) -----------------------------------


def _make_pdf(tmp_path: Path, n: int) -> Path:
    """A born-digital n-page PDF via reportlab."""
    from reportlab.pdfgen import canvas

    path = tmp_path / f"doc{n}.pdf"
    c = canvas.Canvas(str(path))
    for i in range(n):
        c.drawString(72, 720, f"Page {i}")
        c.showPage()
    c.save()
    return path


def _page_count(pdf_bytes: bytes) -> int:
    doc = pdfium.PdfDocument(pdf_bytes)
    try:
        return len(doc)
    finally:
        doc.close()


class _RecordingMistral(MistralEngine):
    """Mistral engine that records calls instead of hitting the network."""

    def __init__(self, config, pages):
        super().__init__(config)
        self._pages = pages
        self.pdf_calls: list[bytes] = []
        self.image_calls: list[list[bytes]] = []

    def check(self) -> None:  # skip the API-key requirement offline
        pass

    def ocr_pdf(self, pdf_bytes: bytes) -> OcrResult:
        self.pdf_calls.append(pdf_bytes)
        return OcrResult(
            markdown="\n\n".join(self._pages),
            pages=list(self._pages),
            engine=self.name,
            structured=True,
        )

    def ocr(self, images):  # must never be reached on the native path
        self.image_calls.append(list(images))
        raise AssertionError("image path used for a Mistral PDF")


class _RecordingImageEngine(OcrEngine):
    """Non-Mistral engine that records the rendered images it receives."""

    name = "rapidocr"

    def __init__(self, config, pages):
        super().__init__(config)
        self._pages = pages
        self.image_calls: list[list[bytes]] = []

    def ocr(self, images) -> OcrResult:
        self.image_calls.append(list(images))
        return OcrResult(
            markdown="\n\n".join(self._pages),
            pages=list(self._pages),
            engine=self.name,
        )


def test_subset_pdf_selects_pages(tmp_path):
    path = _make_pdf(tmp_path, 4)
    sub = pdf.subset_pdf(path, [0, 2])
    assert _page_count(sub) == 2


def test_run_pdf_ocr_mistral_subset(tmp_path, config):
    path = _make_pdf(tmp_path, 3)
    eng = _RecordingMistral(config, ["OCR0", "OCR2"])
    result = _run_pdf_ocr(eng, path, [0, 2], page_count=3)
    # Native PDF call, not the image path.
    assert eng.image_calls == []
    assert len(eng.pdf_calls) == 1
    # A sub-PDF of exactly the two OCR pages was sent (not the whole 3-page doc).
    assert _page_count(eng.pdf_calls[0]) == 2
    assert result.pages == ["OCR0", "OCR2"]


def test_run_pdf_ocr_mistral_all_pages(tmp_path, config):
    path = _make_pdf(tmp_path, 2)
    eng = _RecordingMistral(config, ["A", "B"])
    _run_pdf_ocr(eng, path, [0, 1], page_count=2)
    # Whole PDF sent verbatim when every page needs OCR (no subsetting).
    assert eng.pdf_calls[0] == path.read_bytes()


def test_run_pdf_ocr_non_mistral_rasterizes(tmp_path, config):
    path = _make_pdf(tmp_path, 3)
    eng = _RecordingImageEngine(config, ["x", "y"])
    _run_pdf_ocr(eng, path, [0, 2], page_count=3)
    # Image engines receive one rendered image per OCR page.
    assert len(eng.image_calls) == 1
    assert len(eng.image_calls[0]) == 2
    assert all(img[:8] == b"\x89PNG\r\n\x1a\n" for img in eng.image_calls[0])


def test_ocr_files_mistral_pdf_native(tmp_path, monkeypatch):
    """`doc ocr` on a PDF with Mistral sends the whole PDF, never rasterizes."""
    path = _make_pdf(tmp_path, 3)
    eng = _RecordingMistral(Config(), ["A", "B", "C"])
    monkeypatch.setattr(pipeline, "get_engine", lambda name, cfg: eng)
    monkeypatch.setattr(
        pipeline.pdf,
        "render_pages",
        lambda *a, **k: pytest.fail("render_pages called on Mistral PDF path"),
    )
    result = ocr_files([path], "mistral", Config())
    # Native PDF call, no image path.
    assert eng.image_calls == []
    assert len(eng.pdf_calls) == 1
    # Whole PDF sent verbatim (all pages), no subsetting.
    assert eng.pdf_calls[0] == path.read_bytes()
    assert _page_count(eng.pdf_calls[0]) == 3
    assert result["engine"] == "mistral"
    assert result["structured"] is True
    assert result["markdown"] == "A\n\nB\n\nC"
    assert result["pages"] == ["A", "B", "C"]


def test_ocr_files_non_mistral_pdf_rasterizes(tmp_path, monkeypatch):
    """Other engines keep the rendered-image path for a PDF."""
    path = _make_pdf(tmp_path, 2)
    eng = _RecordingImageEngine(Config(), ["p0", "p1"])
    real_render = pdf.render_pages
    calls = {"n": 0}

    def spy(p, indices, *a, **k):
        calls["n"] += 1
        return real_render(p, indices, *a, **k)

    monkeypatch.setattr(pipeline, "get_engine", lambda name, cfg: eng)
    monkeypatch.setattr(pipeline.pdf, "render_pages", spy)
    result = ocr_files([path], "rapidocr", Config())
    assert calls["n"] == 1
    assert len(eng.image_calls) == 1
    assert len(eng.image_calls[0]) == 2
    assert all(img[:8] == b"\x89PNG\r\n\x1a\n" for img in eng.image_calls[0])
    assert result["engine"] == "rapidocr"
    assert result["markdown"] == "p0\n\np1"


def test_parse_pdf_mistral_splices(tmp_path, monkeypatch):
    """OCR markdown is spliced back into born-digital pages at the right index."""
    path = _make_pdf(tmp_path, 3)
    pages = [
        pdf.PdfPage(index=0, markdown="", needs_ocr=True, ocr_reason="scan"),
        pdf.PdfPage(index=1, markdown="MID", needs_ocr=False, ocr_reason=None),
        pdf.PdfPage(index=2, markdown="", needs_ocr=True, ocr_reason="scan"),
    ]
    eng = _RecordingMistral(Config(), ["OCR0", "OCR2"])
    monkeypatch.setattr(pipeline.pdf, "extract_pages", lambda p: pages)
    monkeypatch.setattr(pipeline, "get_engine", lambda name, cfg: eng)
    # Rasterization must not happen on the native PDF path.
    monkeypatch.setattr(
        pipeline.pdf,
        "render_pages",
        lambda *a, **k: pytest.fail("render_pages called on Mistral PDF path"),
    )

    result = parse(path, "mistral", Config())
    assert result["engine"] == "mistral"
    assert result["pages_needing_ocr"] == [0, 2]
    assert result["markdown"] == "OCR0\n\nMID\n\nOCR2"
    assert _page_count(eng.pdf_calls[0]) == 2
