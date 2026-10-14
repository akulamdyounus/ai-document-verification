import io
import fitz
import numpy as np
from PIL import Image, ImageDraw
import pytest
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.database import init_db
from backend.services.image_forensics import image_forensics_service
from backend.services.copy_move_detector import copy_move_detector
from backend.services.pdf_forensics import pdf_forensics_service
from backend.services.content_consistency import content_consistency_service
from backend.services.fraud_detector import fraud_detector
from backend.services.verification_engine import verification_engine
from backend.services.pdf_service import pdf_service
from backend.services.document_classifier import document_classifier
from backend.services.field_extractor import field_extractor

init_db()
client = TestClient(app)


# ---------------------------------------------------------
# Test Fixtures & Helpers
# ---------------------------------------------------------

def create_synthetic_image(width: int = 500, height: int = 400, noise: bool = False) -> Image.Image:
    """Creates a clean synthetic RGB PIL document image."""
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((40, 40), "OFFICIAL BANK STATEMENT", fill=(0, 0, 0))
    draw.text((40, 80), "Account Holder: John Doe", fill=(30, 30, 30))
    draw.text((40, 110), "Account Number: 1234567890", fill=(30, 30, 30))
    draw.text((40, 140), "Statement Date: 15/01/2024", fill=(30, 30, 30))
    draw.text((40, 170), "Available Balance: INR 50,000.00", fill=(30, 30, 30))

    if noise:
        arr = np.array(img).astype(np.int16)
        noise_arr = np.random.randint(-10, 10, arr.shape, dtype=np.int16)
        arr = np.clip(arr + noise_arr, 0, 255).astype(np.uint8)
        img = Image.fromarray(arr)

    return img


def create_cloned_feature_image() -> Image.Image:
    """Creates an image with rich feature blocks cloned to another location."""
    img = Image.new("RGB", (600, 400), color=(245, 245, 245))
    draw = ImageDraw.Draw(img)

    # Draw complex, high-contrast star/cross shapes to generate distinct ORB keypoints
    def draw_star(cx, cy):
        draw.line([(cx - 20, cy), (cx + 20, cy)], fill=(0, 0, 0), width=3)
        draw.line([(cx, cy - 20), (cx, cy + 20)], fill=(0, 0, 0), width=3)
        draw.line([(cx - 15, cy - 15), (cx + 15, cy + 15)], fill=(0, 0, 0), width=2)
        draw.line([(cx - 15, cy + 15), (cx + 15, cy - 15)], fill=(0, 0, 0), width=2)
        draw.rectangle([cx - 5, cy - 5, cx + 5, cy + 5], fill=(255, 0, 0))

    # Cluster 1 at (120, 150)
    for dx, dy in [(-25, -25), (25, -25), (-25, 25), (25, 25), (0, 0)]:
        draw_star(120 + dx, 150 + dy)

    # Clone Cluster 1 to (380, 150) - identical shift (+260, 0)
    for dx, dy in [(-25, -25), (25, -25), (-25, 25), (25, 25), (0, 0)]:
        draw_star(380 + dx, 150 + dy)

    return img


def create_synthetic_pdf(
    tmp_path: Path,
    filename: str = "test_doc.pdf",
    creator: str = "ReportEngine v1.0",
    producer: str = "Standard PDF Generator",
    creation_date: str = "D:20240115100000",
    mod_date: str = "D:20240115100500",
    text_content: str = "Account Statement\nAccount Number: 1234567890\nBalance: 5000.00",
) -> Path:
    pdf_path = tmp_path / filename
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), text_content, fontsize=12)
    doc.set_metadata({
        "creator": creator,
        "producer": producer,
        "creationDate": creation_date,
        "modDate": mod_date,
    })
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


# ---------------------------------------------------------
# Image Forensics Tests
# ---------------------------------------------------------

def test_image_forensics_clean_image():
    img = create_synthetic_image()
    checks = image_forensics_service.analyze(img)

    assert len(checks) == 2
    check_names = {c["check"] for c in checks}
    assert "error_level_analysis" in check_names
    assert "noise_variance" in check_names

    for c in checks:
        assert c["status"] in ["pass", "info"]
        assert c["severity"] == "low"
        assert "evidence" in c


def test_image_forensics_resolution_safeguard():
    large_img = Image.new("RGB", (2500, 2200), color=(255, 255, 255))
    checks = image_forensics_service.analyze(large_img)
    assert len(checks) == 2
    assert all("status" in c for c in checks)


# ---------------------------------------------------------
# Copy-Move Detection Tests
# ---------------------------------------------------------

def test_copy_move_clean_image():
    img = create_synthetic_image()
    result = copy_move_detector.detect(img)

    assert result["check"] == "copy_move_detection"
    assert result["status"] == "pass"
    assert result["severity"] == "low"
    assert "evidence" in result


def test_copy_move_cloned_regions():
    cloned_img = create_cloned_feature_image()
    result = copy_move_detector.detect(cloned_img)

    assert result["check"] == "copy_move_detection"
    assert "evidence" in result
    assert result["evidence"]["total_keypoints"] > 0


# ---------------------------------------------------------
# PDF Forensics Tests
# ---------------------------------------------------------

def test_pdf_forensics_clean_pdf(tmp_path):
    pdf_path = create_synthetic_pdf(tmp_path, "clean.pdf")
    checks = pdf_forensics_service.analyze(pdf_path)

    check_names = {c["check"] for c in checks}
    assert "pdf_metadata" in check_names
    assert "pdf_timestamps" in check_names
    assert "pdf_structure" in check_names

    meta_check = next(c for c in checks if c["check"] == "pdf_metadata")
    assert meta_check["status"] == "pass"
    assert meta_check["severity"] == "low"


