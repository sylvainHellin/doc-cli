"""doc CLI: parse, inspect, ocr, serve."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import Config
from .engines import EngineUnavailable
from .engines.base import ENGINE_NAMES
from .output import emit

ENGINE_CHOICES = ("auto", *ENGINE_NAMES)


def _add_engine_flag(sp: argparse.ArgumentParser) -> None:
    sp.add_argument(
        "--engine",
        choices=ENGINE_CHOICES,
        default="auto",
        help="OCR engine (auto: rapidocr on Linux, glm on macOS)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="doc", description="Document to markdown CLI")
    parser.add_argument("--version", action="version", version=f"doc {__version__}")
    parser.add_argument("--json", action="store_true", help="emit structured JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    p_parse = sub.add_parser("parse", help="full pipeline: office/pdf/image -> markdown")
    p_parse.add_argument("file")
    _add_engine_flag(p_parse)

    p_inspect = sub.add_parser("inspect", help="pdf-inspector classification report")
    p_inspect.add_argument("file")

    p_ocr = sub.add_parser("ocr", help="force the OCR path over a file or image")
    p_ocr.add_argument("file", nargs="+")
    _add_engine_flag(p_ocr)

    p_serve = sub.add_parser("serve", help="run the OCR HTTP server")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8080)
    _add_engine_flag(p_serve)

    return parser


def cmd_parse(args, config: Config) -> int:
    from .pipeline import parse

    result = parse(args.file, args.engine, config)
    emit(result, as_json=args.json, text_key="markdown", threshold=config.spill_threshold)
    return 0


def cmd_inspect(args, config: Config) -> int:
    from .pdf import classify

    path = Path(args.file)
    if path.suffix.lower() != ".pdf":
        print(f"inspect expects a .pdf file, got {path.suffix or '(none)'}", file=sys.stderr)
        return 2
    report = classify(path)
    payload = {"file": str(path), **report.to_dict()}
    if args.json:
        emit(payload, as_json=True, text_key="", threshold=config.spill_threshold)
    else:
        lines = [
            f"file:              {payload['file']}",
            f"type:              {payload['pdf_type']}",
            f"pages:             {payload['page_count']}",
            f"confidence:        {payload['confidence']:.3f}",
            f"pages_needing_ocr: {payload['pages_needing_ocr']}",
        ]
        print("\n".join(lines))
    return 0


def cmd_ocr(args, config: Config) -> int:
    from .pipeline import ocr_files

    result = ocr_files([Path(f) for f in args.file], args.engine, config)
    emit(result, as_json=args.json, text_key="markdown", threshold=config.spill_threshold)
    return 0


def cmd_serve(args, config: Config) -> int:
    try:
        from .server import run
    except ImportError as exc:
        print(
            f"the server needs the [server] extra: uv sync --extra server ({exc})",
            file=sys.stderr,
        )
        return 2
    run(host=args.host, port=args.port, engine_name=args.engine, config=config)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = Config.load()
    handlers = {
        "parse": cmd_parse,
        "inspect": cmd_inspect,
        "ocr": cmd_ocr,
        "serve": cmd_serve,
    }
    try:
        return handlers[args.command](args, config)
    except EngineUnavailable as exc:
        print(f"engine unavailable: {exc}", file=sys.stderr)
        return 3
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
