import pytest
from backend.services.document_classifier import (
    document_classifier,
    RuleBasedDocumentClassifier,
    MLDocumentClassifier,
    HybridDocumentClassifier,
)
from backend.services.field_extractor import field_extractor
from backend.services.text_normalizer import text_normalizer

# --- Text Normalization Tests ---

def test_text_normalizer_repairs_ocr_artifacts():
    raw_ocr = "Here is a state-\n  ment with p a n number and acc0unt info."
    cleaned = text_normalizer.normalize(raw_ocr)
    assert "statement" in cleaned
    assert "pan" in cleaned
    assert "account" in cleaned

# --- Document Classification Tests ---

def test_bank_statement_classification():
    text = """
    HDFC BANK LIMITED
    ACCOUNT STATEMENT
    Customer Name: Ramesh Kumar
    Account Number: 50100234567890
    IFSC: HDFC0001234
    Opening Balance: INR 45,000.00
    Closing Balance: INR 78,920.00
    Total Deposit: INR 50,000.00
    Total Withdrawal: INR 16,080.00
    Transaction Details for January 2026
    """
    res = document_classifier.classify(text)
    assert res.document_type == "Bank Statement"
    assert res.confidence >= 0.70
    assert res.classification_status == "classified"
    assert res.method in ["rule_based", "hybrid", "machine_learning"]
    assert len(res.matched_signals) >= 3

def test_driving_licence_classification():
    text = """
    UNION OF INDIA DRIVING LICENCE
    TRANSPORT DEPARTMENT, MAHARASHTRA
    Licence No: MH-12-20180012345
    Authorisation to drive: LMV, MCWG
    Name: John Doe
    Date of Birth: 15/04/1992
    Valid Till: 14/04/2038
    """
    res = document_classifier.classify(text)
    assert res.document_type == "Driving Licence"
    assert res.confidence >= 0.70
    assert res.classification_status == "classified"

def test_passport_classification():
    text = """
    REPUBLIC OF INDIA PASSPORT
    Type: P, Country Code: IND
    Passport No: Z9182734
    Given Name: Aarav
    Surname: Sharma
    Nationality: Indian
    Date of Birth: 22/08/1995
    Place of Birth: New Delhi
    Date of Issue: 10/01/2020
    Date of Expiry: 09/01/2030
    P<INDSHARMA<<AARAV<<<<<<<<<<<<<<<<<<<<<<<<<<
    """
    res = document_classifier.classify(text)
    assert res.document_type == "Passport"
    assert res.confidence >= 0.75
    assert res.classification_status == "classified"

def test_pan_card_classification():
    text = """
    INCOME TAX DEPARTMENT
    GOVT OF INDIA
    PERMANENT ACCOUNT NUMBER CARD
    Name: Vijay Verma
    Father's Name: Ashok Verma
    DOB: 11/11/1988
    ABCDE1234F
    """
    res = document_classifier.classify(text)
    assert res.document_type == "PAN Card"
    assert res.confidence >= 0.75
    assert res.classification_status == "classified"

def test_aadhaar_classification():
    text = """
    UNIQUE IDENTIFICATION AUTHORITY OF INDIA
    Mera Aadhaar Meri Pehchan
    Government of India
    Name: Priya Singh
    Date of Birth: 05/06/1998
    Female
    9876 5432 1098
    VID: 9182 7364 5019 2837
    """
    res = document_classifier.classify(text)
    assert res.document_type == "Aadhaar"
    assert res.confidence >= 0.75
    assert res.classification_status == "classified"

def test_salary_slip_classification():
    text = """
    TECH SOLUTIONS PVT LTD
    PAYSLIP FOR THE MONTH OF FEBRUARY 2026
    Employee Name: Vikram Patel
    Gross Salary: INR 95,000.00
    Basic Pay: INR 45,000.00
    Provident Fund: INR 5,400.00
    Total Deductions: INR 8,200.00
    Net Salary: INR 86,800.00
    """
    res = document_classifier.classify(text)
    assert res.document_type == "Salary Slip"
    assert res.confidence >= 0.70
    assert res.classification_status == "classified"

def test_invoice_classification():
    text = """
    GLOBAL TRADERS LLC
    TAX INVOICE
    Invoice Number: INV-2026-9081
    Invoice Date: 12/02/2026
    Bill To: Acme Corp
    GSTIN: 27ABCDE1234F1Z5
    Subtotal: $4,500.00
    Tax: $810.00
    Total Amount Due: $5,310.00
    """
    res = document_classifier.classify(text)
    assert res.document_type == "Invoice"
    assert res.confidence >= 0.70
    assert res.classification_status == "classified"

def test_certificate_classification():
    text = """
    CERTIFICATE OF COMPLETION
    This is to certify that
    Ananya Roy
    has successfully completed the Advanced Data Engineering Program
    Awarded on 15/01/2026 by University of Technology
    """
    res = document_classifier.classify(text)
    assert res.document_type == "Certificate"
    assert res.confidence >= 0.70
    assert res.classification_status == "classified"

