"""
Synthetic Dataset Generator for Document Classification.
Generates realistic, privacy-compliant training samples with OCR noise injection
for all supported document categories and non-document text.
"""

import random
import json
import os
from typing import List, Dict, Any

# Reproducible random seeds
RANDOM_FIRST_NAMES = [
    "Aarav", "Rohan", "Priya", "Ananya", "Vikram", "Neha", "Rahul", "Pooja",
    "Aditya", "Sneha", "Karan", "Divya", "Suresh", "Kavita", "Amit", "Sunita",
    "Rajesh", "Meera", "Deepak", "Swati", "Mohammad", "Younus", "Fatima", "Arjun",
    "John", "Sarah", "Michael", "Emily", "David", "Jessica", "James", "Emma"
]

RANDOM_LAST_NAMES = [
    "Sharma", "Verma", "Patel", "Singh", "Kumar", "Roy", "Gupta", "Reddy",
    "Iyer", "Nair", "Das", "Joshi", "Chopra", "Malhotra", "Khan", "Akula",
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Miller", "Davis", "Wilson"
]

RANDOM_CITIES = [
    "Mumbai", "Delhi", "Bengaluru", "Hyderabad", "Chennai", "Kolkata", "Pune",
    "Ahmedabad", "Jaipur", "Surat", "Lucknow", "Chandigarh", "Kochi", "Indore"
]

RANDOM_STATES = [
    "Maharashtra", "Delhi", "Karnataka", "Telangana", "Tamil Nadu", "West Bengal",
    "Gujarat", "Rajasthan", "Uttar Pradesh", "Punjab", "Kerala", "Madhya Pradesh", "Andhra Pradesh"
]

RANDOM_BANKS = [
    "HDFC Bank", "State Bank of India", "ICICI Bank", "Axis Bank", "Kotak Mahindra Bank",
    "Punjab National Bank", "Bank of Baroda", "Canara Bank", "Union Bank of India", "IndusInd Bank"
]

RANDOM_COMPANIES = [
    "Infosys Technologies Ltd", "Tata Consultancy Services", "Wipro Digital Solutions",
    "Reliance Industries Ltd", "Larsen & Toubro Infotech", "HCL Technologies",
    "Tech Mahindra Global", "Bharti Airtel Corp", "Cognizant Technology Solutions", "Accenture Solutions"
]


def _gen_date(start_year: int = 1970, end_year: int = 2026) -> str:
    day = random.randint(1, 28)
    month = random.randint(1, 12)
    year = random.randint(start_year, end_year)
    fmt = random.choice(["DD/MM/YYYY", "DD-MM-YYYY", "YYYY-MM-DD", "D Mon YYYY"])
    if fmt == "DD/MM/YYYY":
        return f"{day:02d}/{month:02d}/{year}"
    elif fmt == "DD-MM-YYYY":
        return f"{day:02d}-{month:02d}-{year}"
    elif fmt == "YYYY-MM-DD":
        return f"{year}-{month:02d}-{day:02d}"
    else:
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        return f"{day:02d} {months[month-1]} {year}"


def _gen_currency_amount(min_val: float = 100.0, max_val: float = 250000.0) -> str:
    amt = round(random.uniform(min_val, max_val), 2)
    prefix = random.choice(["INR ", "₹ ", "Rs. ", "$", ""])
    return f"{prefix}{amt:,.2f}"


def _inject_ocr_noise(text: str, noise_level: float = 0.05) -> str:
    """Injects slight OCR artifacts (dropped spaces, misread chars, scattered colons)."""
    if random.random() > 0.4:
        return text

    chars = list(text)
    substitutions = {"0": "O", "1": "l", "5": "S", "8": "B", "I": "1"}
    for i in range(len(chars)):
        if random.random() < noise_level:
            c = chars[i]
            if c in substitutions and random.random() < 0.3:
                chars[i] = substitutions[c]
            elif c == ":" and random.random() < 0.2:
                chars[i] = " :"
            elif c == "\n" and random.random() < 0.1:
                chars[i] = "\n:\n"
    return "".join(chars)


# --- Category Generators ---

