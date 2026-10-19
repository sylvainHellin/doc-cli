"""doc CLI: parse, inspect, ocr, serve."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import CLOUD_KEY_NAMES, Config, set_cloud_key
from .engines import EngineUnavailable
from .engines.base import ENGINE_NAMES
from .output import OutputError, emit

ENGINE_CHOICES = ("auto", *ENGINE_NAMES)


def _add_engine_flag(sp: argparse.ArgumentParser) -> None:
    sp.add_argument(
        "--engine",
        choices=ENGINE_CHOICES,
        default="auto",
        help=(
            "OCR engine (auto: mistral if MISTRAL_API_KEY, else gemini if "
            "GEMINI_API_KEY, else local: rapidocr on Linux, glm on macOS; "
            "indra only when named)"
        ),
    )


def _add_output_flag(sp: argparse.ArgumentParser) -> None:
    sp.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        help=(
            "write the full output (Markdown, or JSON with --json) to FILE instead of "
            "stdout; creates parent dirs, overwrites, never spills; '-' = stdout"
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="doc", description="Document to markdown CLI")
    parser.add_argument("--version", action="version", version=f"doc {__version__}")
    parser.add_argument("--json", action="store_true", help="emit structured JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    p_parse = sub.add_parser("parse", help="full pipeline: office/pdf/image -> markdown")
    p_parse.add_argument("file")
    _add_engine_flag(p_parse)
    _add_output_flag(p_parse)

    p_inspect = sub.add_parser("inspect", help="pdf-inspector classification report")
    p_inspect.add_argument("file")

    p_ocr = sub.add_parser("ocr", help="force the OCR path over a file or image")
    p_ocr.add_argument("file", nargs="+")
    _add_engine_flag(p_ocr)
    _add_output_flag(p_ocr)

    p_serve = sub.add_parser("serve", help="run the OCR HTTP server")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8080)
    _add_engine_flag(p_serve)

    p_config = sub.add_parser("config", help="manage the config file")
    config_sub = p_config.add_subparsers(dest="config_command", required=True)
    p_set_key = config_sub.add_parser(
        "set-key", help="store a cloud API key in the config file (no env var needed)"
    )
    p_set_key.add_argument("engine", choices=sorted(CLOUD_KEY_NAMES))
    p_set_key.add_argument("key", help="the API key to store")

    return parser


def cmd_parse(args, config: Config) -> int:
    from .pipeline import parse

    result = parse(args.file, args.engine, config)
    emit(
        result,
        as_json=args.json,
        text_key="markdown",
        threshold=config.spill_threshold,
        output=args.output,
    )
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
    emit(
        result,
        as_json=args.json,
        text_key="markdown",
        threshold=config.spill_threshold,
        output=args.output,
    )
    return 0


def cmd_config(args, config: Config) -> int:
    if args.config_command == "set-key":
        path = set_cloud_key(args.engine, args.key)
        print(f"stored {CLOUD_KEY_NAMES[args.engine]} in {path}")
        return 0
    return 2


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
        "config": cmd_config,
    }
    try:
        return handlers[args.command](args, config)
    except EngineUnavailable as exc:
        print(f"engine unavailable: {exc}", file=sys.stderr)
        return 3
    except (FileNotFoundError, ValueError, OutputError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
