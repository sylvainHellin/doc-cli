# doc-cli

A command-line tool that turns documents into Markdown.
Office formats and born-digital PDFs are parsed locally with no OCR.
Scanned pages and standalone images go through a pluggable OCR engine, local or cloud.

The CLI command is `doc`.

## Why Python

The house style is Rust, and this project is a deliberate exception.
The OCR ecosystem doc-cli depends on (RapidOCR-ONNX, GLM-OCR via mlx-vlm, the pdf-inspector and anydoc bindings) is Python-first, so the tool is uv-managed Python.

## Install

```
uv sync                 # core: office + pdf parsing + rapidocr
uv sync --extra server  # add the FastAPI OCR server (doc serve)
uv sync --extra mlx     # macOS arm64 only: GLM-OCR via mlx-vlm
uv sync --extra indra   # Indra OCR (opt-in local engine, --engine indra)
```

Run the CLI with `uv run doc ...`, or install the console script into a tool environment with `uv tool install .`.
To get the Indra engine in the installed `doc`, include the extra: `uv tool install --reinstall '.[indra]'`.

## Pipeline

Routing is by file type.

- Office formats (docx, pptx, xlsx, odt, epub, rtf, csv, ...) go to `firecrawl-anydoc` (`anydoc.to_markdown`), which detects the format from the file content and emits GitHub-Flavored Markdown.
- PDFs go to `pdf-inspector`, which classifies each page and extracts born-digital text pages to Markdown locally.
  Only the pages it flags in `pages_needing_ocr` are rasterized (via pypdfium2) and sent to the OCR engine, then spliced back into reading order.
- Standalone images go straight to the OCR engine.

## OCR engines

All engines implement one interface, `OcrEngine.ocr(images) -> OcrResult`.
An engine that cannot run in the current environment raises `EngineUnavailable` with a clear message rather than a stack trace.

| Engine | Where | Model | Output |
| --- | --- | --- | --- |
| `mistral` | Cloud, default when MISTRAL_API_KEY is set | `mistral-ocr-4-1`, native PDF input | Markdown |
| `gemini` | Cloud, free-tier fallback | `gemini-3.5-flash-lite` | Markdown |
| `rapidocr` | Local, CPU, offline fallback on Linux | RapidOCR-ONNX v3.9.x (PP-OCRv6) | Plain text lines assembled in reading order (no invented Markdown structure) |
| `glm` | Local, offline fallback on macOS arm64 (mlx-vlm) or Linux (Ollama HTTP) | GLM-OCR 0.9B (MIT) | Markdown |
| `indra` | Local, CPU, opt-in only (`[indra]` extra) | Indra OCR 1.1.x (datalab-to/indra-ocr); code Apache-2.0, weights OpenRAIL-M (modified): free for research and for companies under 20M USD revenue and funding, not for products competing with Datalab | Markdown with HTML tables |

RapidOCR is the fast classical path: sub-second per page on CPU, strong on plain text, no tables or math.
GLM-OCR is a small document VLM: higher-quality Markdown with tables and formulas, but slow on a CPU-only server, so on Linux it is opt-in and reached through an Ollama server you run yourself.
Indra is a 1M-parameter line recognizer with a layout and reading-order model: on typed German business documents it returns paragraphs, headings and one table row per price position at about 0.5 s per page on CPU, but it reads degraded scans and handwriting worse than Mistral.
In a benchmark of 18 pages on 2026-10-19 (8-core Ryzen 7 CPU, scripts in `bench/`), Indra reached a word F1 of 0.91 against Mistral on German pages (rapidocr 0.94, GLM-OCR 0.96) and 5.1 pages/s in an 8-core batch, against about 2 s per page for rapidocr and 2.5 s for Mistral.
It kept price tables one row per position with every amount right, but merged EUR/Ct columns on a degraded tax scan, lost a handwritten total, over-tabled form-like blocks, and rotated a mixed-orientation photo by 270 degrees.
Indra 1.1.2 (2026-10-26 re-run on the same pages, results in `bench/results/20261026-indra112/`) adds handwriting, 80+ scan languages and any-angle pages: German typed pages went from 0.910 to 0.918 word F1, a page with handwriting from 0.73 to 0.79 and the French carte grise front from 0.85 to 0.94, at the same batch speed.
No engine read a CAD floor plan: Indra returned empty tables, rapidocr only the title, and Mistral invented a title block.
doc-cli calls it only on the pages pdf-inspector flags for OCR, keeps page headers and footers (Indra drops them by default, letterheads included), and leaves Indra's orientation model off because it turned an upright mixed-orientation page by 270 degrees (1.1.2 still does, and also flips an upright floor plan by 180); set `"indra_auto_rotate": true` for scans that arrive sideways.
No model weights are downloaded during install; RapidOCR and Indra fetch their ONNX models on first use (Indra from Hugging Face, or from `INDRA_OCR_MODEL_DIR`), and the GLM backends require a server or the `mlx` extra you set up separately.