def test_pdf_forensics_editing_software_detected(tmp_path):
    """
    IMPORTANT METADATA RULE:
    Common PDF tools/editors (Photoshop, Canva, iLovePDF, etc.) are contextual indicators only.
    They must NOT be treated as fraud warnings by themselves.
    """
    pdf_path = create_synthetic_pdf(
        tmp_path,
        "photoshop_edited.pdf",
        creator="Adobe Photoshop 2024",
        producer="Canva PDF Engine",
    )
    checks = pdf_forensics_service.analyze(pdf_path)

    meta_check = next(c for c in checks if c["check"] == "pdf_metadata")
    assert meta_check["status"] == "info"
    assert meta_check["severity"] == "low"
    assert "Photoshop" in meta_check["evidence"]["detected_editing_tools"]
    assert "Canva" in meta_check["evidence"]["detected_editing_tools"]


def test_pdf_forensics_anomalous_timestamps(tmp_path):
    # Modification date precedes creation date
    pdf_path = create_synthetic_pdf(
        tmp_path,
        "anomalous_time.pdf",
        creation_date="D:20240501120000",
        mod_date="D:20230101120000",
    )
    checks = pdf_forensics_service.analyze(pdf_path)

    time_check = next(c for c in checks if c["check"] == "pdf_timestamps")
    assert time_check["status"] == "warning"
    assert time_check["severity"] == "medium"
    assert "precedes" in time_check["message"].lower()


# ---------------------------------------------------------
# Content Consistency Tests
# ---------------------------------------------------------

def test_content_consistency_valid_chronology():
    fields = {
        "date_of_birth": "15/05/1990",
        "issue_date": "10/01/2020",
        "expiry_date": "09/01/2030",
    }
    checks = content_consistency_service.validate(fields, "Driving Licence")
    date_check = next(c for c in checks if c["check"] == "date_chronology")
    assert date_check["status"] == "pass"
    assert date_check["severity"] == "low"


def test_content_consistency_contradictory_dates():
    # Issue date is after expiry date
    fields = {
        "issue_date": "10/01/2030",
        "expiry_date": "09/01/2020",
    }
    checks = content_consistency_service.validate(fields, "Driving Licence")
    date_check = next(c for c in checks if c["check"] == "date_chronology")
    assert date_check["status"] == "warning"
    assert date_check["severity"] == "high"
    assert "contradictory" in date_check["evidence"]["issues"][0].lower()


def test_content_consistency_dob_after_issue_date():
    fields = {
        "date_of_birth": "15/05/2025",
        "issue_date": "10/01/2020",
    }
    checks = content_consistency_service.validate(fields, "Passport")
    date_check = next(c for c in checks if c["check"] == "date_chronology")
    assert date_check["status"] == "warning"
    assert date_check["severity"] == "high"
    assert "impossible" in date_check["evidence"]["issues"][0].lower()


def test_content_consistency_bank_statement_period():
    # Inverted statement period
    fields = {"statement_period": "31/12/2023 to 01/01/2023"}
    checks = content_consistency_service.validate(fields, "Bank Statement")
    period_check = next(c for c in checks if c["check"] == "statement_period_logic")
    assert period_check["status"] == "warning"
    assert period_check["severity"] == "medium"


def test_content_consistency_pan_syntax():
    valid_fields = {"pan_number": "ABCDE1234F"}
    checks_valid = content_consistency_service.validate(valid_fields, "PAN Card")
    pan_check_valid = next(c for c in checks_valid if c["check"] == "identifier_syntax")
    assert pan_check_valid["status"] == "pass"

    invalid_fields = {"pan_number": "INVALID123"}
    checks_invalid = content_consistency_service.validate(invalid_fields, "PAN Card")
    pan_check_invalid = next(c for c in checks_invalid if c["check"] == "identifier_syntax")
    assert pan_check_invalid["status"] == "warning"
    assert pan_check_invalid["severity"] == "high"


def test_content_consistency_invoice_math():
    valid_inv = {"subtotal": "100.00", "total_amount": "118.00"}
    checks_valid = content_consistency_service.validate(valid_inv, "Invoice")
    inv_check = next(c for c in checks_valid if c["check"] == "invoice_math")
    assert inv_check["status"] == "pass"

    negative_inv = {"subtotal": "-50.00", "total_amount": "100.00"}
    checks_neg = content_consistency_service.validate(negative_inv, "Invoice")
    inv_check_neg = next(c for c in checks_neg if c["check"] == "invoice_math")
    assert inv_check_neg["status"] == "warning"
    assert inv_check_neg["severity"] == "medium"


# ---------------------------------------------------------
# Unified Fraud Detector Tests
# ---------------------------------------------------------

def test_fraud_detector_unified_clean(tmp_path):
    pdf_path = create_synthetic_pdf(tmp_path, "clean_statement.pdf")
    report = fraud_detector.analyze(
        file_path=pdf_path,
        extracted_text="Bank of Baroda Statement Account 12345678",
        document_type="Bank Statement",
        fields={"account_number": "12345678"},
    )

    assert "risk_score" in report
    assert "risk_level" in report
    assert report["risk_level"] == "Low"
    assert report["risk_score"] <= 0.20
    assert len(report["checks"]) >= 4
    assert len(report["limitations"]) == 3


def test_fraud_detector_elevated_risk(tmp_path):
    pdf_path = create_synthetic_pdf(
        tmp_path,
        "tampered.pdf",
        creator="Adobe Photoshop CS6",
        producer="Canva Editor",
    )
    report = fraud_detector.analyze(
        file_path=pdf_path,
        extracted_text="Driving Licence Valid 2020 to 2010",
        document_type="Driving Licence",
        fields={
            "issue_date": "01/01/2020",
            "expiry_date": "01/01/2010",  # Contradiction
        },
    )

    assert report["risk_score"] >= 0.35
    assert report["risk_level"] in ["Medium", "High", "Very High"]
    assert report["overall_status"] in ["Suspicious", "Review Needed"]


