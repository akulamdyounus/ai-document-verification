import io
from fastapi.testclient import TestClient
from backend.main import app
from backend.models.database import init_db
from PIL import Image

init_db()
client = TestClient(app)

def create_test_image_bytes() -> bytes:
    """Creates a simple valid in-memory PNG image."""
    img = Image.new("RGB", (200, 100), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert "ocr_available" in data
    assert "project_name" in data


def test_upload_invalid_extension():
    response = client.post(
        "/api/upload",
        files={"file": ("malicious.exe", b"fake binary content", "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "Unsupported file extension" in response.json()["detail"]


def test_upload_empty_file():
    response = client.post(
        "/api/upload",
        files={"file": ("empty.png", b"", "image/png")},
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_upload_spoofed_mime_type():
    # File named .png but header is not PNG/PDF/JPEG
    response = client.post(
        "/api/upload",
        files={"file": ("fake.png", b"plain text header not an image", "image/png")},
    )
    assert response.status_code == 400
    assert "File signature does not match" in response.json()["detail"]


def test_upload_and_analyze_flow():
    # 1. Upload valid PNG
    img_bytes = create_test_image_bytes()
    upload_res = client.post(
        "/api/upload",
        files={"file": ("sample_test.png", img_bytes, "image/png")},
    )
    assert upload_res.status_code == 201
    upload_data = upload_res.json()
    assert "file_id" in upload_data
    file_id = upload_data["file_id"]
    assert upload_data["original_filename"] == "sample_test.png"

    # 2. Analyze the uploaded document
    analyze_res = client.post(f"/api/analyze/{file_id}")
    assert analyze_res.status_code == 200
    analysis = analyze_res.json()

    assert analysis["file_id"] == file_id
    assert "document_type" in analysis
    assert "classification_confidence" in analysis
    assert analysis["verification_status"] == "Unable to Verify"
    assert "extracted_text" in analysis
    assert "fields" in analysis
    assert "findings" in analysis
    assert isinstance(analysis["findings"], list)


def test_analyze_nonexistent_file():
    response = client.post("/api/analyze/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