def test_weak_evidence_single_word_does_not_classify():
    # Only a single generic word 'account' with no bank context
    text = "Please verify your account settings in your profile preferences menu."
    res = document_classifier.classify(text)
    assert res.document_type in ["Unknown", "Other Document"]
    assert res.classification_status == "insufficient_evidence"

def test_unknown_random_text():
    text = "The quick brown fox jumps over the lazy dog in the middle of summer."
    res = document_classifier.classify(text)
    assert res.document_type in ["Unknown", "Other Document"]
    assert res.classification_status == "insufficient_evidence"

def test_conflicting_ambiguous_evidence():
    # Artificially created text with conflicting cues
    text = """
    TAX INVOICE AND CERTIFICATE OF COMPLETION
    Invoice Number: INV-999
    Subtotal: $1,000.00
    Total Amount: $1,000.00
    This is to certify that the recipient completed the course.
    """
    res = document_classifier.classify(text)
    # When evidence is split, system should recognize alternatives
    assert len(res.alternative_types) > 0

def test_rule_based_classifier_direct():
    rule_clf = RuleBasedDocumentClassifier()
    text = "UNION OF INDIA DRIVING LICENCE Transport Department MH-12-20180012345 Name: John"
    res = rule_clf.classify(text)
    assert res.document_type == "Driving Licence"
    assert res.method == "rule_based"
    assert res.confidence >= 0.70

def test_ml_classifier_direct():
    ml_clf = MLDocumentClassifier()
    assert ml_clf.is_available() is True
    text = "UNION OF INDIA DRIVING LICENCE Transport Department MH-12-20180012345 Authorisation to drive LMV Name: John"
    res = ml_clf.classify(text)
    assert res.document_type == "Driving Licence"
    assert res.method == "machine_learning"
    assert res.confidence >= 0.70
    assert len(res.matched_signals) > 0

def test_hybrid_classifier_direct():
    hybrid_clf = HybridDocumentClassifier()
    text = "TAX INVOICE Seller: Acme Corp Invoice Number: INV-2026-101 Subtotal: $500.00 Total: $590.00"
    res = hybrid_clf.classify(text)
    assert res.document_type == "Invoice"
    assert res.method == "hybrid"
    assert res.confidence >= 0.75
    assert len(res.matched_signals) >= 2

def test_hybrid_fallback_when_model_missing():
    # Pass a non-existent model path to verify fallback to rule-based logic
    fallback_clf = HybridDocumentClassifier(ml_model_path="models/non_existent_model.joblib")
    text = "TAX INVOICE Invoice Number: INV-900 Bill To: John Doe Total Amount Due: $100.00"
    res = fallback_clf.classify(text)
    assert res.document_type == "Invoice"
    assert res.method == "rule_based"
    assert res.confidence >= 0.70

# --- Field Extraction Tests ---


def test_bank_statement_field_extraction():
    text = """
    HDFC Bank
    Customer Name: Johnathan Doe
    Account Number: 123456789012
    Opening Balance: INR 10,000.00
    Closing Balance: INR 25,500.00
    IFSC: HDFC0001234
    Statement Period: 01/01/2026 to 31/01/2026
    """
    fields = field_extractor.extract_fields(text, "Bank Statement")
    assert fields.get("bank_name") == "HDFC Bank"
    assert fields.get("account_holder") == "Johnathan Doe"
    assert fields.get("account_number") == "XXXXXX9012"  # Masked
    assert "10,000.00" in fields.get("opening_balance", "")
    assert "25,500.00" in fields.get("closing_balance", "")
    assert fields.get("ifsc_code") == "HDFC0001234"

def test_driving_licence_field_extraction():
    text = """
    Driving Licence
    Name: Sarah Connor
    Licence No: DL-0420110012345
    DOB: 12/03/1985
    Issue Date: 01/05/2015
    Valid Till: 01/05/2035
    """
    fields = field_extractor.extract_fields(text, "Driving Licence")
    assert fields.get("name") == "Sarah Connor"
    assert fields.get("licence_number") == "DL-0420110012345"
    assert fields.get("date_of_birth") == "12/03/1985"
    assert fields.get("issue_date") == "01/05/2015"
    assert fields.get("expiry_date") == "01/05/2035"

def test_passport_field_extraction():
    text = """
    Passport No: M1234567
    Given Name: Michael Smith
    Nationality: British
    DOB: 09/09/1980
    Date of Issue: 12/04/2018
    Date of Expiry: 11/04/2028
    """
    fields = field_extractor.extract_fields(text, "Passport")
    assert fields.get("passport_number") == "M1234567"
    assert fields.get("name") == "Michael Smith"
    assert fields.get("nationality") == "British"
    assert fields.get("date_of_birth") == "09/09/1980"
    assert fields.get("issue_date") == "12/04/2018"
    assert fields.get("expiry_date") == "11/04/2028"

def test_aadhaar_field_masking():
    text = "Aadhaar Card: 1234 5678 9876, DOB: 01/01/2000, Gender: Female"
    fields = field_extractor.extract_fields(text, "Aadhaar")
    assert fields.get("aadhaar_number") == "XXXX XXXX 9876"  # Masked first 8 digits
    assert fields.get("date_of_birth") == "01/01/2000"
    assert fields.get("gender") == "Female"