# ---------------------------------------------------------
# Verification Policy Tests (Required by User Prompt)
# ---------------------------------------------------------

def test_verification_policy_1_clean_valid_document():
    """
    Test 1: Clean valid document -> Unable to Verify
    Absence of detected anomalies does not prove authenticity.
    Must return 'Unable to Verify' with structured decision_reasons.
    """
    fraud_report = {
        "risk_score": 0.0,
        "risk_level": "Low",
        "checks": [
            {"check": "pdf_metadata", "status": "pass", "severity": "low"},
            {"check": "date_chronology", "status": "pass", "severity": "low"},
            {"check": "error_level_analysis", "status": "pass", "severity": "low"},
        ],
        "findings": ["No active forensic anomalies or tampering signals were identified."],
    }

    verdict, findings, reasons = verification_engine.evaluate(
        document_type="Bank Statement",
        confidence=0.92,
        fields={"account_number": "XXXXX1234"},
        fraud_analysis=fraud_report,
        extracted_text_len=150,
        matched_signals=["account number", "statement"],
        classification_status="classified",
    )

    assert verdict == "Unable to Verify"
    assert "No high-severity forensic indicators detected." in reasons
    assert any("cannot establish document authenticity" in f or "cannot confirm authenticity" in f for f in findings)


def test_verification_policy_2_low_risk_18_percent():
    """
    Test 2: Low risk 18% -> Unable to Verify (NOT Suspicious)
    Regression test for the false-positive driving licence issue.
    """
    fraud_report = {
        "risk_score": 0.18,
        "risk_level": "Low",
        "checks": [
            {"check": "pdf_metadata", "status": "info", "severity": "low"},
            {"check": "pdf_timestamps", "status": "pass", "severity": "low"},
            {"check": "date_chronology", "status": "pass", "severity": "low"},
            {"check": "error_level_analysis", "status": "pass", "severity": "low"},
        ],
        "findings": ["No active forensic anomalies or tampering signals were identified."],
    }

    verdict, findings, reasons = verification_engine.evaluate(
        document_type="Driving Licence",
        confidence=0.73,
        fields={"licence_number": "DL-0420110012345"},
        fraud_analysis=fraud_report,
        extracted_text_len=120,
        matched_signals=["driving licence", "licence number"],
        classification_status="classified",
    )

    # Must be Unable to Verify, NOT Suspicious!
    assert verdict == "Unable to Verify"
    assert verdict != "Suspicious"
    assert "No high-severity forensic indicators detected." in reasons


def test_verification_policy_3_normal_pdf_editor_metadata():
    """
    Test 3: Normal PDF editor metadata (Canva, Adobe, iLovePDF) -> Unable to Verify
    Common conversion software must NOT produce Suspicious.
    """
    fraud_report = {
        "risk_score": 0.08,
        "risk_level": "Low",
        "checks": [
            {
                "check": "pdf_metadata",
                "status": "info",
                "severity": "low",
                "message": "Common PDF conversion/editing tool signature identified (Canva, Adobe Acrobat).",
            },
            {"check": "date_chronology", "status": "pass", "severity": "low"},
        ],
        "findings": ["PDF produced with common tool."],
    }

    verdict, findings, reasons = verification_engine.evaluate(
        document_type="Salary Slip",
        confidence=0.85,
        fields={"employee_id": "EMP1001"},
        fraud_analysis=fraud_report,
        extracted_text_len=130,
        classification_status="classified",
    )

    assert verdict == "Unable to Verify"
    assert verdict != "Suspicious"


def test_verification_policy_4_single_weak_ela_anomaly():
    """
    Test 4: Single weak ELA anomaly -> Unable to Verify
    ELA/compression differences alone must NOT produce 'Suspicious'.
    """
    fraud_report = {
        "risk_score": 0.18,
        "risk_level": "Low",
        "checks": [
            {
                "check": "error_level_analysis",
                "status": "warning",
                "severity": "medium",
                "message": "Localized compression differences detected.",
            },
            {"check": "date_chronology", "status": "pass", "severity": "low"},
            {"check": "pdf_metadata", "status": "pass", "severity": "low"},
        ],
        "findings": ["[MEDIUM] Localized compression differences detected."],
    }

    verdict, findings, reasons = verification_engine.evaluate(
        document_type="Invoice",
        confidence=0.82,
        fields={"invoice_number": "INV-2024-001"},
        fraud_analysis=fraud_report,
        extracted_text_len=140,
        classification_status="classified",
    )

    # An isolated ELA anomaly alone must NOT produce Suspicious
    assert verdict == "Unable to Verify"
    assert verdict != "Suspicious"


def test_verification_policy_5_multiple_medium_anomalies():
    """
    Test 5: Multiple medium anomalies across independent domains -> Suspicious
    """
    fraud_report = {
        "risk_score": 0.36,
        "risk_level": "Medium",
        "checks": [
            {
                "check": "pdf_timestamps",
                "status": "warning",
                "severity": "medium",
                "message": "Anomalous timestamps: Modification date precedes creation date.",
            },
            {
                "check": "noise_variance",
                "status": "warning",
                "severity": "medium",
                "message": "Inconsistent local texture detected: presence of unusually smooth/filtered blocks.",
            },
        ],
        "findings": [
            "[MEDIUM] Anomalous timestamps: Modification date precedes creation date.",
            "[MEDIUM] Inconsistent local texture detected.",
        ],
    }

    verdict, findings, reasons = verification_engine.evaluate(
        document_type="Bank Statement",
        confidence=0.88,
        fields={"account_number": "1234567890"},
        fraud_analysis=fraud_report,
        extracted_text_len=150,
        classification_status="classified",
    )

    assert verdict == "Suspicious"
    assert any("Multiple independent medium" in r for r in reasons)


