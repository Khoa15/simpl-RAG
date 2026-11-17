"""Tests run against the real running stack (API + worker + Redis + Qdrant), not against mocks.

Run with:  docker compose run --rm api pytest tests -q
"""
import io
import os
import time
import uuid

import jwt
import pytest
import requests

API_URL = os.environ.get("API_URL", "http://api:8000")
JWT_SECRET = os.environ.get("JWT_SECRET", "")
JWT_ISSUER = os.environ.get("JWT_ISSUER", "simpl-rag")
POLL_SECONDS = 180


def new_session() -> dict:
    response = requests.post(f"{API_URL}/api/v1/session", timeout=30)
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.fixture
def user() -> dict:
    return new_session()


@pytest.fixture
def other_user() -> dict:
    return new_session()


def upload(headers: dict, name: str, content: bytes, mime: str = "application/octet-stream"):
    return requests.post(
        f"{API_URL}/api/v1/documents",
        headers=headers,
        files={"file": (name, io.BytesIO(content), mime)},
        timeout=120,
    )


def wait_for_status(headers: dict, doc_id: str, wanted=("ready", "failed")) -> dict:
    deadline = time.time() + POLL_SECONDS
    while time.time() < deadline:
        doc = requests.get(f"{API_URL}/api/v1/documents/{doc_id}", headers=headers, timeout=30).json()
        if doc["status"] in wanted:
            return doc
        time.sleep(2)
    raise AssertionError(f"document {doc_id} did not finish in {POLL_SECONDS}s")


def wait_gap():
    """Uploads and queries are rate-limited per user; step over the interval."""
    time.sleep(3.5)


def search(headers: dict, query: str) -> list:
    wait_gap()  # queries are rate-limited per user
    response = requests.post(f"{API_URL}/api/v1/search", headers=headers, json={"query": query}, timeout=60)
    assert response.status_code == 200, response.text
    return response.json()["results"]


def make_pdf(pages: int, words_per_page: int = 120, marker: str = "kho hang") -> bytes:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_auto_page_break(True, 15)
    for page in range(pages):
        pdf.add_page()
        pdf.set_font("Helvetica", size=11)
        body = " ".join(f"{marker} muc {page} tu {i}" for i in range(words_per_page))
        pdf.multi_cell(0, 6, body)
    return bytes(pdf.output())


def make_xlsx(rows: int, marker: str = "Kho Ha Noi") -> bytes:
    from openpyxl import Workbook

    wb = Workbook(write_only=True)
    ws = wb.create_sheet("Inventory")
    ws.append(["Ma SP", "Ten", "Kho", "So luong"])
    for i in range(rows):
        ws.append([f"SP{i:05d}", f"San pham {i}", marker, i])
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def make_docx(marker: str = "Hop dong thue van phong Quan 7") -> bytes:
    import docx

    document = docx.Document()
    document.add_paragraph(marker)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def make_png_with_text(text: str = "HOA DON 2026") -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (900, 200), "white")
    draw = ImageDraw.Draw(image)
    draw.text((30, 60), text, fill="black", font=ImageFont.load_default(size=64))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def forged_token(user_id: str) -> str:
    """Token signed with a different secret. Must be rejected."""
    return jwt.encode({"sub": user_id, "iss": JWT_ISSUER, "iat": int(time.time()), "exp": int(time.time()) + 600},
                      "x" * 48, algorithm="HS256")
