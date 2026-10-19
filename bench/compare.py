#!/usr/bin/env python
"""Score engine outputs against a reference engine's outputs.

bench/run.py and bench/indra.py write one markdown file per input under
results/<ts>/<engine>/<stem>.md. This script lines them up by stem and scores
each engine against a reference engine (usually mistral), after stripping
markdown and HTML markup:

- word_f1: bag-of-words F1 against the reference (text fidelity, order-free).
- order: difflib ratio of the two word sequences (reading order on top of fidelity).
- per-feature counts of umlauts, ß, € and decimal-comma numbers (1.234,56),
  reported as engine/reference, so a dropped umlaut or a misread amount shows.

The reference is a proxy, not ground truth: read the page image for hard pages.

Usage:
    uv run python bench/compare.py --ref results/A/mistral \
        --dirs results/B/rapidocr results/C/indra-ocr-c8 [--csv out.csv]
"""

from __future__ import annotations

import argparse
import csv
import difflib
import html
import re
import sys
from collections import Counter
from pathlib import Path

FEATURES = {
    "umlaut": re.compile(r"[äöüÄÖÜ]"),
    "eszett": re.compile(r"ß"),
    "euro": re.compile(r"€|\bEUR\b"),
    "dec_comma": re.compile(r"\b\d{1,3}(?:\.\d{3})*,\d{2}\b"),
}


def plain(markdown: str) -> str:
    """Strip HTML tags, markdown markup and image links; keep the words."""
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", markdown)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[#*_|`>]+", " ", text)
    text = re.sub(r"-{3,}|:?-{2,}:?", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def words(text: str) -> list[str]:
    return re.findall(r"\w+(?:[.,/-]\w+)*|€", text)


def word_f1(hyp: list[str], ref: list[str]) -> float:
    if not hyp and not ref:
        return 1.0
    common = sum((Counter(hyp) & Counter(ref)).values())
    if not common:
        return 0.0
    p, r = common / len(hyp), common / len(ref)
    return 2 * p * r / (p + r)


def order_ratio(hyp: list[str], ref: list[str]) -> float:
    return difflib.SequenceMatcher(None, hyp, ref, autojunk=False).ratio()


def score(hyp_md: str, ref_md: str) -> dict:
    hyp_t, ref_t = plain(hyp_md), plain(ref_md)
    hyp_w, ref_w = words(hyp_t), words(ref_t)
    row = {
        "word_f1": round(word_f1(hyp_w, ref_w), 3),
        "order": round(order_ratio(hyp_w, ref_w), 3),
        "tables": hyp_md.count("<table") + len(re.findall(r"^\|.*\|\s*$\n^\|[ :|-]+\|", hyp_md, re.M)),
    }
    for name, rx in FEATURES.items():
        row[name] = f"{len(rx.findall(hyp_t))}/{len(rx.findall(ref_t))}"
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="score engine outputs against a reference")
    parser.add_argument("--ref", type=Path, required=True, help="reference engine dir")
    parser.add_argument("--dirs", type=Path, nargs="+", required=True, help="engine dirs to score")
    parser.add_argument("--csv", type=Path, help="write the table as CSV")
    args = parser.parse_args(argv)

    rows: list[dict] = []
    for ref_file in sorted(args.ref.glob("*.md")):
        ref_md = ref_file.read_text(encoding="utf-8")
        for d in [args.ref, *args.dirs]:
            hyp_file = d / ref_file.name
            if not hyp_file.exists():
                continue
            rows.append({
                "page": ref_file.stem,
                "engine": f"{d.parent.name}/{d.name}",
                **score(hyp_file.read_text(encoding="utf-8"), ref_md),
            })

    fields = list(rows[0]) if rows else []
    writer = csv.DictWriter(
        args.csv.open("w", newline="", encoding="utf-8") if args.csv else sys.stdout, fields
    )
    writer.writeheader()
    writer.writerows(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