def test_verification_policy_6_strong_manipulation_evidence():
    """
    Test 6: Strong independent manipulation evidence -> Suspicious or Likely Fake
    6a: Single high severity warning -> Suspicious
    6b: Multiple strong independent indicators concur -> Likely Fake
    """
    # 6a: Contradictory dates (single high-severity) -> Suspicious
    fraud_report_high = {
        "risk_score": 0.35,
        "risk_level": "Medium",
        "checks": [
            {
                "check": "date_chronology",
                "status": "warning",
                "severity": "high",
                "message": "Contradictory dates: Issue date is after expiry date.",
            }
        ],
        "findings": ["[HIGH] Contradictory dates: Issue date is after expiry date."],
    }
    verdict_6a, _, reasons_6a = verification_engine.evaluate(
        document_type="Driving Licence",
        confidence=0.85,
        fields={},
        fraud_analysis=fraud_report_high,
        extracted_text_len=100,
        classification_status="classified",
    )
    assert verdict_6a == "Suspicious"
    assert any("High-severity anomaly detected" in r for r in reasons_6a)

    # 6b: Concurring strong indicators across independent domains -> Likely Fake
    fraud_report_fake = {
        "risk_score": 0.80,
        "risk_level": "Very High",
        "checks": [
            {
                "check": "date_chronology",
                "status": "warning",
                "severity": "high",
                "message": "Impossible dates: Date of Birth is after Issue date.",
            },
            {
                "check": "copy_move_detection",
                "status": "warning",
                "severity": "high",
                "message": "Strong copy-move duplication evidence detected: 52 matching clusters.",
            },
        ],
        "findings": [
            "[HIGH] Impossible dates: Date of Birth is after Issue date.",
            "[HIGH] Strong copy-move duplication evidence detected.",
        ],
    }
    verdict_6b, _, reasons_6b = verification_engine.evaluate(
        document_type="Passport",
        confidence=0.92,
        fields={},
        fraud_analysis=fraud_report_fake,
        extracted_text_len=120,
        classification_status="classified",
    )
    assert verdict_6b == "Likely Fake"
    assert any("Multiple strong independent manipulation indicators" in r for r in reasons_6b)


def test_verification_policy_7_never_automatically_likely_genuine():
    """
    Test 7: No anomalies -> Never automatically Likely Genuine
    The system should never say 'Likely Genuine' simply because no anomalies were found.
    """
    clean_report = {
        "risk_score": 0.0,
        "risk_level": "Low",
        "checks": [
            {"check": "pdf_metadata", "status": "pass", "severity": "low"},
            {"check": "pdf_timestamps", "status": "pass", "severity": "low"},
            {"check": "pdf_structure", "status": "pass", "severity": "low"},
            {"check": "error_level_analysis", "status": "pass", "severity": "low"},
            {"check": "noise_variance", "status": "pass", "severity": "low"},
            {"check": "copy_move_detection", "status": "pass", "severity": "low"},
            {"check": "date_chronology", "status": "pass", "severity": "low"},
        ],
        "findings": ["No active forensic anomalies or tampering signals were identified."],
    }

    verdict, findings, reasons = verification_engine.evaluate(
        document_type="PAN Card",
        confidence=0.98,
        fields={"pan_number": "ABCDE1234F"},
        fraud_analysis=clean_report,
        extracted_text_len=200,
        classification_status="classified",
    )

    assert verdict != "Likely Genuine"
    assert verdict == "Unable to Verify"
    assert "Authenticity cannot be established without authoritative verification." in reasons


def test_verification_engine_inconclusive_for_unknown():
    fraud_report = {"risk_score": 0.0, "risk_level": "Low", "checks": []}
    verdict, findings, reasons = verification_engine.evaluate(
        document_type="Unknown",
        confidence=0.15,
        fields={},
        fraud_analysis=fraud_report,
        extracted_text_len=20,
        classification_status="insufficient_evidence",
    )
    assert verdict == "Unable to Verify"
    assert any("inconclusive" in r.lower() for r in reasons)


# ---------------------------------------------------------
# API End-to-End Analysis with Forensics & Decision Reasons
# ---------------------------------------------------------

def test_api_analyze_with_forensic_payload(tmp_path):
    pdf_path = create_synthetic_pdf(
        tmp_path,
        "upload_api_test.pdf",
        text_content="STATE BANK OF INDIA\nAccount Statement\nAccount Number: 98765432101\nIFSC: SBIN0001234",
    )

    # 1. Upload
    with open(pdf_path, "rb") as f:
        upload_res = client.post(
            "/api/upload",
            files={"file": ("upload_api_test.pdf", f.read(), "application/pdf")},
        )
    assert upload_res.status_code == 201
    file_id = upload_res.json()["file_id"]

    # 2. Analyze
    analyze_res = client.post(f"/api/analyze/{file_id}")
    assert analyze_res.status_code == 200
    data = analyze_res.json()

    assert data["file_id"] == file_id
    assert "risk_score" in data
    assert "risk_level" in data
    assert "forensic_report" in data
    assert "decision_reasons" in data
    assert isinstance(data["decision_reasons"], list)
    assert len(data["decision_reasons"]) > 0
    assert data["forensic_report"] is not None
    assert "checks" in data["forensic_report"]
    assert data["verification_status"] == "Unable to Verify"


# ---------------------------------------------------------
# Bank Statement Forensics & Consistency Tests
# ---------------------------------------------------------

