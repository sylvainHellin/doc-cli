"""Routing pipeline: office -> anydoc, PDF -> pdf-inspector (+OCR), image -> OCR."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import office, pdf
from .config import Config
from .engines import get_engine

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


def _parse_pdf(path: Path, engine_name: str, config: Config) -> dict[str, Any]:
    pages = pdf.extract_pages(path)
    ocr_indices = [p.index for p in pages if p.needs_ocr]
    engine_used = None
    if ocr_indices:
        images_by_index = pdf.render_pages(path, ocr_indices)
        engine = get_engine(engine_name, config)
        engine.check()
        ordered = [images_by_index[i] for i in ocr_indices]
        result = engine.ocr(ordered)
        engine_used = result.engine
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
