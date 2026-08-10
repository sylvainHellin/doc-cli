"""GLM-OCR 0.9B engine (MIT, zai-org/GLM-OCR).

Two backends, selected by platform:
- macOS arm64: mlx-vlm with mlx-community/GLM-OCR-bf16 (optional [mlx] extra).
- Linux: an Ollama HTTP server that has the GLM-OCR model pulled (config.ollama_url).

GLM-OCR needs a task-keyword prompt ("Text/Table/Formula Recognition:"). We use
a general text-recognition prompt by default. No weights are downloaded here; if
no backend is reachable, ocr() raises EngineUnavailable with a clear message.
"""

from __future__ import annotations

import base64
import platform

import httpx

from .base import EngineUnavailable, OcrEngine, OcrResult

PROMPT = "Text Recognition: Convert this document image to markdown."


class GlmEngine(OcrEngine):
    name = "glm"
    structured = True

    def ocr(self, images: list[bytes]) -> OcrResult:
        if platform.system() == "Darwin" and platform.machine() == "arm64":
            pages = [self._ocr_mlx(img) for img in images]
        else:
            pages = [self._ocr_ollama(img) for img in images]
        markdown = "\n\n".join(pages)
        return OcrResult(
            markdown=markdown, pages=pages, engine=self.name, structured=True
        )

    # macOS / MLX backend
    def _ocr_mlx(self, image: bytes) -> str:
        try:
            from mlx_vlm import generate, load
            from mlx_vlm.prompt_utils import apply_chat_template
            from mlx_vlm.utils import load_config
        except ImportError as exc:
            raise EngineUnavailable(
                "GLM via MLX needs the [mlx] extra (mlx-vlm) on macOS arm64"
            ) from exc
        import tempfile

        model_id = self.config.mlx_model
        model, processor = load(model_id)
        cfg = load_config(model_id)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as fh:
            fh.write(image)
            image_path = fh.name
        formatted = apply_chat_template(processor, cfg, PROMPT, num_images=1)
        out = generate(model, processor, formatted, [image_path], verbose=False)
        return out.text if hasattr(out, "text") else str(out)

    # Linux / Ollama backend
    def _ocr_ollama(self, image: bytes) -> str:
        url = self.config.ollama_url.rstrip("/")
        model = self.config.ollama_model
        b64 = base64.b64encode(image).decode("ascii")
        payload = {
            "model": model,
            "prompt": PROMPT,
            "images": [b64],
            "stream": False,
        }
        try:
            resp = httpx.post(f"{url}/api/generate", json=payload, timeout=300.0)
        except httpx.HTTPError as exc:
            raise EngineUnavailable(
                f"GLM via Ollama unreachable at {url}: {exc}. "
                f"Start an Ollama server with the '{model}' model, or set ollama_url."
            ) from exc
        if resp.status_code == 404:
            raise EngineUnavailable(
                f"Ollama at {url} has no model '{model}'. Pull it first."
            )
        if resp.status_code >= 400:
            raise EngineUnavailable(
                f"Ollama error {resp.status_code}: {resp.text[:200]}"
            )
        return resp.json().get("response", "")
