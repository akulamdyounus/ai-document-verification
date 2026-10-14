import pytest
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

from backend.services.ocr_service import ocr_service, TesseractOCRService
from backend.services.pdf_service import pdf_service


def create_synthetic_text_image(text: str, width: int = 800, height: int = 200) -> Image.Image:
    """Helper to generate a clean synthetic text image."""
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((30, 60), text, fill=(0, 0, 0))
    return img


def test_upscale_image():
    """Verify that small images are upscaled to reach target OCR resolution."""
    small = np.zeros((300, 400, 3), dtype=np.uint8)
    scaled, scale = ocr_service.upscale_image(small, target_min_dim=1200)
    assert scale > 1.0
    assert max(scaled.shape[:2]) >= 1200


def test_upscale_image_large_preserved():
    """Large images should not be unnecessarily upscaled."""
    large = np.zeros((2000, 2000, 3), dtype=np.uint8)
    scaled, scale = ocr_service.upscale_image(large, target_min_dim=1800)
    assert scale == 1.0
    assert scaled.shape == large.shape


def test_enhance_contrast_and_sharpen():
    """Verify sharpening returns valid array of identical dimensions."""
    img = np.full((100, 100, 3), 128, dtype=np.uint8)
    sharpened = ocr_service.enhance_contrast_and_sharpen(img)
    assert sharpened.shape == img.shape
    assert sharpened.dtype == np.uint8


def test_apply_clahe():
    """Verify CLAHE equalization produces valid grayscale output."""
    gray = np.linspace(0, 255, 10000, dtype=np.uint8).reshape((100, 100))
    enhanced = ocr_service.apply_clahe(gray)
    assert enhanced.shape == gray.shape
    assert enhanced.dtype == np.uint8


def test_apply_adaptive_threshold():
    """Verify adaptive threshold produces binary 0/255 output."""
    gray = np.full((100, 100), 120, dtype=np.uint8)
    gray[40:60, 40:60] = 20
    thresh = ocr_service.apply_adaptive_threshold(gray)
    unique_vals = set(np.unique(thresh))
    assert unique_vals.issubset({0, 255})


def test_apply_otsu_threshold():
    """Verify Otsu threshold produces binary output."""
    gray = np.full((100, 100), 200, dtype=np.uint8)
    gray[30:70, 30:70] = 50
    thresh = ocr_service.apply_otsu_threshold(gray)
    unique_vals = set(np.unique(thresh))
    assert unique_vals.issubset({0, 255})


def test_deskew_image_straight():
    """Straight image should report ~0.0 angle."""
    img = np.full((200, 200, 3), 255, dtype=np.uint8)
    # Draw horizontal text-like bar
    cv2.rectangle(img, (20, 90), (180, 110), (0, 0, 0), -1)
    deskewed, angle = ocr_service.deskew_image(img)
    assert abs(angle) < 1.0


def test_generate_preprocessing_variants():
    """Verify multi-variant generation creates all 5 distinct candidate variants."""
    img = np.full((400, 600, 3), 255, dtype=np.uint8)
    cv2.putText(img, "TEST DOCUMENT", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
    variants = ocr_service.generate_preprocessing_variants(img)
    assert len(variants) == 5
    names = [v[0] for v in variants]
    assert "enhanced_color" in names
    assert "clahe" in names
    assert "adaptive_thresh" in names
    assert "otsu_thresh" in names
    assert "raw_scaled" in names


def test_score_text_quality():
    """Verify quality scoring rewards structured words and penalizes lone symbols."""
    high_quality = """
    Driving Licence
    Name : Johnathan Doe
    DOB : 15-08-1992
    License No : DL-0420110012345
    Address : 123 Main Street, City, 500001
    """
    sc_high = ocr_service.score_text_quality(high_quality, avg_conf=85.0)

    low_quality_colons = """
    :
    :
    :
    :
    Address:
    """
    sc_low = ocr_service.score_text_quality(low_quality_colons, avg_conf=30.0)

    assert sc_high > sc_low
    assert sc_high > 400.0


def test_determine_document_source_type_image(tmp_path):
    """Image files should be classified as 'image'."""
    img_path = tmp_path / "sample.jpg"
    img = Image.new("RGB", (200, 200), color=(255, 255, 255))
    img.save(img_path)

    source_type, text = pdf_service.determine_document_source_type(img_path)
    assert source_type == "image"
    assert text == ""


@pytest.mark.skipif(not ocr_service.is_available(), reason="Tesseract OCR not installed")
def test_extract_text_with_diagnostics():
    """Verify OCR extracts text and generates comprehensive diagnostics."""
    pil_img = create_synthetic_text_image("Driving Licence Name : Sarah Connor DOB : 12/03/1985")
    text, diag = ocr_service.extract_text_with_diagnostics(pil_img)

    assert "Driving" in text or "Licence" in text or "Sarah" in text
    assert diag is not None
    assert "preprocessing_method" in diag
    assert "psm_used" in diag
    assert "extracted_character_count" in diag
    assert diag["extracted_character_count"] > 0
