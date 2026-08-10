"""Routing pipeline: office -> anydoc, PDF -> pdf-inspector (+OCR), image -> OCR."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import office, pdf
from .config import Config
from .engines import get_engine
from .engines.base import OcrEngine, OcrResult

IMAGE_EXTENSIONS = frozenset(
    {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".gif"}
)


def _read_image_as_png(path: str | Path) -> bytes:
    """Load an image file and re-encode as PNG bytes for the OCR engines."""
    import io

    from PIL import Image

    with Image.open(path) as img:
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="PNG")
        return buf.getvalue()


def kind_of(path: str | Path) -> str:
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if office.is_office(path):
        return "office"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    return "unknown"


def parse(path: str | Path, engine_name: str, config: Config) -> dict[str, Any]:
    """Full pipeline. Returns {markdown, kind, engine, ...metadata}."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"no such file: {path}")

    kind = kind_of(path)
    if kind == "office":
        return {
            "markdown": office.to_markdown(path),
            "kind": "office",
            "engine": None,
            "file": str(path),
        }
    if kind == "image":
        return ocr_files([path], engine_name, config)
    if kind == "pdf":
        return _parse_pdf(path, engine_name, config)
    raise ValueError(f"unsupported file type: {path.suffix or '(none)'}")


def _run_pdf_ocr(
    engine: OcrEngine, path: Path, ocr_indices: list[int], page_count: int
) -> OcrResult:
    """OCR the pages that need it, using a native PDF call when the engine supports it.

    Mistral OCR accepts PDF input directly, so we skip rasterization: send the
    whole PDF when every page needs OCR, otherwise assemble a sub-PDF of just the
    ocr_indices (in order) so the returned per-page markdown lines up with them.
    Other engines take rendered page images as before.
    """
    from .engines.mistral_engine import MistralEngine

    if isinstance(engine, MistralEngine):
        if len(ocr_indices) == page_count:
            pdf_bytes = path.read_bytes()
        else:
            pdf_bytes = pdf.subset_pdf(path, ocr_indices)
        return engine.ocr_pdf(pdf_bytes)

    images_by_index = pdf.render_pages(path, ocr_indices)
    ordered = [images_by_index[i] for i in ocr_indices]
    return engine.ocr(ordered)


def _parse_pdf(path: Path, engine_name: str, config: Config) -> dict[str, Any]:
    pages = pdf.extract_pages(path)
    ocr_indices = [p.index for p in pages if p.needs_ocr]
    engine_used = None
    if ocr_indices:
        engine = get_engine(engine_name, config)
        engine.check()
        result = _run_pdf_ocr(engine, path, ocr_indices, len(pages))
        engine_used = result.engine
        # result.pages is aligned with ocr_indices order (sub-PDF page order).
        ocr_text = dict(zip(ocr_indices, result.pages))
        for p in pages:
            if p.needs_ocr:
                p.markdown = ocr_text.get(p.index, p.markdown)

    markdown = "\n\n".join(p.markdown for p in pages if p.markdown)
    return {
        "markdown": markdown,
        "kind": "pdf",
        "engine": engine_used,
        "file": str(path),
        "page_count": len(pages),
        "pages_needing_ocr": ocr_indices,
    }


def ocr_files(paths: list[Path], engine_name: str, config: Config) -> dict[str, Any]:
    """Force the OCR path over one or more image/PDF files."""
    images: list[bytes] = []
    for p in paths:
        p = Path(p)
        if p.suffix.lower() == ".pdf":
            page_count = pdf.classify(p).page_count
            rendered = pdf.render_pages(p, list(range(page_count)))
            images.extend(rendered[i] for i in range(page_count))
        else:
            images.append(_read_image_as_png(p))

    engine = get_engine(engine_name, config)
    engine.check()
    result = engine.ocr(images)
    return {
        "markdown": result.markdown,
        "kind": "ocr",
        "engine": result.engine,
        "structured": result.structured,
        "file": ",".join(str(p) for p in paths),
        "pages": result.pages,
    }
