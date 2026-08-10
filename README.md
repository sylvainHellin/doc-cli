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
```

Run the CLI with `uv run doc ...`, or install the console script into a tool environment with `uv tool install .`.

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
| `mistral` | Cloud, default when MISTRAL_API_KEY is set | `mistral-ocr-4-0`, native PDF input | Markdown |
| `gemini` | Cloud, free-tier fallback | `gemini-3.5-flash-lite` | Markdown |
| `rapidocr` | Local, CPU, offline fallback on Linux | RapidOCR-ONNX v3.9.x (PP-OCRv6) | Plain text lines assembled in reading order (no invented Markdown structure) |
| `glm` | Local, offline fallback on macOS arm64 (mlx-vlm) or Linux (Ollama HTTP) | GLM-OCR 0.9B (MIT) | Markdown |

RapidOCR is the fast classical path: sub-second per page on CPU, strong on plain text, no tables or math.
GLM-OCR is a small document VLM: higher-quality Markdown with tables and formulas, but slow on a CPU-only server, so on Linux it is opt-in and reached through an Ollama server you run yourself.
No model weights are downloaded during install; RapidOCR fetches its ONNX models on first use, and the GLM backends require a server or the `mlx` extra you set up separately.

### Engine selection

```
doc parse file.pdf --engine rapidocr|glm|gemini|mistral|auto
```

`auto` (the default) prefers cloud OCR, in cost order:

1. `mistral` (`mistral-ocr-4-0`) when `MISTRAL_API_KEY` is available.
2. `gemini` (`gemini-3.5-flash-lite`, free tier) when `GEMINI_API_KEY` is available.
3. The local engine for the platform otherwise: `rapidocr` on Linux, `glm` on macOS.

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
doc parse confidential.pdf --engine rapidocr   # or --engine glm
```

Set `"default_engine": "rapidocr"` (or `"glm"`) in the config to make local the standing default and opt into cloud only per call.

### Cloud keys

Keys are read from the environment, never stored by the engines in the config file.

- `MISTRAL_API_KEY` for the `mistral` engine.
- `GEMINI_API_KEY` for the `gemini` engine.

With either key present in the environment, `auto` routes to that cloud engine, so exporting the key is all it takes to switch on cloud OCR.

## Commands

```
doc parse <file>                 # full pipeline (office/pdf/image), Markdown out
doc inspect <file.pdf>           # pdf-inspector classification report
doc ocr <file|image> [--engine]  # force the OCR path
doc serve [--host] [--port]      # run the OCR HTTP server (needs [server] extra)
```

Global flags:

- `--json` emits a structured JSON payload instead of human text.
- Text output larger than 30000 characters (configurable) is written to a temp file and the path is printed instead, so a large document never floods the terminal.

## Configuration

Config lives at `~/.config/doc/config.json` (override with `DOC_CONFIG`).
Every key is optional and falls back to a default; secrets are not stored here.

```json
{
  "default_engine": "auto",
  "ollama_url": "http://localhost:11434",
  "ollama_model": "glm-ocr",
  "gemini_model": "gemini-3.5-flash-lite",
  "mistral_model": "mistral-ocr-4-0",
  "mlx_model": "mlx-community/GLM-OCR-bf16",
  "spill_threshold": 30000
}
```

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

## Development

```
uv run pytest
```

The suite covers config loading, engine selection, cloud request construction (offline, no live calls), the GLM Ollama request shape, RapidOCR on a rendered image, pdf-inspector classification and parsing, and the server round-trip against RapidOCR.
Cloud engines are tested by asserting request construction only.

## Licensing

doc-cli is MIT.
Its parsing dependencies (pdf-inspector, anydoc, RapidOCR, GLM-OCR weights) are MIT or Apache-2.0.
