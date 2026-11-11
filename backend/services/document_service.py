"""Secure document extraction and validation.

Uploaded files are processed in memory. Only metadata and extracted text are
persisted, which reduces storage exposure and satisfies the project brief's
preference not to keep original uploads.
"""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import fitz  # PyMuPDF
from docx import Document as DocxDocument
from werkzeug.datastructures import FileStorage

from backend.services.nlp.preprocessing import clean_text, text_statistics
from backend.utils.responses import APIError

MAX_PAGES = 250


def sanitize_filename(filename: str | None) -> str:
    name = Path(filename or "document").name
    name = re.sub(r"[\x00-\x1f\x7f/\\:*?\"<>|]", "_", name).strip(" .")
    return (name or "document")[:200]


def _decode_text(raw: bytes) -> str:
    if b"\x00" in raw[:4000] and not raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise APIError("The file appears to be binary, not plain text.", 422, "invalid_file")
    for encoding in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            text = raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
        # Reject binary-looking decode results (many control characters).
        control = sum(1 for char in text[:4000] if ord(char) < 9)
        if control / max(len(text[:4000]), 1) < 0.02:
            return text
    raise APIError("The text file could not be decoded. Save it as UTF-8 and retry.", 422, "invalid_file")


def _extract_pdf(raw: bytes) -> str:
    if not raw.lstrip()[:5].startswith(b"%PDF"):
        raise APIError("The file does not have a valid PDF signature.", 422, "invalid_file")
    try:
        pdf = fitz.open(stream=raw, filetype="pdf")
    except Exception as exc:
        raise APIError("The PDF file is corrupted or password protected.", 422, "invalid_file") from exc
    if pdf.page_count > MAX_PAGES:
        pdf.close()
        raise APIError(f"PDFs with more than {MAX_PAGES} pages are not supported.", 413, "file_too_large")
    parts: list[str] = []
    try:
        for page in pdf:
            parts.append(page.get_text("text"))
    finally:
        pdf.close()
    text = "\n\n".join(parts)
    if len(re.sub(r"\s", "", text)) < 10:
        raise APIError(
            "No selectable text was found. The PDF may be a scanned image; OCR is not enabled.",
            422,
            "no_text",
        )
    return text


def _extract_docx(raw: bytes) -> str:
    if not zipfile.is_zipfile(io.BytesIO(raw)):
        raise APIError("The DOCX file is not a valid ZIP container.", 422, "invalid_file")
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
        if "word/document.xml" not in archive.namelist():
            raise APIError("The file is a ZIP archive but not a Word document.", 422, "invalid_file")
        document = DocxDocument(io.BytesIO(raw))
    except APIError:
        raise
    except Exception as exc:
        raise APIError("The Word document could not be read.", 422, "invalid_file") from exc
    parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n\n".join(parts)


def extract_upload(file: FileStorage, *, max_bytes: int, max_text_length: int) -> dict:
    if file is None or not file.filename:
        raise APIError("Choose a file to upload.", 422, "validation_error")
    filename = sanitize_filename(file.filename)
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    from flask import current_app

    if extension not in current_app.config["ALLOWED_EXTENSIONS"]:
        raise APIError("Only TXT, PDF and DOCX files are supported.", 422, "unsupported_file")
    allowed_mimes = current_app.config["ALLOWED_MIME_TYPES"][extension]
    mime = (file.mimetype or "application/octet-stream").lower()
    if mime not in allowed_mimes:
        raise APIError(f"The uploaded file type ({mime}) does not match .{extension}.", 422, "unsupported_file")

    raw = file.read(max_bytes + 1)
    if len(raw) == 0:
        raise APIError("The uploaded file is empty.", 422, "empty_file")
    if len(raw) > max_bytes:
        raise APIError(
            f"The file exceeds the {max_bytes // (1024 * 1024)} MB upload limit.",
            413,
            "file_too_large",
        )

    if extension == "pdf":
        text = _extract_pdf(raw)
    elif extension == "docx":
        text = _extract_docx(raw)
    else:
        text = _decode_text(raw)

    text = clean_text(text)
    if len(text) < 20:
        raise APIError(
            "The document contains too little extractable text to analyse.",
            422,
            "no_text",
        )
    if len(text) > max_text_length:
        raise APIError(
            f"The extracted text is {len(text):,} characters; the limit is {max_text_length:,}. "
            "Upload a shorter document.",
            413,
            "text_too_long",
        )

    stats = text_statistics(text)
    return {
        "filename": filename,
        "file_type": extension,
        "file_size": len(raw),
        "mime_type": mime,
        "extracted_text": text,
        "word_count": stats["word_count"],
        "char_count": stats["character_count"],
        "statistics": stats,
    }
