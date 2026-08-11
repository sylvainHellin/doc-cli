"""Mistral OCR cloud engine: mistral-ocr-4-0 via POST /v1/ocr.

Mistral OCR accepts native PDF input (base64 document) and image input, and
returns markdown per page. Key from MISTRAL_API_KEY, falling back to a key
stored in the config file. Request construction is unit-tested offline.
"""

from __future__ import annotations

import base64

import httpx

from .base import EngineUnavailable, OcrEngine, OcrResult, cloud_key

API_URL = "https://api.mistral.ai/v1/ocr"


class MistralEngine(OcrEngine):
    name = "mistral"
    structured = True

    def check(self) -> None:
        self._api_key()

    def _api_key(self) -> str:
        key = cloud_key("MISTRAL_API_KEY", self.config)
        if not key:
            raise EngineUnavailable(
                "MISTRAL_API_KEY is not set (export it or run: doc config set-key mistral <key>)"
            )
        return key

    def build_image_request(self, image: bytes, mime: str = "image/png") -> tuple[str, dict, dict]:
        """Return (url, headers, json_body) for an image page. Pure, no network."""
        b64 = base64.b64encode(image).decode("ascii")
        body = {
            "model": self.config.mistral_model,
            "document": {
                "type": "image_url",
                "image_url": f"data:{mime};base64,{b64}",
            },
        }
        return API_URL, self._headers(), body

    def build_pdf_request(self, pdf: bytes) -> tuple[str, dict, dict]:
        """Return (url, headers, json_body) for a native PDF. Pure, no network."""
        b64 = base64.b64encode(pdf).decode("ascii")
        body = {
            "model": self.config.mistral_model,
            "document": {
                "type": "document_url",
                "document_url": f"data:application/pdf;base64,{b64}",
            },
        }
        return API_URL, self._headers(), body

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._api_key()}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def parse_response(data: dict) -> list[str]:
        return [p.get("markdown", "") for p in data.get("pages", [])]

    def _post(self, client: httpx.Client, url: str, headers: dict, body: dict) -> list[str]:
        resp = client.post(url, headers=headers, json=body)
        if resp.status_code >= 400:
            raise EngineUnavailable(
                f"Mistral error {resp.status_code}: {resp.text[:200]}"
            )
        return self.parse_response(resp.json())

    def ocr(self, images: list[bytes]) -> OcrResult:
        self.check()
        pages: list[str] = []
        with httpx.Client(timeout=120.0) as client:
            for image in images:
                url, headers, body = self.build_image_request(image)
                pages.extend(self._post(client, url, headers, body))
        return OcrResult(
            markdown="\n\n".join(pages), pages=pages, engine=self.name, structured=True
        )

    def ocr_pdf(self, pdf: bytes) -> OcrResult:
        """OCR a native PDF in one call (Mistral supports PDF input directly)."""
        self.check()
        with httpx.Client(timeout=300.0) as client:
            url, headers, body = self.build_pdf_request(pdf)
            pages = self._post(client, url, headers, body)
        return OcrResult(
            markdown="\n\n".join(pages), pages=pages, engine=self.name, structured=True
        )