### Engine selection

```
doc parse file.pdf --engine rapidocr|glm|gemini|mistral|indra|auto
```

`auto` (the default) prefers cloud OCR, in cost order:

1. `mistral` (`mistral-ocr-4-1`) when `MISTRAL_API_KEY` is available.
2. `gemini` (`gemini-3.5-flash-lite`, free tier) when `GEMINI_API_KEY` is available.
3. The local engine for the platform otherwise: `rapidocr` on Linux, `glm` on macOS.

`auto` never picks `indra`; it runs only when named with `--engine indra` or `"default_engine": "indra"`.

An explicit `--engine` always wins, and a `default_engine` in the config file overrides the `auto` order.
So `--engine rapidocr` or `"default_engine": "rapidocr"` pins the local engine regardless of which keys are set.

Cloud OCR is the default because it is cheap enough that CPU-only local OCR is rarely worth the trouble.
Mistral OCR is priced at $4 per 1000 pages at the standard rate, and $2 per 1000 pages in batch mode, per Mistral pricing as of 2026-08.
The OCR endpoint (`POST /v1/ocr`) is billed at the standard rate.
Gemini stays as the free-tier cloud option, and the local engines stay as an offline fallback.

### Privacy

Cloud engines send page images (or, for Mistral, the native PDF) to a third-party API.
For sensitive documents, force a local engine so nothing leaves the machine:

```
doc parse confidential.pdf --engine rapidocr   # or --engine glm, --engine indra
```

Set `"default_engine": "rapidocr"` (or `"glm"`) in the config to make local the standing default and opt into cloud only per call.

### Cloud keys

A cloud engine needs its key, read from the environment first and from the config file as a fallback.

- `MISTRAL_API_KEY` for the `mistral` engine.
- `GEMINI_API_KEY` for the `gemini` engine.

With either key present, `auto` routes to that cloud engine, so providing the key is all it takes to switch on cloud OCR.

Two ways to provide it:

- Export it in the environment (`export MISTRAL_API_KEY=...`).
  This wins over a stored key and leaves nothing on disk.
- Store it once in the config file so a globally installed `doc` works with nothing exported, mirroring `zot config set-key`:

  ```
  doc config set-key mistral <key>
  doc config set-key gemini <key>
  ```

  This writes the key into `~/.config/doc/config.json` and tightens the file to owner-only (`0600`).
  The key sits there in plaintext, so keep that file out of any synced or version-controlled tree.

## Commands

```
doc parse <file> [-o FILE]                    # full pipeline (office/pdf/image), Markdown out
doc inspect <file.pdf>                        # pdf-inspector classification report
doc ocr <file|image>... [--engine] [-o FILE]  # force the OCR path
doc serve [--host] [--port]                   # run the OCR HTTP server (needs [server] extra)
```

Global flags (before the subcommand, e.g. `doc --json parse f.pdf`):

- `--json` emits a structured JSON payload instead of human text.

Subcommand flags (after `parse` or `ocr`, e.g. `doc parse f.pdf -o out.md`):

- `-o/--output FILE` writes the full output to FILE, JSON too with `--json`, creating parent directories and overwriting; `-` prints the full output to stdout.
- Without `-o`, text output larger than 30000 characters (configurable) is written to a temp file and the path is printed instead, so a large document never floods the terminal.
  Use `-o` rather than `>` to save a large document to a file.

## Configuration