def generate_bank_statement_sample() -> str:
    bank = random.choice(RANDOM_BANKS)
    name = f"{random.choice(RANDOM_FIRST_NAMES)} {random.choice(RANDOM_LAST_NAMES)}"
    acct = "".join([str(random.randint(0, 9)) for _ in range(random.choice([11, 14, 16]))])
    ifsc = f"{bank[:4].upper().replace(' ', 'X')}0{random.randint(100000, 999999)}"
    opening_bal = _gen_currency_amount(10000, 100000)
    closing_bal = _gen_currency_amount(20000, 150000)
    start_date = _gen_date(2025, 2026)
    end_date = _gen_date(2026, 2026)

    templates = [
        f"""
        {bank.upper()}
        STATEMENT OF ACCOUNT / ACCOUNT STATEMENT
        Customer Name: {name}
        Account Number: {acct}
        Branch: {random.choice(RANDOM_CITIES)}
        IFSC Code: {ifsc}
        Statement Period: {start_date} to {end_date}
        Opening Balance: {opening_bal}
        Total Deposit / Credit: {_gen_currency_amount(5000, 50000)}
        Total Withdrawal / Debit: {_gen_currency_amount(2000, 30000)}
        Closing Balance: {closing_bal}
        Available Balance: {closing_bal}
        Transaction Details:
        Date | Description | Chq/Ref No | Debit | Credit | Balance
        {_gen_date(2026, 2026)} | UPI Transfer / IMPS | REF{random.randint(100000,999999)} | 1,500.00 | - | {closing_bal}
        {_gen_date(2026, 2026)} | Salary Credit | SAL{random.randint(100000,999999)} | - | 45,000.00 | {closing_bal}
        """,
        f"""
        {bank}
        e-Statement of Account
        Account Holder: {name}
        Account No: {acct}
        IFSC: {ifsc}
        Ledger Balance: {opening_bal}
        Total Credits: {_gen_currency_amount(10000, 80000)}
        Total Debits: {_gen_currency_amount(5000, 40000)}
        Available Balance: {closing_bal}
        Value Date | Transaction Remarks | Amount | Cr/Dr
        {start_date} | ATM Cash Withdrawal | 2000.00 | Dr
        {end_date} | Interest Capitalized | 340.00 | Cr
        This is a system generated statement and does not require signature.
        """
    ]
    return _inject_ocr_noise(random.choice(templates).strip())


def generate_driving_licence_sample() -> str:
    name = f"{random.choice(RANDOM_FIRST_NAMES)} {random.choice(RANDOM_LAST_NAMES)}"
    state = random.choice(RANDOM_STATES)
    code = state[:2].upper()
    rto = f"{random.randint(1, 99):02d}"
    year = random.randint(2010, 2024)
    num = f"{random.randint(1000000, 9999999)}"
    dl_no = f"{code}{rto}{year}{num}"
    dob = _gen_date(1975, 2005)
    issue_date = _gen_date(2018, 2024)
    valid_till = _gen_date(2035, 2045)
    blood_group = random.choice(["O+", "A+", "B+", "AB+", "O-", "B-"])

    templates = [
        f"""
        UNION OF INDIA DRIVING LICENCE
        TRANSPORT DEPARTMENT, {state.upper()}
        Licence No: {dl_no}
        Authorisation to drive: LMV, MCWG
        Name: {name}
        Date of Birth: {dob}
        Blood Group: {blood_group}
        Issue Date: {issue_date}
        Valid Till / Validity: {valid_till}
        Address: {random.randint(1, 200)}/{random.randint(1, 99)}, Main Road, {random.choice(RANDOM_CITIES)}
        Holder's Signature: Present
        Issuing Authority: RTO {random.choice(RANDOM_CITIES)}
        """,
        f"""
        Indian Union Driving Licence
        Issued by {state.upper()}
        DL No: {dl_no}
        Licence to Drive Throughout India
        COV: Non-Transport LMV
        Name: {name}
        DOB: {dob}
        Blood Group: {blood_group}
        Issue Date: {issue_date}
        Validity (NT): {valid_till}
        Holder Signature
        Motor Vehicles Department
        """
    ]
    return _inject_ocr_noise(random.choice(templates).strip())


