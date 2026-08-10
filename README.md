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
| `rapidocr` | Local, CPU, Linux default | RapidOCR-ONNX v3.9.x (PP-OCRv6) | Plain text lines assembled in reading order (no invented Markdown structure) |
| `glm` | macOS arm64 via mlx-vlm, Linux via Ollama HTTP | GLM-OCR 0.9B (MIT) | Markdown |
| `gemini` | Cloud, default cloud choice | `gemini-3.5-flash-lite` | Markdown |
| `mistral` | Cloud | `mistral-ocr-4-0`, native PDF input | Markdown |

RapidOCR is the fast classical path: sub-second per page on CPU, strong on plain text, no tables or math.
GLM-OCR is a small document VLM: higher-quality Markdown with tables and formulas, but slow on a CPU-only server, so on Linux it is opt-in and reached through an Ollama server you run yourself.
No model weights are downloaded during install; RapidOCR fetches its ONNX models on first use, and the GLM backends require a server or the `mlx` extra you set up separately.

### Engine selection

```
doc parse file.pdf --engine rapidocr|glm|gemini|mistral|auto
```

`auto` (the default) picks the local engine for the platform: RapidOCR on Linux, GLM on macOS.
Cloud engines are used only when named explicitly with `--engine`, or when `default_engine` in the config file names one.
`auto` never silently reaches the network.

### Cloud keys

Keys are read from the environment, never from the config file.

- `GEMINI_API_KEY` for the `gemini` engine.
- `MISTRAL_API_KEY` for the `mistral` engine.

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
  "default_cloud_engine": "gemini",
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

`GET /health` reports liveness and the configured engine.

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
