import time

import requests
from conftest import (API_URL, make_docx, make_pdf, make_png_with_text, make_xlsx, search,
                      upload, wait_for_status, wait_gap)


def test_mixed_file_types_are_indexed_and_searchable(user):
    files = [
        ("notes.txt", b"Cuoc hop ngay 12 thang 3 bao ve luan van thac si.", "text/plain"),
        ("stock.csv", "Ma,Kho,SoLuong\nSP1,Kho Thu Duc,40\nSP2,Kho Binh Duong,15\n".encode(), "text/csv"),
        ("contract.docx", make_docx(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("inventory.xlsx", make_xlsx(30), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("scan.png", make_png_with_text("HOA DON 2026"), "image/png"),
        ("report.pdf", make_pdf(3, marker="bao cao doanh thu quy 3"), "application/pdf"),
    ]
    doc_ids = []
    for name, content, mime in files:
        wait_gap()
        response = upload(user, name, content, mime)
        assert response.status_code == 202, response.text
        doc_ids.append(response.json()["doc_id"])

    for doc_id in doc_ids:
        doc = wait_for_status(user, doc_id)
        assert doc["status"] == "ready", doc
        assert doc["chunks"] > 0

    assert any("Kho Ha Noi" in h["text"] for h in search(user, "kho Ha Noi san pham")), "xlsx not searchable"
    assert any("Quan 7" in h["text"] for h in search(user, "hop dong thue van phong")), "docx not searchable"
    assert any("bao cao doanh thu" in h["text"] for h in search(user, "doanh thu quy 3")), "pdf not searchable"


def test_large_pdf_is_fully_indexed(user):
    """300 pages, roughly 35k words. Every page must be indexed, not only the first ones."""
    content = make_pdf(300, words_per_page=120, marker="tai lieu lon")
    wait_gap()
    started = time.time()
    response = upload(user, "large.pdf", content, "application/pdf")
    assert response.status_code == 202, response.text
    doc = wait_for_status(user, response.json()["doc_id"])
    elapsed = time.time() - started
    assert doc["status"] == "ready", doc
    assert doc["chunks"] >= 300, f"expected at least one chunk per page, got {doc['chunks']}"
    print(f"large pdf: {doc['chunks']} chunks in {elapsed:.1f}s")
    last_page_hits = [h for h in search(user, "tai lieu lon muc 299") if h["source"].get("page") == 300]
    assert last_page_hits, "last page of the large document is not searchable"


def test_many_documents_per_user_and_delete(user):
    ids = []
    for i in range(4):
        wait_gap()
        response = upload(user, f"doc{i}.txt", f"Tai lieu so {i} noi dung rieng.".encode(), "text/plain")
        assert response.status_code == 202
        ids.append(response.json()["doc_id"])
    for doc_id in ids:
        wait_for_status(user, doc_id)
    listing = requests.get(f"{API_URL}/api/v1/documents", headers=user, timeout=30).json()["documents"]
    assert len(listing) == 4

    removed = ids[0]
    assert requests.delete(f"{API_URL}/api/v1/documents/{removed}", headers=user, timeout=60).status_code == 204
    assert requests.get(f"{API_URL}/api/v1/documents/{removed}", headers=user, timeout=30).status_code == 404
    remaining_hits = search(user, "Tai lieu so 0 noi dung rieng")
    assert all(h["source"].get("doc_id") != removed for h in remaining_hits), "deleted document still searchable"


def test_corrupt_pdf_is_marked_failed_without_retry(user):
    wait_gap()
    response = upload(user, "broken.pdf", b"%PDF-1.4 this is not a real pdf", "application/pdf")
    assert response.status_code == 202
    doc = wait_for_status(user, response.json()["doc_id"])
    assert doc["status"] == "failed"
    assert doc["error"] in ("invalid_or_encrypted_pdf", "empty_pdf")


def test_other_users_cannot_see_or_search_documents(user, other_user):
    wait_gap()
    response = upload(user, "secret.txt", b"Ma ngan hang rieng cua nguoi dung A 999999", "text/plain")
    doc = wait_for_status(user, response.json()["doc_id"])
    assert doc["status"] == "ready"
    listing = requests.get(f"{API_URL}/api/v1/documents", headers=other_user, timeout=30).json()["documents"]
    assert listing == []
    other_search = requests.post(f"{API_URL}/api/v1/search", headers=other_user,
                                 json={"query": "ma ngan hang"}, timeout=60)
    assert other_search.status_code == 404