def generate_passport_sample() -> str:
    first_name = random.choice(RANDOM_FIRST_NAMES)
    last_name = random.choice(RANDOM_LAST_NAMES)
    letter = random.choice(["Z", "A", "K", "L", "M", "P", "R", "S", "T"])
    num = random.randint(1000000, 9999999)
    passport_no = f"{letter}{num}"
    dob = _gen_date(1970, 2004)
    issue_date = _gen_date(2018, 2024)
    expiry_date = _gen_date(2028, 2034)
    city = random.choice(RANDOM_CITIES)

    # Machine Readable Zone line
    mrz = f"P<IND{last_name.upper()}<<{first_name.upper()}{'<' * 20}"

    templates = [
        f"""
        REPUBLIC OF INDIA PASSPORT
        Type: P, Country Code: IND
        Passport No: {passport_no}
        Surname: {last_name}
        Given Name: {first_name}
        Nationality: Indian
        Sex: {random.choice(['M', 'F'])}
        Date of Birth: {dob}
        Place of Birth: {city}
        Place of Issue: {city}
        Date of Issue: {issue_date}
        Date of Expiry: {expiry_date}
        {mrz[:44]}
        {passport_no}4IND{dob.replace('-', '').replace('/', '')[2:]}M{expiry_date.replace('-', '').replace('/', '')[2:]}<<<<<<<
        """,
        f"""
        PASSPORT REPUBLIC OF INDIA
        Passport No.: {passport_no}
        Type P Country Code IND
        Given Name(s): {first_name}
        Surname: {last_name}
        Nationality: Indian
        Date of Birth: {dob}
        Date of Issue: {issue_date}
        Date of Expiry: {expiry_date}
        Place of Issue: {city}
        {mrz[:44]}
        """
    ]
    return _inject_ocr_noise(random.choice(templates).strip())


def generate_pan_card_sample() -> str:
    name = f"{random.choice(RANDOM_FIRST_NAMES)} {random.choice(RANDOM_LAST_NAMES)}"
    father = f"{random.choice(RANDOM_FIRST_NAMES)} {random.choice(RANDOM_LAST_NAMES)}"
    dob = _gen_date(1965, 2004)
    letters = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=3))
    type_char = "P"  # Individual
    fifth_char = name.split()[-1][0].upper()
    digits = "".join(random.choices("0123456789", k=4))
    last_char = random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    pan_num = f"{letters}{type_char}{fifth_char}{digits}{last_char}"

    templates = [
        f"""
        INCOME TAX DEPARTMENT
        GOVT OF INDIA
        PERMANENT ACCOUNT NUMBER CARD
        PAN: {pan_num}
        Name: {name}
        Father's Name: {father}
        Date of Birth: {dob}
        Signature
        """,
        f"""
        Government of India
        Income Tax Department
        Permanent Account Number
        {pan_num}
        Name: {name}
        Father's Name: {father}
        DOB: {dob}
        Tax Department Official Card
        """
    ]
    return _inject_ocr_noise(random.choice(templates).strip())


def generate_aadhaar_sample() -> str:
    name = f"{random.choice(RANDOM_FIRST_NAMES)} {random.choice(RANDOM_LAST_NAMES)}"
    dob = _gen_date(1960, 2005)
    gender = random.choice(["Male", "Female"])
    p1 = f"{random.randint(2000, 9999)}"
    p2 = f"{random.randint(1000, 9999)}"
    p3 = f"{random.randint(1000, 9999)}"
    aadhaar_num = f"{p1} {p2} {p3}"
    vid = f"{random.randint(1000, 9999)} {random.randint(1000, 9999)} {random.randint(1000, 9999)} {random.randint(1000, 9999)}"

    templates = [
        f"""
        UNIQUE IDENTIFICATION AUTHORITY OF INDIA
        GOVERNMENT OF INDIA
        Mera Aadhaar Meri Pehchan
        Enrollment No: {random.randint(1000,9999)}/{random.randint(10000,99999)}/{random.randint(10000,99999)}
        To: {name}
        Date of Birth: {dob}
        Gender: {gender}
        {aadhaar_num}
        VID: {vid}
        help@uidai.gov.in | www.uidai.gov.in
        """,
        f"""
        UIDAI - Unique Identification Authority of India
        Aadhaar Card
        Government of India
        Name: {name}
        DOB / Year of Birth: {dob}
        {gender}
        {aadhaar_num}
        Mera Aadhaar, Meri Pehchan
        VID: {vid}
        """
    ]
    return _inject_ocr_noise(random.choice(templates).strip())


