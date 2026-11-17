import uuid

import requests
from conftest import API_URL, forged_token, new_session, upload, wait_gap


def test_session_is_anonymous_and_needs_no_credentials():
    response = requests.post(f"{API_URL}/api/v1/session", timeout=30)
    assert response.status_code == 201
    assert response.json()["token"]


def test_missing_or_forged_token_is_rejected():
    assert requests.get(f"{API_URL}/api/v1/documents", timeout=30).status_code == 401
    bad = {"Authorization": f"Bearer {forged_token(uuid.uuid4().hex)}"}
    assert requests.get(f"{API_URL}/api/v1/documents", headers=bad, timeout=30).status_code == 401


def test_user_id_in_form_is_ignored_and_users_are_isolated(user, other_user):
    # The old API trusted a `uid` form field. The identity must come only from the token.
    response = upload(user, "a.txt", b"Noi dung bi mat cua nguoi A", "text/plain")
    assert response.status_code == 202
    response = requests.post(f"{API_URL}/api/v1/documents", headers=other_user,
                             files={"file": ("b.txt", b"hello", "text/plain")},
                             data={"uid": "someone-else"}, timeout=60)
    assert response.status_code in (202, 429)
    listing = requests.get(f"{API_URL}/api/v1/documents", headers=user, timeout=30).json()["documents"]
    assert all(d["filename"] == "a.txt" for d in listing)


def test_unsupported_type_is_rejected(user):
    response = upload(user, "virus.exe", b"MZ....", "application/octet-stream")
    assert response.status_code == 415


def test_empty_file_is_rejected(user):
    wait_gap()
    response = upload(user, "empty.txt", b"", "text/plain")
    assert response.status_code == 400


def test_oversized_file_is_rejected(user):
    wait_gap()
    response = upload(user, "big.txt", b"a" * (21 * 1024 * 1024), "text/plain")
    assert response.status_code == 413


def test_upload_rate_limit(user):
    wait_gap()
    first = upload(user, "one.txt", b"first document", "text/plain")
    second = upload(user, "two.txt", b"second document", "text/plain")
    assert first.status_code == 202
    assert second.status_code == 429


def test_search_requires_a_ready_document(user):
    response = requests.post(f"{API_URL}/api/v1/search", headers=user, json={"query": "x"}, timeout=30)
    assert response.status_code == 404