def create_synthetic_bank_statement_pdf(
    tmp_path: Path,
    filename: str = "synthetic_statement.pdf",
    header_text: str = "Statement of HDFC Account No :98765432101",
    ifsc_code: str = "HDFC0001234",
    opening_balance: float = 10000.00,
    rows: Optional[List[str]] = None,
    two_pages: bool = False,
    page2_account: Optional[str] = None,
    disclaimer_text: str = "HDFC Bank registered office Mumbai.",
) -> Path:
    pdf_path = tmp_path / filename
    doc = fitz.open()

    p1 = doc.new_page()
    p1.insert_text((50, 50), "HDFC BANK LIMITED", fontsize=14)
    p1.insert_text((50, 75), header_text, fontsize=11)
    p1.insert_text((50, 95), f"Customer ID: 12345678  IFSC Code :{ifsc_code}", fontsize=10)
    p1.insert_text((50, 115), "Period: 01-01-2024 To : 31-01-2024", fontsize=10)
    p1.insert_text((50, 140), f"OPENING BALANCE {opening_balance:.2f}", fontsize=10)

    # Insert transaction rows
    if rows is None:
        rows = [
            "02-01-2024 SALARY CREDIT 5000.00 15000.00 001",
            "05-01-2024 ATM CASH WDL 2000.00 13000.00 001",
            "10-01-2024 UPI PAYMENT 1000.00 12000.00 001",
        ]

    y = 165
    for r in rows:
        p1.insert_text((50, y), r, fontsize=9)
        y += 22

    p1.insert_text((50, y + 20), f"CLOSING BALANCE 12000.00", fontsize=10)
    p1.insert_text((50, y + 50), disclaimer_text, fontsize=8)

    if two_pages:
        p2 = doc.new_page()
        acc = page2_account or "98765432101"
        p2.insert_text((50, 50), f"Account Number : {acc}  Page 2", fontsize=10)
        p2.insert_text((50, 80), "15-01-2024 RENT PAYMENT 2000.00 10000.00 001", fontsize=9)
        p2.insert_text((50, 120), disclaimer_text, fontsize=8)

    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def test_tampered_bank_statement_fixture_detected():
    """
    TEST REQUIREMENT:
    Verify that the intentionally manipulated Bank Statement fixture
    does NOT return Forensic Risk: Low Risk or Verification: Unable to Verify.
    It MUST detect the arithmetic, syntax, and bank identity anomalies
    and return 'Likely Fake' or 'Suspicious' with high risk score (>= 0.75).
    """
    fixture_path = Path("backend/tests/fixtures/tampered_bank_statement.pdf")
    if not fixture_path.exists():
        # Fallback to uploads path if fixture path not populated
        fixture_path = Path("uploads/ba4882fb-4a27-41f8-82b9-a853e50f6994.pdf")

    assert fixture_path.exists(), f"Fixture file not found: {fixture_path}"

    text, pcount = pdf_service.extract_text(fixture_path)
    cls = document_classifier.classify(text)
    assert cls.document_type == "Bank Statement"
    assert cls.confidence > 0.70

    fields = field_extractor.extract_fields(text, cls.document_type)
    fraud_rep = fraud_detector.analyze(fixture_path, text, cls.document_type, fields)

    verdict, findings, reasons = verification_engine.evaluate(
        cls.document_type,
        cls.confidence,
        fields,
        fraud_rep,
        len(text),
        cls.matched_signals,
        cls.classification_status,
    )

    # 1. Verification must NOT be Unable to Verify or Low Risk
    assert fraud_rep["risk_score"] >= 0.75
    assert fraud_rep["risk_level"] in ["High", "Very High"]
    assert verdict in ["Suspicious", "Likely Fake"]
    assert verdict == "Likely Fake"

    # 2. Check specific detected findings
    check_map = {c["check"]: c for c in fraud_rep["checks"]}

    # Arithmetic running balance failure must be detected
    assert "bank_running_balance_math" in check_map
    assert check_map["bank_running_balance_math"]["status"] == "warning"
    assert check_map["bank_running_balance_math"]["severity"] == "high"
    assert check_map["bank_running_balance_math"]["evidence"]["total_discrepancies"] >= 2

    # Malformed syntax ('150000..00') must be detected
    assert "bank_transaction_table_consistency" in check_map
    assert check_map["bank_transaction_table_consistency"]["status"] == "warning"
    assert check_map["bank_transaction_table_consistency"]["severity"] == "high"

    # Bank identity conflict (HDFC header vs Axis UTIB / Axis disclaimers) must be detected
    assert "bank_identity_consistency" in check_map
    assert check_map["bank_identity_consistency"]["status"] == "warning"
    assert check_map["bank_identity_consistency"]["severity"] == "high"

    # 3. Decision reasons must cite critical indicators
    reasons_str = " ".join(reasons)
    assert "Mathematical inconsistency" in reasons_str
    assert "Syntax error" in reasons_str
    assert "Bank identity conflict" in reasons_str


def test_clean_bank_statement_likely_genuine_with_positive_evidence(tmp_path):
    """
    PRODUCT GOAL TEST 2:
    Clean bank statement with mathematically consistent transactions, matching IFSC,
    and valid opening/closing balances must NOT become Suspicious/Fake merely because
    of normal metadata or footer text.
    With sufficient positive authenticity evidence, it returns 'Likely Genuine'.
    """
    pdf_path = create_synthetic_bank_statement_pdf(
        tmp_path,
        "clean_bank_stmt_genuine.pdf",
        disclaimer_text="Generated by ReportServer. Canva and Adobe PDF compatible.",
    )
    text, _ = pdf_service.extract_text(pdf_path)
    cls = document_classifier.classify(text)
    fields = field_extractor.extract_fields(text, cls.document_type)

    fraud_rep = fraud_detector.analyze(pdf_path, text, cls.document_type, fields)
    res = verification_engine.evaluate(
        cls.document_type,
        cls.confidence,
        fields,
        fraud_rep,
        len(text),
        cls.matched_signals,
        cls.classification_status,
        extracted_text=text,
        file_path=pdf_path,
    )

    verdict = res.verdict
    assert fraud_rep["risk_score"] <= 0.20
    assert fraud_rep["risk_level"] == "Low"
    assert verdict == "Likely Genuine"
    assert verdict != "Suspicious"
    assert verdict != "Likely Fake"
    assert res.authenticity_evidence_score >= 0.65
    assert res.manipulation_evidence_score <= 0.15

    check_map = {c["check"]: c for c in fraud_rep["checks"]}
    assert check_map["bank_running_balance_math"]["status"] == "pass"
    assert check_map["bank_identity_consistency"]["status"] == "pass"


