"""FastAPI OCR server.

Two contracts:

1. Firecrawl RunPod-MU envelope, so this plugs into a self-hosted Firecrawl via
   ``PDF_MU_V2_BASE_URL``. Firecrawl POSTs the URL directly with
   ``{"input": {"file_content": "<base64>", "filename": "x.pdf"}}`` and expects
   ``{"status": "COMPLETED", "output": {"markdown": "..."}}``. Served at both
   ``POST /`` and ``POST /runsync`` (point PDF_MU_V2_BASE_URL at whichever).

2. A plain ``POST /ocr`` for direct use: multipart file upload, or JSON
   ``{"file_content": "<base64>", "filename": "x.pdf"}``. Returns
   ``{"markdown": ..., "engine": ..., "kind": ...}``.

Note: PRs firecrawl/firecrawl #3201 and #3211 (both closed, unmerged as of this
writing) propose a simpler ``PDF_OCR_BASE_URL`` contract returning
``{markdown, html}``. If that lands, the plain /ocr shape here is close; see the
README for how to adapt.
"""

from __future__ import annotations

import base64
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from .config import Config


def _process_bytes(data: bytes, filename: str, engine_name: str, config: Config) -> dict[str, Any]:
    from .pipeline import parse

    suffix = Path(filename).suffix or ".pdf"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as fh:
        fh.write(data)
        fh.flush()
        return parse(fh.name, engine_name, config)


def build_app(config: Config, engine_name: str = "auto"):
    from .engines.base import resolve_engine_name

    # Resolve once, local-first: auto stays on the local engine unless the
    # config explicitly names a cloud default_engine. This keeps a self-hosted
    # Firecrawl backend from silently billing a paid cloud OCR endpoint just
    # because a cloud key happens to sit in the server's environment.
    engine_name = resolve_engine_name(engine_name, config, prefer_cloud=False)

    app = FastAPI(title="doc-cli OCR server")

    async def _mu(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"invalid JSON: {exc}") from exc
        payload = body.get("input") or {}
        b64 = payload.get("file_content")
        filename = payload.get("filename", "input.pdf")
        if not b64:
            raise HTTPException(status_code=400, detail="missing input.file_content")
        try:
            data = base64.b64decode(b64)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"bad base64: {exc}") from exc
        try:
            result = _process_bytes(data, filename, engine_name, config)
        except Exception as exc:  # noqa: BLE001
            return JSONResponse({"status": "FAILED", "error": str(exc)}, status_code=200)
        return JSONResponse(
            {"status": "COMPLETED", "output": {"markdown": result["markdown"]}}
        )

    @app.post("/")
    async def mu_root(request: Request):
        return await _mu(request)

    @app.post("/runsync")
    async def mu_runsync(request: Request):
        return await _mu(request)

    @app.post("/ocr")
    async def ocr(request: Request):
        content_type = request.headers.get("content-type", "")
        if content_type.startswith("multipart/form-data"):
            form = await request.form()
            upload = form.get("file")
            if upload is None:
                raise HTTPException(status_code=400, detail="missing 'file' part")
            data = await upload.read()
            filename = getattr(upload, "filename", None) or "upload.bin"
        else:
            body = await request.json()
            b64 = body.get("file_content")
            filename = body.get("filename", "input.pdf")
            if not b64:
                raise HTTPException(status_code=400, detail="missing file or file_content")
            data = base64.b64decode(b64)
        result = _process_bytes(data, filename, engine_name, config)
        return {
            "markdown": result["markdown"],
            "engine": result.get("engine"),
            "kind": result.get("kind"),
        }

    @app.get("/health")
    async def health():
        return {"status": "ok", "engine": engine_name}

    return app


def run(host: str, port: int, engine_name: str, config: Config) -> None:
    import uvicorn

    app = build_app(config, engine_name)
    uvicorn.run(app, host=host, port=port)
