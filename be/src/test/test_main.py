import tempfile
import time
import pytest
from fastapi.testclient import TestClient
from src.main import app, users_vectorstores  # main.py là file chứa code FastAPI

client = TestClient(app)


def test_upload_and_retrieve():
    # from fpdf import FPDF
    # pdf = FPDF()
    # pdf.add_page()
    # pdf.set_font("Arial", size=12)
    # pdf.cell(200, 10, txt="Hello RAG Test", ln=True)
    # pdf.output("test.pdf")

    uid = "test_user"

    # with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
    #     pdf.output(tmp_pdf.name)
    #     tmp_pdf_path = tmp_pdf.name

    # Upload file
    with open("test.pdf", "rb") as f:
        response = client.post(
            "/api/v1/document",
            data={"uid": uid},
            files={"file": ("test.pdf", f, "application/pdf")}
        )
    assert response.status_code == 200
    assert response.json()["message"] == "Upload successfully"
    assert uid in users_vectorstores

    # Retrieve document
    response = client.post(
        "/api/v1/retrieve",
        data={"query_text": "Hello?", "uid": uid}
    )
    assert response.status_code == 200
    assert "message" in response.json()


def test_auto_delete():
    uid = "delete_me"
    users_vectorstores[uid] = {"time": time.time() - 20000, "vectorstores": None}

    # Giả lập chạy cleanup
    from src.main import cleanup_task
    import asyncio
    asyncio.run(cleanup_task())

    assert uid not in users_vectorstores
