import pytest
from backend.services.text_normalizer import text_normalizer
from backend.services.field_extractor import field_extractor

# 1. Noisy OCR & Isolated OCR noise tests

def test_isolated_ocr_noise_removal():
    noisy_input = """
    o
    aN
    Ox)                                                        )
    Indian Union Driving Licence
    Sens aad          AP22120260004571                        |         ©
    aw
    Name : AKULA MAHAMMAD YOUNUS                                      @
    e
    5
    Date Of Birth : 20-09-2005
    Q
    Address:
    1/58,
    CHIPPAGIRI VILLAGE AND MANDAL,
    KURNOOL DISTRICT,518396
    Els
    40
    le
    a
    Qe
    —Ty
    =
    pe“4
    oe
    foe
    ee
    rss
    oa
    a ee ee ee eee ee
    P|
    Licencing Authority
    UNIT OFFICE ADONI
    """
    cleaned = text_normalizer.normalize_ocr_text(noisy_input)

    # Isolated noise lines must NOT be present
    assert "\no\n" not in f"\n{cleaned}\n"
    assert "\naN\n" not in f"\n{cleaned}\n"
    assert "\nOx)\n" not in f"\n{cleaned}\n"
    assert "\nEls\n" not in f"\n{cleaned}\n"
    assert "\n40\n" not in f"\n{cleaned}\n"
    assert "\nle\n" not in f"\n{cleaned}\n"
    assert "\nQe\n" not in f"\n{cleaned}\n"
    assert "\npe“4\n" not in f"\n{cleaned}\n"
    assert "\noe\n" not in f"\n{cleaned}\n"
    assert "\nfoe\n" not in f"\n{cleaned}\n"
    assert "\nfee\n" not in f"\n{cleaned}\n"
    assert "a ee ee ee eee ee" not in cleaned

    # Real data must be preserved
    assert "Indian Union Driving Licence" in cleaned
    assert "AP22120260004571" in cleaned
    assert "AKULA MAHAMMAD YOUNUS" in cleaned
    assert "20-09-2005" in cleaned
    assert "1/58" in cleaned
    assert "CHIPPAGIRI VILLAGE AND MANDAL" in cleaned
    assert "UNIT OFFICE ADONI" in cleaned


def test_noisy_ocr_preserves_identifiers():
    sample = """
    DL No: AP22120260004571
    Emergency Contact Number 91-9618802994
    Pincode: 518396
    PAN: ABCDE1234F
    IFSC: HDFC0001234
    """
    cleaned = text_normalizer.normalize_ocr_text(sample)
    assert "AP22120260004571" in cleaned
    assert "91-9618802994" in cleaned
    assert "518396" in cleaned
    assert "ABCDE1234F" in cleaned
    assert "HDFC0001234" in cleaned


# 2. Multiline labels association

def test_multiline_labels_association():
    raw_ocr = """
    Name:
    AKULA MAHAMMAD YOUNUS

    Date of Birth:
    20-09-2005

    Licence No:
    AP22120260004571
    """
    cleaned = text_normalizer.normalize_ocr_text(raw_ocr)
    assert "Name = AKULA MAHAMMAD YOUNUS" in cleaned or "Name: AKULA MAHAMMAD YOUNUS" in cleaned

    fields = field_extractor.extract_fields(cleaned, "Driving Licence")
    assert fields.get("name") == "AKULA MAHAMMAD YOUNUS"
    assert fields.get("date_of_birth") == "20-09-2005"
    assert fields.get("licence_number") == "AP22120260004571"


# 3. Date extraction & sequence handling

def test_date_extraction_sequences_and_nearby_labels():
    text = """
    Indian Union Driving Licence
    Issue Date Validity(NT) Validity (TR) |   > =  F
    18-08-2026    19-09-2045
    Name : AKULA MAHAMMAD YOUNUS
    Date Of Birth : 20-09-2005
    """
    fields = field_extractor.extract_fields(text, "Driving Licence")
    assert fields.get("date_of_birth") == "20-09-2005"
    assert fields.get("issue_date") == "18-08-2026"
    assert fields.get("expiry_date") == "19-09-2045"


