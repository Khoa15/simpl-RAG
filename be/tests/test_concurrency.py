"""Several users upload documents at the same time. Every document must finish as ready."""
from concurrent.futures import ThreadPoolExecutor

from conftest import make_pdf, new_session, upload, wait_for_status


def _one_user(index: int) -> tuple[str, str]:
    headers = new_session()
    content = make_pdf(40, words_per_page=100, marker=f"nguoi dung {index} tai lieu")
    response = upload(headers, f"user{index}.pdf", content, "application/pdf")
    assert response.status_code == 202, response.text
    doc = wait_for_status(headers, response.json()["doc_id"])
    return doc["status"], doc.get("error") or ""


def test_parallel_uploads_all_complete():
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(_one_user, range(6)))
    assert all(status == "ready" for status, _ in results), results