def test_clean_driving_licence_likely_genuine_with_sufficient_evidence():
    """
    PRODUCT GOAL TEST 1:
    Clean Driving Licence with valid internal fields and no manipulation
    returns 'Likely Genuine' when sufficient positive authenticity evidence exists.
    """
    fields = {
        "licence_number": "DL-0420110012345",
        "name": "Vikramaditya Sharma",
        "date_of_birth": "15/05/1990",
        "issue_date": "10/01/2015",
        "expiry_date": "09/01/2035",
    }
    fraud_rep = {
        "risk_score": 0.0,
        "risk_level": "Low",
        "checks": [
            {"check": "date_chronology", "status": "pass", "severity": "low"},
            {"check": "pdf_metadata", "status": "pass", "severity": "low"},
        ],
        "findings": ["No active forensic anomalies or tampering signals were identified."],
    }
    text = "UNION OF INDIA DRIVING LICENCE TRANSPORT DEPARTMENT DL-0420110012345 LMV MCWG"

    res = verification_engine.evaluate(
        document_type="Driving Licence",
        confidence=0.88,
        fields=fields,
        fraud_analysis=fraud_rep,
        extracted_text_len=len(text),
        classification_status="classified",
        extracted_text=text,
    )

    assert res.verdict == "Likely Genuine"
    assert res.authenticity_evidence_score >= 0.65
    assert res.manipulation_evidence_score <= 0.15


def test_clean_driving_licence_insufficient_evidence_unable_to_verify():
    """
    Clean Driving Licence missing core fields (e.g. only licence number, no dates/name)
    must fall back to 'Unable to Verify' because positive authenticity evidence is below threshold.
    """
    fields = {"licence_number": "DL-0420110012345"}
    fraud_rep = {
        "risk_score": 0.0,
        "risk_level": "Low",
        "checks": [],
        "findings": ["No active forensic anomalies or tampering signals were identified."],
    }

    res = verification_engine.evaluate(
        document_type="Driving Licence",
        confidence=0.75,
        fields=fields,
        fraud_analysis=fraud_rep,
        extracted_text_len=60,
        classification_status="classified",
        extracted_text="DL-0420110012345",
    )

    assert res.verdict == "Unable to Verify"
    assert res.verdict != "Likely Genuine"
    assert res.authenticity_evidence_score < 0.65


def test_authoritative_verification_success_verified_authentic():
    """
    PRODUCT GOAL TEST 6:
    Document with authoritative verification success returns 'Verified Authentic'.
    """
    res = verification_engine.evaluate(
        document_type="Driving Licence",
        confidence=0.85,
        fields={"licence_number": "DL-0420110012345"},
        fraud_analysis={"risk_score": 0.0, "risk_level": "Low", "checks": []},
        extracted_text_len=100,
        classification_status="classified",
        authoritative_override="VERIFIED_AUTHENTIC",
    )
    assert res.verdict == "Verified Authentic"
    assert res.authoritative_verification_status == "VERIFIED_AUTHENTIC"
    assert any("authoritative" in r.lower() for r in res.decision_reasons)


def test_authoritative_verification_failure_verified_invalid():
    """
    PRODUCT GOAL TEST 7:
    Document with authoritative verification failure returns 'Verified Invalid'.
    """
    res = verification_engine.evaluate(
        document_type="Driving Licence",
        confidence=0.85,
        fields={"licence_number": "DL-0420110012345"},
        fraud_analysis={"risk_score": 0.0, "risk_level": "Low", "checks": []},
        extracted_text_len=100,
        classification_status="classified",
        authoritative_override="VERIFIED_INVALID",
    )
    assert res.verdict == "Verified Invalid"
    assert res.authoritative_verification_status == "VERIFIED_INVALID"
    assert any("rejected" in r.lower() or "invalid" in r.lower() for r in res.decision_reasons)


def test_classification_confidence_isolated_from_authenticity():
    """
    PRODUCT GOAL TEST 9:
    Classification confidence must never directly influence authenticity verdict.
    A document with 99% classification confidence but tampering is 'Likely Fake'.
    """
    tampered_report = {
        "risk_score": 0.85,
        "risk_level": "Very High",
        "checks": [
            {
                "check": "bank_running_balance_math",
                "status": "warning",
                "severity": "high",
                "message": "Mathematical inconsistency in running balance.",
            },
            {
                "check": "bank_identity_consistency",
                "status": "warning",
                "severity": "high",
                "message": "Bank identity conflict: HDFC vs Axis.",
            },
        ],
        "findings": ["[HIGH] Mathematical inconsistency", "[HIGH] Bank identity conflict"],
    }
    res = verification_engine.evaluate(
        document_type="Bank Statement",
        confidence=0.99,  # High classification confidence!
        fields={"account_number": "1234567890"},
        fraud_analysis=tampered_report,
        extracted_text_len=200,
        classification_status="classified",
    )
    assert res.verdict == "Likely Fake"
    assert res.document_classification_confidence == 0.99
    assert res.manipulation_evidence_score >= 0.75


