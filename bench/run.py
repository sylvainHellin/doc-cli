#!/usr/bin/env python
"""Reusable OCR benchmark harness.

Runs a set of input files through a set of engines, recording per-page latency
and output length, and saving each engine's markdown side by side under
bench/results/<timestamp>/ for manual quality comparison. Intended first use:
RapidOCR vs GLM-OCR on the same scanned pages.

Usage:
    uv run python bench/run.py --files a.pdf img.png --engines rapidocr glm
    uv run python bench/run.py --files scan.pdf --engines rapidocr gemini --json

Each engine's output is written to results/<ts>/<engine>/<input-stem>.md and a
summary.json records latency and length. No quality scoring is done here; open
the markdown files side by side to compare.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from doc_cli.config import Config
from doc_cli.engines import EngineUnavailable
from doc_cli.pipeline import ocr_files

REPO_ROOT = Path(__file__).resolve().parent
RESULTS_ROOT = REPO_ROOT / "results"


def run_one(file: Path, engine: str, config: Config) -> dict:
    """OCR a single file with one engine, timing it. Returns a record."""
    start = time.perf_counter()
    error = None
    markdown = ""
    pages = 0
    try:
        result = ocr_files([file], engine, config)
        markdown = result["markdown"]
        pages = len(result.get("pages", [])) or 1
    except (EngineUnavailable, Exception) as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
    elapsed = time.perf_counter() - start
    return {
        "file": str(file),
        "engine": engine,
        "seconds": round(elapsed, 3),
        "pages": pages,
        "seconds_per_page": round(elapsed / pages, 3) if pages else None,
        "output_chars": len(markdown),
        "error": error,
        "markdown": markdown,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OCR engine benchmark")
    parser.add_argument("--files", nargs="+", required=True, help="input files (pdf/image)")
    parser.add_argument("--engines", nargs="+", required=True, help="engine names")
    parser.add_argument("--json", action="store_true", help="print summary as JSON")
    args = parser.parse_args(argv)

    config = Config.load()
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = RESULTS_ROOT / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    summary: list[dict] = []
    for engine in args.engines:
        engine_dir = out_dir / engine
        engine_dir.mkdir(exist_ok=True)
        for file_str in args.files:
            file = Path(file_str)
            record = run_one(file, engine, config)
            (engine_dir / f"{file.stem}.md").write_text(
                record.pop("markdown"), encoding="utf-8"
            )
            summary.append(record)
            status = record["error"] or f"{record['output_chars']} chars in {record['seconds']}s"
            print(f"[{engine}] {file.name}: {status}")

    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nresults saved under {out_dir}")
    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
