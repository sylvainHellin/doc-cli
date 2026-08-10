"""Integration: pdf-inspector classify/parse and rapidocr on a rendered image."""

from __future__ import annotations

from doc_cli import pdf
from doc_cli.engines.rapidocr_engine import RapidOcrEngine
from doc_cli.pipeline import kind_of, ocr_files, parse


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
