"""Gemini cloud OCR engine: gemini-3.5-flash-lite (free-tier friendly default).

Sends page images to the Gemini generateContent endpoint and returns markdown.
Key from GEMINI_API_KEY. Request construction is unit-tested offline; no live
call is made during tests.
"""

from __future__ import annotations

import base64
import os

import httpx

from .base import EngineUnavailable, OcrEngine, OcrResult

PROMPT = (
    "Transcribe this document image to clean GitHub-Flavored Markdown. "
    "Preserve headings, lists, and tables. Output only the markdown, no commentary."
)
API_ROOT = "https://generativelanguage.googleapis.com/v1beta"


class GeminiEngine(OcrEngine):
    name = "gemini"
    structured = True

    def check(self) -> None:
        if not os.environ.get("GEMINI_API_KEY"):
            raise EngineUnavailable("GEMINI_API_KEY is not set")

    def _api_key(self) -> str:
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise EngineUnavailable("GEMINI_API_KEY is not set")
        return key

    def build_request(self, image: bytes, mime: str = "image/png") -> tuple[str, dict, dict]:
        """Return (url, headers, json_body) for one page. Pure, no network."""
        model = self.config.gemini_model
        url = f"{API_ROOT}/models/{model}:generateContent"
        b64 = base64.b64encode(image).decode("ascii")
        body = {
            "contents": [
                {
                    "parts": [
                        {"text": PROMPT},
                        {"inline_data": {"mime_type": mime, "data": b64}},
                    ]
                }
            ]
        }
        headers = {"x-goog-api-key": self._api_key()}
        return url, headers, body

    @staticmethod
    def parse_response(data: dict) -> str:
        candidates = data.get("candidates", [])
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts)

    def ocr(self, images: list[bytes]) -> OcrResult:
        self.check()
        pages: list[str] = []
        with httpx.Client(timeout=120.0) as client:
            for image in images:
                url, headers, body = self.build_request(image)
                resp = client.post(url, headers=headers, json=body)
                if resp.status_code >= 400:
                    raise EngineUnavailable(
                        f"Gemini error {resp.status_code}: {resp.text[:200]}"
                    )
                pages.append(self.parse_response(resp.json()))
        return OcrResult(
            markdown="\n\n".join(pages), pages=pages, engine=self.name, structured=True
        )
