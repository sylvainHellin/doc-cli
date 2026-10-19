#!/usr/bin/env python
"""Benchmark the Indra OCR CLI on the same inputs as bench/run.py.

Indra (datalab-to/indra-ocr) is not a doc-cli dependency, so this script shells
out to an `indra-ocr` binary installed in a separate, throwaway environment:

    uv venv /tmp/indra-venv && VIRTUAL_ENV=/tmp/indra-venv uv pip install indra-ocr
    uv run python bench/indra.py --indra-bin /tmp/indra-venv/bin/indra-ocr \
        --files bench/inputs/* --modes ocr auto --cores 8 16

For every (mode, cores) pair it runs one batch invocation over all files, so the
wall time includes process start and model load once, as a real bulk run would.
Each file's markdown goes to results/<ts>/indra-<mode>-c<cores>/<input-stem>.md,
next to the bench/run.py outputs, and summary-indra.json holds one record per
file (same keys as bench/run.py) plus one batch record with pages per second.
--loops N feeds the file list N times into the same batch, so a small input set
still measures steady-state throughput rather than model load.
`seconds` per file is Indra's own per-page `total_ms`, summed over the file's
pages; the batch wall time is the honest throughput figure.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
RESULTS_ROOT = REPO_ROOT / "results"


def run_batch(
    bin_path: str,
    files: list[Path],
    mode: str,
    cores: int,
    loops: int = 1,
    extra: list[str] | None = None,
) -> tuple[float, list[dict], str]:
    """Run one indra-ocr batch; return wall seconds, JSON page records, stderr."""
    cmd = [
        bin_path,
        *[str(f) for f in files] * loops,
        "--format", "json",
        "--mode", mode,
        "--cores", str(cores),
        "--timings",
        *(extra or []),
    ]
    start = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    wall = time.perf_counter() - start
    pages = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    if proc.returncode != 0:
        raise RuntimeError(f"indra-ocr exited {proc.returncode}: {proc.stderr[-2000:]}")
    return wall, pages, proc.stderr


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Indra OCR benchmark")
    parser.add_argument("--files", nargs="+", required=True, help="input files (pdf/image)")
    parser.add_argument(
        "--indra-bin",
        default=os.environ.get("INDRA_OCR_BIN") or shutil.which("indra-ocr") or "indra-ocr",
        help="path to the indra-ocr executable (default: $INDRA_OCR_BIN or PATH)",
    )
    parser.add_argument("--modes", nargs="+", default=["ocr"], choices=["auto", "ocr", "text"])
    parser.add_argument("--cores", nargs="+", type=int, default=[8])
    parser.add_argument("--repeat", type=int, default=1, help="batches per config; the fastest counts")
    parser.add_argument("--loops", type=int, default=1, help="feed the file list N times per batch")
    parser.add_argument(
        "--keep-furniture",
        action="store_true",
        help="pass --keep-furniture (keep page headers/footers); engine name gets a -kf suffix",
    )
    parser.add_argument("--out", type=Path, help="results dir (default: results/<timestamp>)")
    parser.add_argument("--json", action="store_true", help="print summary as JSON")
    args = parser.parse_args(argv)

    files = [Path(f).resolve() for f in args.files]
    out_dir = args.out or RESULTS_ROOT / datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    summary: list[dict] = []
    for mode in args.modes:
        for cores in args.cores:
            name = f"indra-{mode}-c{cores}" + ("-kf" if args.keep_furniture else "")
            extra = ["--keep-furniture"] if args.keep_furniture else []
            runs = [
                run_batch(args.indra_bin, files, mode, cores, args.loops, extra)
                for _ in range(args.repeat)
            ]
            walls = [r[0] for r in runs]
            wall, pages, _ = min(runs, key=lambda r: r[0])

            by_file: dict[str, dict[int, dict]] = defaultdict(dict)
            for page in pages:
                by_file[page["file"]].setdefault(page["page"], page)

            engine_dir = out_dir / name
            engine_dir.mkdir(exist_ok=True)
            stems = Counter(f.stem for f in files)
            for file in files:
                # a.png keeps a.md (matches bench/run.py); a.pdf next to it becomes a.pdf.md
                clash = stems[file.stem] > 1 and file.suffix.lower() == ".pdf"
                out_name = file.name if clash else file.stem
                recs = [p for _, p in sorted(by_file.get(str(file), {}).items())]
                markdown = "\n\n".join(p.get("markdown") or "" for p in recs)
                (engine_dir / f"{out_name}.md").write_text(markdown, encoding="utf-8")
                busy = sum(p.get("timings", {}).get("total_ms", 0.0) for p in recs) / 1000
                summary.append({
                    "file": str(file),
                    "engine": name,
                    "seconds": round(busy, 3),
                    "pages": len(recs),
                    "seconds_per_page": round(busy / len(recs), 3) if recs else None,
                    "output_chars": len(markdown),
                    "error": None if recs else "no pages returned",
                    "source": sorted({p.get("source", "?") for p in recs}),
                    "rotation": sorted({p.get("rotation", 0) for p in recs}),
                })

            n_pages = len(pages)
            batch = {
                "engine": name,
                "batch": True,
                "files": len(files),
                "loops": args.loops,
                "pages": n_pages,
                "wall_seconds": [round(w, 3) for w in walls],
                "pages_per_second": round(n_pages / wall, 2) if wall else None,
            }
            summary.append(batch)
            print(f"[{name}] {n_pages} pages, wall {[round(w, 2) for w in walls]}s, "
                  f"{batch['pages_per_second']} pages/s")

    # a reused --out dir accumulates configs; a rerun of the same config replaces its records
    summary_path = out_dir / "summary-indra.json"
    if summary_path.exists():
        done = {r["engine"] for r in summary}
        old = json.loads(summary_path.read_text(encoding="utf-8"))
        summary = [r for r in old if r["engine"] not in done] + summary
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nresults saved under {out_dir}")
    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
