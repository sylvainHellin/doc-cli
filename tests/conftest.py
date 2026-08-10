"""Shared fixtures: a tiny born-digital text PDF and a text image."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from doc_cli.config import Config


@pytest.fixture
def config() -> Config:
    return Config()


@pytest.fixture
def text_pdf(tmp_path: Path) -> Path:
    """A small born-digital (text layer) PDF, via reportlab."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    path = tmp_path / "hello.pdf"
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setFont("Helvetica", 16)
    c.drawString(72, 720, "Hello from doc-cli.")
    c.drawString(72, 690, "This is a born-digital text PDF for smoke testing.")
    c.showPage()
    c.save()
    return path


@pytest.fixture
def text_image(tmp_path: Path) -> Path:
    """A PNG image containing rendered text for the OCR path."""
    from PIL import Image, ImageDraw, ImageFont

    path = tmp_path / "line.png"
    img = Image.new("RGB", (600, 160), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 48)
    except OSError:
        font = ImageFont.load_default()
    draw.text((20, 50), "HELLO WORLD", fill="black", font=font)
    img.save(path)
    return path


@pytest.fixture
def text_image_bytes(text_image: Path) -> bytes:
    return text_image.read_bytes()