def generate_salary_slip_sample() -> str:
    company = random.choice(RANDOM_COMPANIES)
    name = f"{random.choice(RANDOM_FIRST_NAMES)} {random.choice(RANDOM_LAST_NAMES)}"
    emp_id = f"EMP{random.randint(10000, 99999)}"
    uan = f"{random.randint(100000000000, 999999999999)}"
    basic = round(random.uniform(25000, 80000), 2)
    hra = round(basic * 0.40, 2)
    special = round(random.uniform(5000, 25000), 2)
    gross = basic + hra + special
    pf = round(basic * 0.12, 2)
    tax = round(random.uniform(1000, 6000), 2)
    deductions = pf + tax
    net = gross - deductions

    month = random.choice(["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"])
    year = random.choice([2025, 2026])

    templates = [
        f"""
        {company}
        PAYSLIP FOR THE MONTH OF {month.upper()} {year}
        Employee Name: {name}
        Employee ID: {emp_id}
        Designation: Software Engineer
        UAN: {uan} | PF No: {emp_id}/PF
        Pay Period: {month} {year}
        Earnings:
        Basic Pay: INR {basic:,.2f}
        HRA: INR {hra:,.2f}
        Special Allowance: INR {special:,.2f}
        Gross Salary / Gross Pay: INR {gross:,.2f}
        Deductions:
        Provident Fund (PF): INR {pf:,.2f}
        Professional Tax / TDS: INR {tax:,.2f}
        Total Deductions: INR {deductions:,.2f}
        Net Salary / Net Pay: INR {net:,.2f}
        Take Home Pay: INR {net:,.2f}
        """,
        f"""
        {company}
        Salary Slip - {month} {year}
        Employee: {name} ({emp_id})
        Earnings and Deductions:
        Basic Pay: {basic:,.2f}
        Allowances: {special:,.2f}
        Gross Pay: {gross:,.2f}
        PF Deductions: {pf:,.2f}
        Total Deductions: {deductions:,.2f}
        Net Salary: {net:,.2f}
        This is a computer generated pay slip and does not require an authorized signature.
        """
    ]
    return _inject_ocr_noise(random.choice(templates).strip())


def generate_invoice_sample() -> str:
    vendor = random.choice(RANDOM_COMPANIES)
    customer = f"{random.choice(RANDOM_FIRST_NAMES)} {random.choice(RANDOM_LAST_NAMES)}"
    inv_num = f"INV-{random.randint(2024, 2026)}-{random.randint(1000, 9999)}"
    inv_date = _gen_date(2025, 2026)
    due_date = _gen_date(2026, 2026)
    gstin = f"27{random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ') * 4}{random.randint(1000,9999)}A1Z5"
    subtotal = round(random.uniform(500, 50000), 2)
    tax = round(subtotal * 0.18, 2)
    total = subtotal + tax

    templates = [
        f"""
        TAX INVOICE / COMMERCIAL INVOICE
        Seller: {vendor}
        GSTIN: {gstin}
        Invoice Number: {inv_num}
        Invoice Date: {inv_date}
        Due Date: {due_date}
        Bill To: {customer}
        Ship To: {customer}, {random.choice(RANDOM_CITIES)}
        Item Description | Quantity | Qty | Unit Price | Subtotal
        Consulting Services | 1 | 1 | {subtotal:,.2f} | {subtotal:,.2f}
        Subtotal: ${subtotal:,.2f}
        GST Tax (18%): ${tax:,.2f}
        Total Amount Due / Total: ${total:,.2f}
        Payment Terms: Net 30 Days
        """,
        f"""
        {vendor}
        TAX INVOICE
        Invoice No: {inv_num}
        Date: {inv_date}
        Customer: {customer}
        GSTIN: {gstin}
        Items:
        Hardware Supply - Qty: 2 - Price: {subtotal/2:,.2f}
        Subtotal: INR {subtotal:,.2f}
        Applicable Tax: INR {tax:,.2f}
        Total Due: INR {total:,.2f}
        Thank you for your business.
        """
    ]
    return _inject_ocr_noise(random.choice(templates).strip())


