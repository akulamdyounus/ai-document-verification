import io
from pathlib import Path
import fitz
from PIL import Image
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.database import init_db

init_db()
client = TestClient(app)


def create_test_image_bytes(format_type: str = "PNG") -> bytes:
    """Creates a valid test image with text."""
    img = Image.new("RGB", (300, 200), color=(240, 240, 240))
    buf = io.BytesIO()
    img.save(buf, format=format_type)
    return buf.getvalue()


def create_test_pdf_bytes(pages: int = 1, text_prefix: str = "Test Page") -> bytes:
    """Creates a synthetic PDF with specified page count."""
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 100), f"{text_prefix} {i + 1}", fontsize=14)
    buf = doc.tobytes()
    doc.close()
    return buf


# --------------------------------------------------------------------------
# 1. PDF Preview & Metadata Tests
# --------------------------------------------------------------------------

def test_single_page_pdf_preview():
    pdf_bytes = create_test_pdf_bytes(pages=1, text_prefix="Driving Licence DL-0420110012345")
    up_res = client.post(
        "/api/upload",
        files={"file": ("licence.pdf", pdf_bytes, "application/pdf")},
    )
    assert up_res.status_code == 201
    file_id = up_res.json()["file_id"]
    assert up_res.json()["page_count"] == 1
    assert up_res.json()["preview_available"] is True

    # 1. Check metadata endpoint
    meta_res = client.get(f"/api/documents/{file_id}/metadata")
    assert meta_res.status_code == 200
    meta = meta_res.json()
    assert meta["file_id"] == file_id
    assert meta["file_type"] == "pdf"
    assert meta["page_count"] == 1
    assert meta["preview_available"] is True

    # 2. Check preview image endpoint
    prev_res = client.get(f"/api/documents/{file_id}/preview?page=1")
    assert prev_res.status_code == 200
    assert prev_res.headers["content-type"] == "image/png"
    assert len(prev_res.content) > 100


def test_multipage_pdf_preview():
    pdf_bytes = create_test_pdf_bytes(pages=3, text_prefix="Bank Statement Page")
    up_res = client.post(
        "/api/upload",
        files={"file": ("statement.pdf", pdf_bytes, "application/pdf")},
    )
    assert up_res.status_code == 201
    file_id = up_res.json()["file_id"]
    assert up_res.json()["page_count"] == 3

    # Metadata should show 3 pages
    meta_res = client.get(f"/api/documents/{file_id}/metadata")
    assert meta_res.status_code == 200
    assert meta_res.json()["page_count"] == 3

    # Test preview for each page
    for p in [1, 2, 3]:
        p_res = client.get(f"/api/documents/{file_id}/preview?page={p}")
        assert p_res.status_code == 200
        assert p_res.headers["content-type"] == "image/png"
        assert len(p_res.content) > 100

    # Test thumbnail rendering
    thumb_res = client.get(f"/api/documents/{file_id}/preview?page=1&thumbnail=true")
    assert thumb_res.status_code == 200
    assert thumb_res.headers["content-type"] == "image/png"


# --------------------------------------------------------------------------
# 2. Image Preview Tests (JPG & PNG)
# --------------------------------------------------------------------------

def test_png_image_preview():
    png_bytes = create_test_image_bytes("PNG")
    up_res = client.post(
        "/api/upload",
        files={"file": ("sample.png", png_bytes, "image/png")},
    )
    assert up_res.status_code == 201
    file_id = up_res.json()["file_id"]

    meta_res = client.get(f"/api/documents/{file_id}/metadata")
    assert meta_res.status_code == 200
    assert meta_res.json()["file_type"] == "image"
    assert meta_res.json()["page_count"] == 1

    prev_res = client.get(f"/api/documents/{file_id}/preview")
    assert prev_res.status_code == 200
    assert "image/" in prev_res.headers["content-type"]
    assert len(prev_res.content) > 100


def test_jpg_image_preview():
    jpg_bytes = create_test_image_bytes("JPEG")
    up_res = client.post(
        "/api/upload",
        files={"file": ("photo_licence.jpg", jpg_bytes, "image/jpeg")},
    )
    assert up_res.status_code == 201
    file_id = up_res.json()["file_id"]

    prev_res = client.get(f"/api/documents/{file_id}/preview")
    assert prev_res.status_code == 200
    assert "image/" in prev_res.headers["content-type"]
    assert len(prev_res.content) > 100


# --------------------------------------------------------------------------
# 3. Edge Cases & Error Handling
# --------------------------------------------------------------------------

def test_preview_invalid_file_id():
    res = client.get("/api/documents/00000000-0000-0000-0000-000000000000/preview")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


def test_preview_invalid_page_numbers():
    pdf_bytes = create_test_pdf_bytes(pages=2)
    up_res = client.post(
        "/api/upload",
        files={"file": ("doc.pdf", pdf_bytes, "application/pdf")},
    )
    file_id = up_res.json()["file_id"]

    # Page 0 (fastapi Query ge=1 validation error -> 422)
    res_zero = client.get(f"/api/documents/{file_id}/preview?page=0")
    assert res_zero.status_code in [400, 422]

    # Page 999 (exceeds total pages -> 400)
    res_exceed = client.get(f"/api/documents/{file_id}/preview?page=999")
    assert res_exceed.status_code == 400
    assert "contains 2 page(s)" in res_exceed.json()["detail"]


def test_preview_corrupted_pdf(tmp_path):
    # Construct a file with valid PDF magic bytes '%PDF-1.4' but broken binary structure
    broken_pdf = b"%PDF-1.4\ncorrupted content that cannot be opened by pymupdf\n%%EOF"
    up_res = client.post(
        "/api/upload",
        files={"file": ("broken.pdf", broken_pdf, "application/pdf")},
    )
    assert up_res.status_code == 201
    file_id = up_res.json()["file_id"]

    # Metadata should indicate preview_available: false
    meta_res = client.get(f"/api/documents/{file_id}/metadata")
    assert meta_res.status_code == 200
    assert meta_res.json()["preview_available"] is False

    # Preview endpoint should return 422
    prev_res = client.get(f"/api/documents/{file_id}/preview?page=1")
    assert prev_res.status_code == 422
    assert "corrupted" in prev_res.json()["detail"].lower()


def test_preview_failure_does_not_break_analysis():
    """Confirms that preview errors or metadata failure do not block or crash document analysis."""
    pdf_bytes = create_test_pdf_bytes(pages=1, text_prefix="INCOME TAX DEPARTMENT PAN CARD ABCDE1234F")
    up_res = client.post(
        "/api/upload",
        files={"file": ("pan.pdf", pdf_bytes, "application/pdf")},
    )
    file_id = up_res.json()["file_id"]

    # Normal analysis should work seamlessly
    ana_res = client.post(f"/api/analyze/{file_id}")
    assert ana_res.status_code == 200
    data = ana_res.json()
    assert data["document_type"] == "PAN Card"
    assert data["verification_status"] in ["Unable to Verify", "Suspicious", "Likely Genuine"]


def test_upload_directory_not_publicly_accessible():
    """Security check: verify uploads folder is NOT served statically."""
    res = client.get("/uploads/any_file.pdf")
    assert res.status_code == 404

    res2 = client.get("/static/uploads/any_file.pdf")
    assert res2.status_code == 404
