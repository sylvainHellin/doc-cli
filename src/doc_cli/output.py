"""CLI output helpers: JSON mode, spill-to-tempfile and -o/--output file writes."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any


class OutputError(Exception):
    """Raised when the -o/--output target cannot be written."""


def spill_if_large(text: str, threshold: int) -> str | None:
    """Write text to a temp file if it exceeds threshold. Returns the path or None."""
    if len(text) <= threshold:
        return None
    fd, path = tempfile.mkstemp(prefix="doc-", suffix=".md")
    with open(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def render(payload: dict[str, Any], *, as_json: bool, text_key: str) -> str:
    """Render a payload as JSON or as the text at ``text_key``, without trailing newline."""
    if as_json:
        return json.dumps(payload, ensure_ascii=False, indent=2)
    text = payload.get(text_key, "")
    return text if isinstance(text, str) else str(text)


def write_output(content: str, path: str) -> None:
    """Write content to path (UTF-8, overwrite, parents created)."""
    target = Path(path).expanduser()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise OutputError(f"cannot write {path}: {exc.strerror or exc}") from exc


def emit(
    payload: dict[str, Any],
    *,
    as_json: bool,
    text_key: str,
    threshold: int,
    output: str | None = None,
) -> None:
    """Emit a result either as JSON or as human text.

    With ``output`` set to a path, the full rendered output is written there
    (never spilled) and a one-line note goes to stderr; ``output == "-"``
    prints the full output to stdout without spilling.

    Without ``output``, in text mode the value at ``text_key`` is printed; if
    it exceeds ``threshold`` chars it is spilled to a temp file and the path is
    printed instead. In JSON mode the full payload is always printed (never
    spilled), so downstream tools receive complete structured data.
    """
    text = render(payload, as_json=as_json, text_key=text_key)
    if output == "-":
        print(text)
        return
    if output is not None:
        write_output(text + "\n", output)
        print(f"wrote {len(text)} chars to {output}", file=sys.stderr)
        return
    if as_json:
        print(text)
        return
    spilled = spill_if_large(text, threshold)
    if spilled:
        print(f"[output {len(text)} chars spilled to] {spilled}", file=sys.stderr)
        print(spilled)
    else:
        print(text)