def generate_certificate_sample() -> str:
    name = f"{random.choice(RANDOM_FIRST_NAMES)} {random.choice(RANDOM_LAST_NAMES)}"
    univ = f"University of {random.choice(RANDOM_CITIES)}"
    prog = random.choice([
        "Full Stack Web Development", "Machine Learning & AI Engineering",
        "Cybersecurity Fundamentals", "Data Science & Cloud Computing",
        "Executive Leadership and Management", "Advanced Python Programming"
    ])
    date = _gen_date(2023, 2026)

    templates = [
        f"""
        CERTIFICATE OF COMPLETION
        {univ}
        This is to certify that
        {name}
        has successfully completed the program in
        {prog}
        Awarded on {date}
        Director of Academic Affairs | Registrar
        Certificate ID: CERT-{random.randint(100000, 999999)}
        """,
        f"""
        CERTIFICATE OF ACHIEVEMENT
        Hereby certifies that
        {name}
        Presented to / Awarded to {name}
        in recognition of successful completion and dedication in {prog}.
        Date of Award: {date}
        Institution: {univ}
        Dean of Faculty | Academic Director
        """
    ]
    return _inject_ocr_noise(random.choice(templates).strip())


def generate_other_document_sample() -> str:
    topics = [
        # Technology blog / article
        """
        Artificial intelligence and cloud architecture continue to evolve rapidly across global enterprises.
        Modern microservices leverage container orchestration systems such as Kubernetes to guarantee high availability.
        Monitoring pipelines collect telemetry data, logs, and distributed traces to detect anomalies before outages occur.
        Engineers must adhere to test-driven development and continuous integration best practices.
        """,
        # Meeting minutes / internal memo
        """
        Weekly Team Sync Meeting Notes
        Date: Monday, March 14, 2026
        Attendees: Product Management, Engineering Lead, Quality Assurance.
        Discussion Topics:
        1. Sprint velocity and backlog grooming for the upcoming quarter.
        2. Customer feedback regarding dashboard page load latency.
        3. Action items: Alice to review database indices; Bob to update documentation.
        """,
        # Terms of service / privacy policy snippet
        """
        General Terms of Use and Privacy Guidelines
        By accessing this website, users agree to abide by all local guidelines and applicable rules.
        We respect user privacy and do not sell personal browsing telemetry to third-party marketing services.
        Cookies are used strictly for session state management and security rate limiting.
        Contact our legal department for questions or inquiries.
        """,
        # Recipe / lifestyle snippet
        """
        Classic Mediterranean Roasted Vegetables
        Ingredients needed:
        - 2 zucchini, sliced into half-inch rounds
        - 1 red bell pepper, diced
        - 3 tablespoons extra virgin olive oil
        - 1 teaspoon dried oregano and sea salt to taste
        Preheat oven to 400 degrees Fahrenheit. Roast for twenty-five minutes until golden brown and tender.
        """
    ]
    return random.choice(topics).strip()


CATEGORY_MAP = {
    "Bank Statement": generate_bank_statement_sample,
    "Driving Licence": generate_driving_licence_sample,
    "Passport": generate_passport_sample,
    "PAN Card": generate_pan_card_sample,
    "Aadhaar": generate_aadhaar_sample,
    "Salary Slip": generate_salary_slip_sample,
    "Invoice": generate_invoice_sample,
    "Certificate": generate_certificate_sample,
    "Other Document": generate_other_document_sample,
}


def generate_dataset(samples_per_class: int = 120, seed: int = 42) -> List[Dict[str, str]]:
    """
    Generates a balanced, privacy-safe dataset of text samples and labels.
    """
    random.seed(seed)
    dataset: List[Dict[str, str]] = []

    for category, generator_fn in CATEGORY_MAP.items():
        for _ in range(samples_per_class):
            text = generator_fn()
            dataset.append({
                "text": text,
                "label": category,
            })

    random.shuffle(dataset)
    return dataset


if __name__ == "__main__":
    data = generate_dataset(samples_per_class=100)
    print(f"Generated {len(data)} total samples across {len(CATEGORY_MAP)} classes.")
    os.makedirs("data", exist_ok=True)
    with open("data/training_data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print("Saved to data/training_data.json")
