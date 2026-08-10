"""CLI output helpers: JSON mode and spill-to-tempfile for oversized output."""

from __future__ import annotations

import json
import sys
import tempfile
from typing import Any


def spill_if_large(text: str, threshold: int) -> str | None:
    """Write text to a temp file if it exceeds threshold. Returns the path or None."""
    if len(text) <= threshold:
        return None
    fd, path = tempfile.mkstemp(prefix="doc-", suffix=".md")
    with open(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def emit(payload: dict[str, Any], *, as_json: bool, text_key: str, threshold: int) -> None:
    """Emit a result either as JSON or as human text.

    In text mode, the value at ``text_key`` is printed; if it exceeds
    ``threshold`` chars it is spilled to a temp file and the path is printed
    instead. In JSON mode the full payload is always printed (never spilled),
    so downstream tools receive complete structured data.
    """
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    text = payload.get(text_key, "")
    if not isinstance(text, str):
        text = str(text)
    spilled = spill_if_large(text, threshold)
    if spilled:
        print(f"[output {len(text)} chars spilled to] {spilled}", file=sys.stderr)
        print(spilled)
    else:
        print(text)