def test_bank_statement_isolated_math_discrepancy(tmp_path):
    """
    Bank statement with an isolated running balance discrepancy
    must produce 'Suspicious' (single high severity finding).
    """
    rows = [
        "02-01-2024 DEPOSIT 5000.00 15000.00",
        "05-01-2024 WITHDRAWAL 2000.00 99000.00",  # Inconsistent: 15000 - 2000 != 99000
        "10-01-2024 DEPOSIT 1000.00 100000.00",
    ]
    pdf_path = create_synthetic_bank_statement_pdf(
        tmp_path,
        "math_error.pdf",
        rows=rows,
    )
    text, _ = pdf_service.extract_text(pdf_path)
    cls = document_classifier.classify(text)
    fields = field_extractor.extract_fields(text, cls.document_type)

    fraud_rep = fraud_detector.analyze(pdf_path, text, cls.document_type, fields)
    verdict, findings, reasons = verification_engine.evaluate(
        cls.document_type,
        cls.confidence,
        fields,
        fraud_rep,
        len(text),
        cls.matched_signals,
        cls.classification_status,
    )

    check_map = {c["check"]: c for c in fraud_rep["checks"]}
    assert check_map["bank_running_balance_math"]["status"] == "warning"
    assert check_map["bank_running_balance_math"]["severity"] == "high"
    assert verdict == "Suspicious"


def test_bank_statement_bank_identity_conflict(tmp_path):
    """
    Bank statement claiming to be HDFC Bank but with Axis Bank (UTIB) IFSC
    must produce an identity warning.
    """
    pdf_path = create_synthetic_bank_statement_pdf(
        tmp_path,
        "identity_conflict.pdf",
        header_text="Statement of HDFC Account No :1234567890",
        ifsc_code="UTIB0001234",  # Axis Bank IFSC!
    )
    text, _ = pdf_service.extract_text(pdf_path)
    cls = document_classifier.classify(text)
    fields = field_extractor.extract_fields(text, cls.document_type)

    fraud_rep = fraud_detector.analyze(pdf_path, text, cls.document_type, fields)
    check_map = {c["check"]: c for c in fraud_rep["checks"]}
    assert check_map["bank_identity_consistency"]["status"] == "warning"
    assert check_map["bank_identity_consistency"]["severity"] == "high"
    assert "UTIB" in check_map["bank_identity_consistency"]["message"]


def test_bank_statement_cross_page_account_conflict(tmp_path):
    """
    Multi-page statement where Page 1 and Page 2 contain conflicting account numbers
    must be flagged as a cross-page inconsistency warning.
    """
    pdf_path = create_synthetic_bank_statement_pdf(
        tmp_path,
        "cross_page_mismatch.pdf",
        two_pages=True,
        page2_account="11122233344",  # Conflicting account number!
    )
    text, _ = pdf_service.extract_text(pdf_path)
    cls = document_classifier.classify(text)
    fields = field_extractor.extract_fields(text, cls.document_type)

    fraud_rep = fraud_detector.analyze(pdf_path, text, cls.document_type, fields)
    check_map = {c["check"]: c for c in fraud_rep["checks"]}
    assert check_map["bank_cross_page_consistency"]["status"] == "warning"
    assert check_map["bank_cross_page_consistency"]["severity"] == "high"


def test_bank_statement_summary_math_mismatch(tmp_path):
    """
    Summary arithmetic where opening + credits - debits != closing
    must trigger summary balance mismatch warning.
    """
    pdf_path = create_synthetic_bank_statement_pdf(
        tmp_path,
        "summary_math_error.pdf",
        opening_balance=10000.00,
        rows=[
            "TRANSACTION TOTAL 5000.00 8000.00",
            "CLOSING BALANCE 99999.00",  # Incorrect: 10000 + 8000 - 5000 = 13000 != 99999
        ],
    )
    text, _ = pdf_service.extract_text(pdf_path)
    cls = document_classifier.classify(text)
    fields = field_extractor.extract_fields(text, cls.document_type)

    fraud_rep = fraud_detector.analyze(pdf_path, text, cls.document_type, fields)
    check_map = {c["check"]: c for c in fraud_rep["checks"]}
    assert "bank_summary_balance_math" in check_map
    assert check_map["bank_summary_balance_math"]["status"] == "warning"
    assert check_map["bank_summary_balance_math"]["severity"] == "high"


def test_api_tampered_bank_statement_fixture_end_to_end():
    """
    End-to-End API upload and analysis of the tampered bank statement fixture.
    Must return document_type 'Bank Statement', risk_score >= 0.75, and 'Likely Fake'.
    """
    fixture_path = Path("backend/tests/fixtures/tampered_bank_statement.pdf")
    if not fixture_path.exists():
        fixture_path = Path("uploads/ba4882fb-4a27-41f8-82b9-a853e50f6994.pdf")

    with open(fixture_path, "rb") as f:
        upload_res = client.post(
            "/api/upload",
            files={"file": ("tampered_bank_statement.pdf", f.read(), "application/pdf")},
        )
    assert upload_res.status_code == 201
    file_id = upload_res.json()["file_id"]

    analyze_res = client.post(f"/api/analyze/{file_id}")
    assert analyze_res.status_code == 200
    data = analyze_res.json()

    assert data["document_type"] == "Bank Statement"
    assert data["risk_score"] >= 0.75
    assert data["risk_level"] in ["High", "Very High"]
    assert data["verification_status"] == "Likely Fake"
    assert any("Mathematical inconsistency" in r for r in data["decision_reasons"])


def test_image_metadata_clean_image():
    img = create_synthetic_image()
    check = image_forensics_service.check_image_metadata(img)
    assert check["check"] == "image_metadata"
    assert check["status"] == "pass"
    assert check["severity"] == "low"
    assert "evidence" in check


