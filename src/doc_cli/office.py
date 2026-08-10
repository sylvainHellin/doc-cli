"""Office-format handling via firecrawl-anydoc (import name: anydoc).

anydoc converts 14 office formats (docx, pptx, xlsx, odt, epub, rtf, csv, ...)
to GitHub-Flavored Markdown, detecting the format from file content. It also
handles born-digital PDFs, but the pipeline routes PDFs through pdf-inspector
instead so scanned pages can be flagged for OCR.
"""

from __future__ import annotations

from pathlib import Path

# Extensions anydoc handles. PDF is intentionally excluded here (routed to the
# pdf module). Detection is content-based; this set is only for routing.
OFFICE_EXTENSIONS = frozenset(
    {
        ".doc", ".docx", ".docm",
        ".ppt", ".pptx", ".pptm", ".pps", ".pot",
        ".xls", ".xlsx", ".xlsm", ".xlsb",
        ".odt", ".ods", ".odp",
        ".rtf", ".epub", ".csv",
    }
)


def is_office(path: str | Path) -> bool:
    return Path(path).suffix.lower() in OFFICE_EXTENSIONS


def to_markdown(path: str | Path) -> str:
    """Convert an office document to markdown."""
    import anydoc

    return anydoc.to_markdown(str(path))