Config lives at `~/.config/doc/config.json` (override with `DOC_CONFIG`).
Every setting below is optional and falls back to a default.
A cloud key may also live here (see Cloud keys above), written by `doc config set-key`, in which case the file is tightened to `0600`; the environment still overrides it.

```json
{
  "default_engine": "auto",
  "ollama_url": "http://localhost:11434",
  "ollama_model": "glm-ocr",
  "gemini_model": "gemini-3.5-flash-lite",
  "mistral_model": "mistral-ocr-4-1",
  "mlx_model": "mlx-community/GLM-OCR-bf16",
  "indra_threads": 0,
  "indra_auto_rotate": false,
  "spill_threshold": 30000
}
```

`indra_threads` set to 0 lets Indra use every core the process may run on.

## Server

`doc serve` runs a FastAPI app with two contracts.

1. Firecrawl RunPod-MU envelope, so doc-cli plugs into a self-hosted Firecrawl as its OCR backend.
   Firecrawl POSTs the URL in `PDF_MU_V2_BASE_URL` directly with `{"input": {"file_content": "<base64>", "filename": "x.pdf"}}` and expects `{"status": "COMPLETED", "output": {"markdown": "..."}}`.
   The envelope is served at both `POST /` and `POST /runsync`; point `PDF_MU_V2_BASE_URL` at whichever path you prefer.

2. A plain `POST /ocr` for direct use, accepting either a multipart file upload (`file` part) or a JSON body `{"file_content": "<base64>", "filename": "x.pdf"}`, and returning `{"markdown": ..., "engine": ..., "kind": ...}`.

`GET /health` reports liveness and the resolved engine.

### Server engine default stays local

Unlike the CLI, `doc serve` does not let `auto` reach for a cloud engine just because a key sits in the server's environment.
The server resolves `auto` to the local platform engine and only uses a cloud engine when you ask for one explicitly, either with `doc serve --engine mistral` or with `"default_engine": "mistral"` in the config.
This keeps a self-hosted Firecrawl backend from silently sending every document through a paid cloud OCR endpoint and running up a bill.

### On the PDF_OCR_BASE_URL contract

Firecrawl PRs [#3201](https://github.com/firecrawl/firecrawl/pull/3201) and [#3211](https://github.com/firecrawl/firecrawl/pull/3211) proposed a simpler self-hosted OCR contract using `PDF_OCR_BASE_URL` and `PDF_OCR_API_KEY`, returning `{markdown, html}` directly.
Both were closed without merging, so the canonical merged path is still the MinerU-style `PDF_MU_V2_*` envelope that doc-cli implements above.
If the `PDF_OCR_BASE_URL` contract later lands, the plain `POST /ocr` response here is close: it already returns `markdown`, and adding an `html` field rendered from it is the only change needed.

## Benchmarking

`bench/run.py` is a reusable harness for comparing engines on the same inputs.

```
uv run python bench/run.py --files scan.pdf page.png --engines rapidocr glm
```

It records per-page latency and output length, and writes each engine's Markdown side by side under `bench/results/<timestamp>/` for manual quality comparison.
No automatic quality scoring is done; open the outputs side by side.
The first intended use is a RapidOCR versus GLM-OCR comparison.

`bench/indra.py` runs the Indra OCR CLI (`indra-ocr`, from the `[indra]` extra or a throwaway environment) over the same inputs, per mode and core count, and writes its Markdown next to the other engines with batch pages per second.
`bench/compare.py` scores engine outputs against a reference engine (word F1, word-order ratio, and counts of umlauts, ß, € and decimal-comma amounts); the reference is a proxy, so read the page image for hard pages.

## Development

```
uv run pytest
```

The suite covers config loading, engine selection, cloud request construction (offline, no live calls), the GLM Ollama request shape, RapidOCR and Indra on a rendered image (the Indra test skips without the extra), the Indra engine options against a fake converter, pdf-inspector classification and parsing, and the server round-trip against RapidOCR.
Cloud engines are tested by asserting request construction only.

## Licensing

doc-cli is MIT.
Its parsing dependencies (pdf-inspector, anydoc, RapidOCR, GLM-OCR weights) are MIT or Apache-2.0.
The optional Indra OCR code is Apache-2.0, but its weights are OpenRAIL-M (modified), with the revenue and competition limits listed in the engine table.