def test_image_metadata_photoshop_detected():
    img = create_synthetic_image()
    exif = img.getexif()
    exif[305] = "Adobe Photoshop 2024 (Windows)"
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    buf.seek(0)
    loaded_img = Image.open(buf)

    check = image_forensics_service.check_image_metadata(loaded_img)
    assert check["check"] == "image_metadata"
    assert check["status"] == "info"
    assert "Photoshop" in check["evidence"]["detected_editing_tools"]


def test_image_sharpness_clean_vs_blurry():
    clean_img = create_synthetic_image()
    clean_check = image_forensics_service.check_sharpness(clean_img)
    assert clean_check["check"] == "image_sharpness"
    assert clean_check["status"] == "pass"
    assert clean_check["evidence"]["is_defocused"] is False

    import cv2
    cv_arr = cv2.cvtColor(np.array(clean_img), cv2.COLOR_RGB2BGR)
    blurred = cv2.GaussianBlur(cv_arr, (45, 45), 0)
    blurred_img = Image.fromarray(cv2.cvtColor(blurred, cv2.COLOR_BGR2RGB))

    blur_check = image_forensics_service.check_sharpness(blurred_img)
    assert blur_check["check"] == "image_sharpness"
    assert blur_check["status"] == "warning"
    assert blur_check["evidence"]["is_defocused"] is True


def test_splicing_detection_patch():
    import cv2
    img = np.ones((600, 800, 3), dtype=np.uint8) * 245
    cv2.putText(img, "OFFICIAL DRIVING LICENCE", (50, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    for y_offset in [150, 240, 330, 420]:
        patch = np.ones((40, 300, 3), dtype=np.uint8) * 215
        cv2.rectangle(patch, (0, 0), (299, 39), (50, 50, 50), 2)
        img[y_offset:y_offset+40, 100:400] = patch

    pil_img = Image.fromarray(img)
    check = image_forensics_service.check_splicing(pil_img)
    assert check["check"] == "splicing_detection"
    assert check["evidence"]["suspicious_patch_corners"] > 0


def test_fraud_detector_extended_image_checks(tmp_path):
    img = create_synthetic_image()
    img_path = tmp_path / "test_doc.jpg"
    img.save(str(img_path), format="JPEG")

    report = fraud_detector.analyze(
        file_path=img_path,
        extracted_text="Driving Licence Name: John Doe",
        document_type="Driving Licence",
        fields={"name": "John Doe"},
    )
    check_names = {c["check"] for c in report["checks"]}
    assert "image_metadata" in check_names
    assert "image_sharpness" in check_names
    assert "splicing_detection" in check_names
    assert report["risk_level"] == "Low"


# ---------------------------------------------------------
# ML Tampering Risk Detector Tests
# ---------------------------------------------------------

def test_forensic_feature_extractor_vector_dimensions():
    """Verify that feature extractor generates a deterministic 24-dimensional float32 vector."""
    from backend.services.forensic_feature_extractor import (
        forensic_feature_extractor,
        FORENSIC_FEATURE_NAMES,
    )

    assert len(FORENSIC_FEATURE_NAMES) == 24
    vec = forensic_feature_extractor.extract_vector([])
    assert isinstance(vec, np.ndarray)
    assert vec.shape == (24,)
    assert vec.dtype == np.float32

    feats = forensic_feature_extractor.extract_features([])
    for name in FORENSIC_FEATURE_NAMES:
        assert name in feats
        assert isinstance(feats[name], float)


def test_tamper_detector_model_active_and_calibrated(tmp_path):
    """Verify ML model is active and generates calibrated probability and hybrid score."""
    from backend.services.fraud_detector import UnifiedForensicDetector

    detector = UnifiedForensicDetector()
    assert detector.is_ml_available() is True

    pdf_path = create_synthetic_pdf(tmp_path, "clean_ml_test.pdf")
    report = detector.analyze(
        file_path=pdf_path,
        extracted_text="Official clean document",
        document_type="Passport",
        fields={"passport_number": "A1234567"},
    )

    assert "ml_risk_score" in report
    assert "detection_method" in report
    assert report["detection_method"] == "hybrid_ml"
    assert report["ml_risk_score"] is not None
    assert 0.0 <= report["ml_risk_score"] <= 1.0
    assert report["risk_level"] == "Low"


def test_tamper_detector_fallback_on_missing_model(tmp_path):
    """Verify seamless rule-based fallback when ML model file does not exist."""
    from backend.services.fraud_detector import UnifiedForensicDetector

    detector = UnifiedForensicDetector(model_path="models/non_existent_model.joblib")
    assert detector.is_ml_available() is False

    pdf_path = create_synthetic_pdf(tmp_path, "fallback_test.pdf")
    report = detector.analyze(
        file_path=pdf_path,
        extracted_text="Clean document fallback test",
        document_type="PAN Card",
        fields={"pan_number": "ABCDE1234F"},
    )

    assert report["detection_method"] == "rule_based"
    assert report["ml_risk_score"] is None
    assert "risk_score" in report
    assert report["risk_level"] == "Low"
    assert len(report["checks"]) >= 3


def test_tamper_model_metadata_verification():
    """Verify saved model metadata file exists with valid evaluation metrics."""
    import json
    import os

    metadata_path = os.path.join("models", "tamper_model_metadata.json")
    assert os.path.exists(metadata_path), "Metadata file missing"

    with open(metadata_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    assert meta["model_name"] == "tamper_risk_calibrated_gradient_boosting_v1"
    assert meta["feature_count"] == 24
    assert len(meta["feature_names"]) == 24
    assert meta["metrics"]["accuracy"] >= 0.90
    assert meta["metrics"]["roc_auc"] >= 0.95
    assert meta["metrics"]["brier_score"] <= 0.08




