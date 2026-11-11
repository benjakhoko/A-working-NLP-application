"""Document upload, extraction and access-control tests."""
from __future__ import annotations

import io

from backend.models import Analysis, Document
from tests.conftest import GENERAL_TEXT, make_docx_bytes, make_pdf_bytes, upload_txt


def test_txt_upload_extracts_text(auth_client, app):
    response = upload_txt(auth_client)
    assert response.status_code == 201, response.get_json()
    document = response.get_json()["data"]["document"]
    assert document["filename"] == "sample.txt"
    assert document["file_type"] == "txt"
    assert document["word_count"] > 20
    assert document["char_count"] > 50
    with app.app_context():
        stored = Document.query.get(document["id"])
        assert stored.extracted_text.startswith("Baking bread")
        assert stored.file_size > 0


def test_pdf_upload_extracts_text(auth_client):
    response = auth_client.post(
        "/api/documents/upload",
        data={"file": (io.BytesIO(make_pdf_bytes()), "report.pdf", "application/pdf")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 201, response.get_json()
    document = response.get_json()["data"]["document"]
    assert document["file_type"] == "pdf"
    assert document["word_count"] > 10


def test_docx_upload_extracts_text(auth_client):
    response = auth_client.post(
        "/api/documents/upload",
        data={
            "file": (
                io.BytesIO(make_docx_bytes()),
                "notes.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 201, response.get_json()
    assert response.get_json()["data"]["document"]["file_type"] == "docx"


def test_unsupported_extension_rejected(auth_client):
    response = auth_client.post(
        "/api/documents/upload",
        data={"file": (io.BytesIO(b"# Markdown"), "notes.md", "text/markdown")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "unsupported_file"


def test_mime_extension_mismatch_rejected(auth_client):
    response = auth_client.post(
        "/api/documents/upload",
        data={"file": (io.BytesIO(b"plain text"), "fake.pdf", "text/plain")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "unsupported_file"


def test_fake_pdf_signature_rejected(auth_client):
    response = auth_client.post(
        "/api/documents/upload",
        data={"file": (io.BytesIO(b"This is not a PDF file at all " * 10), "fake.pdf", "application/pdf")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "invalid_file"


def test_binary_txt_rejected(auth_client):
    response = auth_client.post(
        "/api/documents/upload",
        data={"file": (io.BytesIO(bytes(range(0, 255)) * 20), "binary.txt", "text/plain")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "invalid_file"


def test_empty_upload_rejected(auth_client):
    response = auth_client.post(
        "/api/documents/upload",
        data={"file": (io.BytesIO(b""), "empty.txt", "text/plain")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "empty_file"


def test_upload_size_limit(auth_client, app):
    app.config["MAX_CONTENT_LENGTH"] = 200
    response = auth_client.post(
        "/api/documents/upload",
        data={"file": (io.BytesIO(b"a" * 500), "large.txt", "text/plain")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 413


def test_document_listing_detail_and_deletion(auth_client, app):
    first = upload_txt(auth_client, GENERAL_TEXT, "first.txt").get_json()["data"]["document"]
    upload_txt(auth_client, GENERAL_TEXT, "second.txt")
    listing = auth_client.get("/api/documents?per_page=10")
    assert listing.status_code == 200
    assert listing.get_json()["data"]["pagination"]["total"] == 2

    detail = auth_client.get(f"/api/documents/{first['id']}")
    assert detail.status_code == 200
    assert "Baking bread" in detail.get_json()["data"]["document"]["extracted_text"]

    keyword = auth_client.post(
        "/api/keywords/extract",
        json={"document_id": first["id"], "algorithm": "tfidf", "top_n": 5},
    )
    analysis_id = keyword.get_json()["data"]["analysis_id"]

    deleted = auth_client.delete(f"/api/documents/{first['id']}")
    assert deleted.status_code == 200
    assert auth_client.get(f"/api/documents/{first['id']}").status_code == 404
    with app.app_context():
        assert Analysis.query.get(analysis_id) is None


def test_cross_user_document_access_is_blocked(auth_client, second_client):
    document_id = upload_txt(auth_client).get_json()["data"]["document"]["id"]
    assert second_client.get(f"/api/documents/{document_id}").status_code == 404
    assert second_client.delete(f"/api/documents/{document_id}").status_code == 404
    assert second_client.get("/api/documents").get_json()["data"]["pagination"]["total"] == 0