def test_date_extraction_chronology_fallback():
    text = """
    Driving Licence
    Holder: Vikram Roy
    Dates on document:
    15-06-2020
    14-06-2040
    DOB: 10-02-1995
    """
    fields = field_extractor.extract_fields(text, "Driving Licence")
    assert fields.get("date_of_birth") == "10-02-1995"
    assert fields.get("issue_date") == "15-06-2020"
    assert fields.get("expiry_date") == "14-06-2040"


# 4. Licence number extraction

def test_licence_number_extraction_formats():
    cases = [
        ("Indian Driving Licence AP22 120260004571 Name: Test", "AP22120260004571"),
        ("DL No: DL-0420110012345 Valid Till: 2035", "DL-0420110012345"),
        ("License Number: MH1220180019283 DOB: 1990-01-01", "MH1220180019283"),
    ]
    for raw, expected in cases:
        fields = field_extractor.extract_fields(raw, "Driving Licence")
        assert fields.get("licence_number") == expected


# 5. Blood group validation

def test_blood_group_valid_patterns():
    valid_groups = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
    for bg in valid_groups:
        text = f"Driving Licence Name: John Doe Blood Group: {bg}"
        fields = field_extractor.extract_fields(text, "Driving Licence")
        assert fields.get("blood_group") == bg


def test_blood_group_invalid_does_not_guess():
    invalid_cases = [
        "Driving Licence Blood Group: Unknown Organ Donor: Yes",
        "Driving Licence Blood Group: Positive",
        "Driving Licence Blood Group: NA",
        "Driving Licence Blood Group: ",
        "Driving Licence Organ Donor: Yes",
    ]
    for text in invalid_cases:
        fields = field_extractor.extract_fields(text, "Driving Licence")
        assert fields.get("blood_group") is None


# 6. Multiline address extraction

def test_multiline_address_extraction():
    text = """
    Driving Licence
    Name: John Doe
    Address:
    1/58,
    CHIPPAGIRI VILLAGE AND MANDAL,
    KURNOOL DISTRICT,518396
    DL No: AP22120260004571
    """
    cleaned = text_normalizer.normalize_ocr_text(text)
    fields = field_extractor.extract_fields(cleaned, "Driving Licence")
    assert fields.get("address") is not None
    assert "1/58" in fields["address"]
    assert "CHIPPAGIRI VILLAGE AND MANDAL" in fields["address"]
    assert "KURNOOL DISTRICT" in fields["address"]
    # Ensure subsequent section label is NOT part of the address
    assert "DL No" not in fields["address"]


# 7. Missing fields return null / None (no fabrication)

def test_missing_fields_return_null():
    text = """
    Indian Union Driving Licence
    DL No: AP22120260004571
    Name: AKULA MAHAMMAD YOUNUS
    """
    fields = field_extractor.extract_fields(text, "Driving Licence")
    assert fields.get("licence_number") == "AP22120260004571"
    assert fields.get("name") == "AKULA MAHAMMAD YOUNUS"
    # Unpresent fields must be explicitly None (not fabricated)
    assert fields.get("date_of_birth") is None
    assert fields.get("blood_group") is None
    assert fields.get("issue_date") is None
    assert fields.get("expiry_date") is None
    assert fields.get("address") is None
    assert fields.get("issuing_authority") is None


# 8. Issuing Authority extraction

def test_issuing_authority_extraction():
    text = """
    Indian Union Driving Licence
    Issued by ANDHRA PRADESH
    Licencing Authority
    UNIT OFFICE ADONI
    """
    fields = field_extractor.extract_fields(text, "Driving Licence")
    assert fields.get("issuing_authority") in ["ANDHRA PRADESH", "UNIT OFFICE ADONI"]
