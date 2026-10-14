import re
from typing import Dict, Any, List, Optional
from backend.utils.logger import logger


class BaseFieldExtractor:
    def extract_fields(self, text: str, document_type: str) -> Dict[str, Any]:
        raise NotImplementedError


class DocumentFieldExtractor(BaseFieldExtractor):
    """
    Phase 2A Document Field Extractor.
    Extracts structured, document-type-specific fields with privacy masking.
    Falls back to generic pattern extraction for Unknown / Other Document.
    """

    DATE_PATTERNS = [
        r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
        r"\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b",
        r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4}\b",
    ]

    CURRENCY_PATTERN = r"(?:(?:INR|USD|EUR|GBP|Rs\.?|₹|\$|€)\s*[\d,]+(?:\.\d{2})?|[\d,]+\.\d{2})"

    def extract_fields(self, text: str, document_type: str, raw_text: Optional[str] = None) -> Dict[str, Any]:
        if not text and not raw_text:
            return {}

        effective_text = text or raw_text or ""
        effective_raw = raw_text or text or ""

        fields: Dict[str, Any] = {}

        if document_type == "Bank Statement":
            fields = self._extract_bank_statement_fields(effective_text)
        elif document_type == "Driving Licence":
            fields = self._extract_driving_licence_fields(effective_text, effective_raw)
            # Driving Licence keeps explicit null for undetected standard fields
            EXPECTED_DL_FIELDS = [
                "licence_number", "name", "date_of_birth", "blood_group",
                "issue_date", "expiry_date", "address", "issuing_authority"
            ]
            for k in EXPECTED_DL_FIELDS:
                if k not in fields:
                    fields[k] = None
            return fields
        elif document_type == "Passport":
            fields = self._extract_passport_fields(effective_text)
        elif document_type == "PAN Card":
            fields = self._extract_pan_card_fields(effective_text)
        elif document_type == "Aadhaar":
            fields = self._extract_aadhaar_fields(effective_text)
        elif document_type == "Salary Slip":
            fields = self._extract_salary_slip_fields(effective_text)
        elif document_type == "Invoice":
            fields = self._extract_invoice_fields(effective_text)
        elif document_type == "Certificate":
            fields = self._extract_certificate_fields(effective_text)
        else:
            fields = self._extract_generic_fields(effective_text)

        # Remove empty / null fields for other types
        cleaned_fields = {k: v for k, v in fields.items() if v is not None and str(v).strip() != ""}
        return cleaned_fields


    # --- Category-Specific Extractors ---

    def _extract_bank_statement_fields(self, text: str) -> Dict[str, Any]:
        fields: Dict[str, Any] = {}

        # 1. Bank Name
        # Check header patterns like "Statement of HDFC Account"
        header_bank_match = re.search(
            r"(?:Statement\s+of\s+([A-Za-z]+)\s+Account|Account\s+Statement\s*-\s*([A-Za-z]+))",
            text,
            re.IGNORECASE,
        )
        if header_bank_match:
            b_name = (header_bank_match.group(1) or header_bank_match.group(2)).strip()
            if b_name.upper() in ["HDFC", "SBI", "ICICI", "AXIS", "KOTAK", "PNB", "BOB", "CANARA", "IDBI", "CITI", "HSBC", "BARCLAYS"]:
                fields["bank_name"] = f"{b_name.upper()} Bank" if not b_name.upper().endswith("BANK") else b_name
            else:
                fields["bank_name"] = b_name

        if "bank_name" not in fields:
            bank_match = re.search(
                r"\b([A-Z][A-Za-z\s]+(?:Bank|BANK)(?:\s+(?:Ltd|Limited|LIMITED))?)\b",
                text,
            )
            if bank_match:
                fields["bank_name"] = bank_match.group(1).strip()
            else:
                for b in ["HDFC Bank", "State Bank of India", "SBI", "ICICI Bank", "Axis Bank", "Kotak Mahindra Bank", "Citibank", "Chase", "HSBC", "Barclays"]:
                    if re.search(r"\b" + re.escape(b) + r"\b", text, re.IGNORECASE):
                        fields["bank_name"] = b
                        break

        # 2. Account Holder
        holder_match = re.search(
            r"(?:Customer\s*Name|Account\s*Holder|Name\s*of\s*Account\s*Holder)[:\s]+([A-Za-z][^\r\n,;]+)",
            text,
            re.IGNORECASE,
        )
        if holder_match:
            fields["account_holder"] = holder_match.group(1).strip()

        # 3. Account Number (Masked)
        acc_match = re.search(
            r"(?:Account\s*(?:No|Number|#)|A/C\s*(?:No|Number)?)[:\s]*(\d{9,18})",
            text,
            re.IGNORECASE,
        )
        if acc_match:
            raw_acc = acc_match.group(1)
            fields["account_number"] = f"XXXXXX{raw_acc[-4:]}"

        # 4. Statement Period
        period_match = re.search(
            r"(?:Statement\s*Period|Period)[:\s]+([^\r\n]+)",
            text,
            re.IGNORECASE,
        )
        if period_match:
            fields["statement_period"] = period_match.group(1).strip()

        # 5. Opening Balance
        open_bal_match = re.search(
            r"(?:Opening\s*Balance|Opening\s*Bal)[:\s]*(" + self.CURRENCY_PATTERN + ")",
            text,
            re.IGNORECASE,
        )
        if open_bal_match:
            fields["opening_balance"] = open_bal_match.group(1).strip()

        # 6. Closing Balance
        close_bal_match = re.search(
            r"(?:Closing\s*Balance|Closing\s*Bal)[:\s]*(" + self.CURRENCY_PATTERN + ")",
            text,
            re.IGNORECASE,
        )
        if close_bal_match:
            fields["closing_balance"] = close_bal_match.group(1).strip()

        # 7. Total Debits and Total Credits (Transaction Totals)
        tot_match = re.search(
            r"TRANSACTION\s+TOTAL\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})",
            text,
            re.IGNORECASE,
        )
        if tot_match:
            fields["total_debits"] = tot_match.group(1).strip()
            fields["total_credits"] = tot_match.group(2).strip()
        else:
            deb_match = re.search(r"(?:Total\s*(?:Debits?|Withdrawals?))[:\s]*(" + self.CURRENCY_PATTERN + ")", text, re.IGNORECASE)
            if deb_match:
                fields["total_debits"] = deb_match.group(1).strip()
            cred_match = re.search(r"(?:Total\s*(?:Credits?|Deposits?))[:\s]*(" + self.CURRENCY_PATTERN + ")", text, re.IGNORECASE)
            if cred_match:
                fields["total_credits"] = cred_match.group(1).strip()

        # 8. IFSC Code
        ifsc_match = re.search(r"\bIFSC(?:\s*Code)?[:\s]*([A-Z]{4}0[A-Z0-9]{6})\b", text, re.IGNORECASE)
        if ifsc_match:
            fields["ifsc_code"] = ifsc_match.group(1)

        # 9. Branch Name
        branch_match = re.search(r"(?:Branch\s*(?:Name)?|Branch)[:\s]+([A-Za-z0-9\s,-]+?)(?:\n|$)", text, re.IGNORECASE)
        if branch_match and len(branch_match.group(1).strip()) < 40:
            fields["branch_name"] = branch_match.group(1).strip()

        return fields

    def _extract_driving_licence_fields(self, text: str, raw_text: Optional[str] = None) -> Dict[str, Any]:
        combined_sources = [text]
        if raw_text and raw_text != text:
            combined_sources.append(raw_text)

        fields: Dict[str, Any] = {}

        # 1. Licence Number
        for src in combined_sources:
            dl_match = (
                re.search(r"\b([A-Z]{2}[-\s]?\d{2,3}[-\s]?(?:19|20)?\d{7,12})\b", src)
                or re.search(r"\b([A-Z]{2}\d{13,15})\b", src)
                or re.search(r"(?:DL\s*No|Licence\s*No|License\s*No)[:=\s]*([A-Za-z0-9\-\s]{10,22})", src, re.IGNORECASE)
            )
            if dl_match:
                val = re.sub(r"\s+", "", dl_match.group(1).strip())
                if len(val) >= 10:
                    fields["licence_number"] = val
                    break

        # 2. Name
        for src in combined_sources:
            name_match = (
                re.search(r"(?:Name|Holder'?s\s*Name)[:=\s]+([A-Za-z][^\r\n,;]+(?:\n[A-Za-z]+)?)", src, re.IGNORECASE)
                or re.search(r"(?:Name|Holder'?s\s*Name)[:=\s\n]+([A-Za-z][^\r\n,;]+)", src, re.IGNORECASE)
            )
            if name_match:
                val = name_match.group(1).strip()
                # Stop before subsequent field labels on the same or adjacent lines
                val = re.split(r"\b(?:Date|DOB|Blood|Address|Licence|License|DL|Issue|Valid|S/O|Father|Holder|Signature)\b", val, flags=re.IGNORECASE)[0].strip()
                val = re.sub(r"\s{2,}.*$", "", val).strip()
                val = re.sub(r"[@\d]+.*$", "", val).strip()
                val = re.sub(r"\s+", " ", val).strip()
                if val and val.lower() != "blood group" and len(val) >= 3:
                    fields["name"] = val
                    break

        # 3. Date of Birth (Supports DD-MM-YYYY, YYYY-MM-DD, DD/MM/YYYY)
        for src in combined_sources:
            dob_match = re.search(
                r"(?:Date\s*of\s*Birth|DOB|Birth\s*Date)[:=\s]*(\d{4}[/-]\d{1,2}[/-]\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
                src,
                re.IGNORECASE,
            )
            if dob_match:
                fields["date_of_birth"] = dob_match.group(1).strip()
                break

        # 4. Blood Group (STRICT validation: only A+, A-, B+, B-, AB+, AB-, O+, O-)
        VALID_BLOOD_GROUPS = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}
        blood_val = None
        for src in combined_sources:
            bg_match = re.search(
                r"(?:Blood\s*Group|BG)[:=\s]*([ABO][+-]|AB[+-])(?![A-Za-z0-9+-])",
                src,
                re.IGNORECASE,
            )
            if bg_match:
                candidate = bg_match.group(1).upper()
                if candidate in VALID_BLOOD_GROUPS:
                    blood_val = candidate
                    break
        fields["blood_group"] = blood_val

        # 5. Issue Date & Expiry Date (Handling adjacent column headers, labels, and chronology)
        issue_date: Optional[str] = None
        expiry_date: Optional[str] = None

        # A. Direct label matches
        for src in combined_sources:
            if not issue_date:
                iss_m = re.search(
                    r"(?:Date\s*Of\s*First\s*Issue|Date\s*of\s*Issue|Issue\s*Date|DOI)[:=\s]*(\d{4}[/-]\d{1,2}[/-]\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
                    src,
                    re.IGNORECASE,
                )
                if iss_m:
                    issue_date = iss_m.group(1).strip()

            if not expiry_date:
                exp_m = re.search(
                    r"(?:Valid\s*Till|Expiry\s*Date|Date\s*of\s*Expiry|Valid\s*Upto|Validity(?:\s*\([A-Z]+\))?)[:=\s]*(\d{4}[/-]\d{1,2}[/-]\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
                    src,
                    re.IGNORECASE,
                )
                if exp_m:
                    expiry_date = exp_m.group(1).strip()

        # B. Header line + date row pattern (e.g. Issue Date Validity(NT) \n 18-08-2026 19-09-2045)
        if not (issue_date and expiry_date):
            for src in combined_sources:
                header_m = re.search(
                    r"(Issue\s*Date).*?(Validity[^\n\r]*)\n[^\d\n\r]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})",
                    src,
                    re.IGNORECASE,
                )
                if header_m:
                    if not issue_date:
                        issue_date = header_m.group(3).strip()
                    if not expiry_date:
                        expiry_date = header_m.group(4).strip()
                    break

        # C. Chronological resolution across all non-DOB dates
        if not (issue_date and expiry_date):
            all_dates: List[str] = []
            for src in combined_sources:
                found = re.findall(r"\b(?:\d{4}[/-]\d{1,2}[/-]\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b", src)
                for d in found:
                    if d not in all_dates:
                        all_dates.append(d)

            dob_val = fields.get("date_of_birth")
            candidate_dates = [d for d in all_dates if d != dob_val]

            def parse_date_year(d_str: str) -> int:
                parts = re.split(r"[-/]", d_str)
                return int(parts[0]) if len(parts[0]) == 4 else int(parts[2])

            if len(candidate_dates) >= 2 and not issue_date and not expiry_date:
                sorted_by_year = sorted(candidate_dates, key=parse_date_year)
                issue_date = sorted_by_year[0]
                expiry_date = sorted_by_year[-1]
            elif len(candidate_dates) == 1:
                single_yr = parse_date_year(candidate_dates[0])
                if single_yr >= 2030 and not expiry_date:
                    expiry_date = candidate_dates[0]
                elif not issue_date:
                    issue_date = candidate_dates[0]

        fields["issue_date"] = issue_date
        fields["expiry_date"] = expiry_date

        # 6. Address (combines multiple address lines while excluding subsequent headers/signatures)
        for src in combined_sources:
            addr_m = re.search(
                r"(?:Permanent\s*Address|Present\s*Address|Address)[:=\s]+([^\n\r]+(?:\n[^\n\r]+){0,5})",
                src,
                re.IGNORECASE,
            )
            if addr_m:
                raw_lines = [l.strip() for l in addr_m.group(1).splitlines() if l.strip()]
                clean_addr_lines: List[str] = []
                for l in raw_lines:
                    if re.search(
                        r"^(?:DL\s*No|Driving\s*Licence|Issued\s*by|Emergency|Holder|Signature|Name|Date\s*of\s*Birth|DOB|Valid|Present)",
                        l,
                        re.IGNORECASE,
                    ):
                        break
                    cl = re.sub(r"\s{3,}.*$", "", l).strip()
                    cl = re.sub(r"^[^\w\d]+", "", cl).strip()
                    if cl and len(cl) > 1:
                        clean_addr_lines.append(cl)
                if clean_addr_lines:
                    combined_addr = ", ".join(clean_addr_lines)
                    combined_addr = re.sub(r",\s*,+", ",", combined_addr)
                    combined_addr = re.sub(r"\s+", " ", combined_addr).strip()
                    if len(combined_addr) >= 5:
                        fields["address"] = combined_addr
                        break

        # 7. Issuing Authority
        for src in combined_sources:
            auth_m = (
                re.search(r"Issued\s*by\s+([A-Za-z\s]+?)(?:\n|$)", src, re.IGNORECASE)
                or re.search(r"Licencing\s*Authority[:=\s\n]+([A-Za-z\s]+?)(?:\n|$)", src, re.IGNORECASE)
            )
            if auth_m:
                val = auth_m.group(1).strip()
                val = re.sub(r"\s+", " ", val).strip()
                if len(val) >= 3 and not re.search(r"^(?:Validity|Date|Number|Badge)", val, re.IGNORECASE):
                    fields["issuing_authority"] = val
                    break

        return fields

    def _extract_passport_fields(self, text: str) -> Dict[str, Any]:
        fields: Dict[str, Any] = {}

        # 1. Passport Number
        pass_match = re.search(r"\b([A-PR-WYa-pr-wy][1-9]\d\s?\d{4}[1-9])\b", text)
        if pass_match:
            fields["passport_number"] = pass_match.group(1).strip()

        # 2. Name
        name_match = re.search(r"(?:Given\s*Name[s]?|Name)[:\s]+([A-Za-z][^\r\n,;]+)", text, re.IGNORECASE)
        if name_match:
            fields["name"] = name_match.group(1).strip()

        # 3. Nationality
        nat_match = re.search(r"(?:Nationality)[:\s]+([A-Za-z]+)", text, re.IGNORECASE)
        if nat_match:
            fields["nationality"] = nat_match.group(1).strip()

        # 4. Date of Birth
        dob_match = re.search(r"(?:Date\s*of\s*Birth|DOB)[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", text, re.IGNORECASE)
        if dob_match:
            fields["date_of_birth"] = dob_match.group(1).strip()

        # 5. Issue Date
        issue_match = re.search(r"(?:Date\s*of\s*Issue)[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", text, re.IGNORECASE)
        if issue_match:
            fields["issue_date"] = issue_match.group(1).strip()

        # 6. Expiry Date
        exp_match = re.search(r"(?:Date\s*of\s*Expiry)[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", text, re.IGNORECASE)
        if exp_match:
            fields["expiry_date"] = exp_match.group(1).strip()

        return fields

    def _extract_pan_card_fields(self, text: str) -> Dict[str, Any]:
        fields: Dict[str, Any] = {}

        # 1. PAN Number
        pan_match = re.search(r"\b([A-Z]{5}[0-9]{4}[A-Z]{1})\b", text)
        if pan_match:
            fields["pan_number"] = pan_match.group(1)

        # 2. Name
        name_match = re.search(r"(?:Name)[:\s]+([A-Za-z][^\r\n,;]+)", text, re.IGNORECASE)
        if name_match:
            fields["name"] = name_match.group(1).strip()

        # 3. Father's Name
        father_match = re.search(r"(?:Father['’]?s?\s*Name)[:\s]+([A-Za-z][^\r\n,;]+)", text, re.IGNORECASE)
        if father_match:
            fields["father_name"] = father_match.group(1).strip()

        # 4. Date of Birth
        dob_match = re.search(r"(?:DOB|Date\s*of\s*Birth)[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", text, re.IGNORECASE)
        if dob_match:
            fields["date_of_birth"] = dob_match.group(1).strip()

        return fields

    def _extract_aadhaar_fields(self, text: str) -> Dict[str, Any]:
        fields: Dict[str, Any] = {}

        # 1. Aadhaar Number (Masked)
        aadhaar_match = re.search(r"\b(\d{4}\s\d{4}\s\d{4})\b", text)
        if aadhaar_match:
            raw = aadhaar_match.group(1)
            fields["aadhaar_number"] = f"XXXX XXXX {raw[-4:]}"

        # 2. Date of Birth / Year of Birth
        dob_match = re.search(r"(?:DOB|Date\s*of\s*Birth)[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", text, re.IGNORECASE)
        yob_match = re.search(r"(?:Year\s*of\s*Birth|YOB)[:\s]*(\d{4})", text, re.IGNORECASE)
        if dob_match:
            fields["date_of_birth"] = dob_match.group(1).strip()
        elif yob_match:
            fields["year_of_birth"] = yob_match.group(1).strip()

        # 3. Gender
        gender_match = re.search(r"\b(Female|Male|Transgender)\b", text, re.IGNORECASE)
        if gender_match:
            fields["gender"] = gender_match.group(1).capitalize()

        return fields

    def _extract_salary_slip_fields(self, text: str) -> Dict[str, Any]:
        fields: Dict[str, Any] = {}

        # 1. Employee Name
        emp_match = re.search(r"(?:Employee\s*Name|Emp\s*Name)[:\s]+([A-Za-z][^\r\n,;]+)", text, re.IGNORECASE)
        if emp_match:
            fields["employee_name"] = emp_match.group(1).strip()

        # 2. Company / Employer
        company_match = re.search(r"\b([A-Z][A-Za-z0-9\s]+(?:Pvt\.?\s*Ltd\.?|Limited|LLP|Inc\.?|Corp\.?))\b", text)
        if company_match:
            fields["company_name"] = company_match.group(1).strip()

        # 3. Pay Period
        period_match = re.search(r"(?:Pay\s*Period|Month|Salary\s*Month)[:\s]+([A-Za-z0-9/\-\s]+)", text, re.IGNORECASE)
        if period_match:
            fields["pay_period"] = period_match.group(1).strip()

        # 4. Gross Salary
        gross_match = re.search(r"(?:Gross\s*(?:Salary|Pay|Earnings))[:\s]*(" + self.CURRENCY_PATTERN + ")", text, re.IGNORECASE)
        if gross_match:
            fields["gross_salary"] = gross_match.group(1).strip()

        # 5. Net Salary
        net_match = re.search(r"(?:Net\s*(?:Salary|Pay)|Take\s*Home)[:\s]*(" + self.CURRENCY_PATTERN + ")", text, re.IGNORECASE)
        if net_match:
            fields["net_salary"] = net_match.group(1).strip()

        # 6. Total Deductions
        ded_match = re.search(r"(?:Total\s*Deductions|Deductions)[:\s]*(" + self.CURRENCY_PATTERN + ")", text, re.IGNORECASE)
        if ded_match:
            fields["total_deductions"] = ded_match.group(1).strip()

        return fields

    def _extract_invoice_fields(self, text: str) -> Dict[str, Any]:
        fields: Dict[str, Any] = {}

        # 1. Invoice Number
        inv_match = re.search(r"(?:Invoice\s*(?:No|Number|#)|Bill\s*No)[:\s]*([A-Za-z0-9\-_/]+)", text, re.IGNORECASE)
        if inv_match:
            fields["invoice_number"] = inv_match.group(1).strip()

        # 2. Invoice Date
        date_match = re.search(r"(?:Invoice\s*Date|Date)[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", text, re.IGNORECASE)
        if date_match:
            fields["invoice_date"] = date_match.group(1).strip()

        # 3. Due Date
        due_match = re.search(r"(?:Due\s*Date)[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", text, re.IGNORECASE)
        if due_match:
            fields["due_date"] = due_match.group(1).strip()

        # 4. Total Amount
        tot_match = re.search(r"(?:Total\s*(?:Amount|Due)?|Grand\s*Total)[:\s]*(" + self.CURRENCY_PATTERN + ")", text, re.IGNORECASE)
        if tot_match:
            fields["total_amount"] = tot_match.group(1).strip()

        # 5. Subtotal
        sub_match = re.search(r"(?:Subtotal|Sub\s*Total)[:\s]*(" + self.CURRENCY_PATTERN + ")", text, re.IGNORECASE)
        if sub_match:
            fields["subtotal"] = sub_match.group(1).strip()

        # 6. GSTIN / Tax ID
        gst_match = re.search(r"\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1})\b", text)
        if gst_match:
            fields["gstin"] = gst_match.group(1)

        # 7. Seller / Vendor
        seller_match = re.search(r"(?:Seller|Vendor|From)[:\s]+([A-Za-z0-9][^\r\n,;]+)", text, re.IGNORECASE)
        if seller_match:
            fields["seller_name"] = seller_match.group(1).strip()

        return fields

    def _extract_certificate_fields(self, text: str) -> Dict[str, Any]:
        fields: Dict[str, Any] = {}

        # 1. Recipient
        recip_match = re.search(r"(?:Certif(?:y|ies)\s*that|Awarded\s*to|Presented\s*to)[:\s]+([A-Za-z][^\r\n,;]+)", text, re.IGNORECASE)
        if recip_match:
            fields["recipient_name"] = recip_match.group(1).strip()
        if recip_match:
            fields["recipient_name"] = recip_match.group(1).strip()

        # 2. Certificate Title
        title_match = re.search(r"(?:Certificate\s*of\s*[A-Za-z\s]+)", text, re.IGNORECASE)
        if title_match:
            fields["certificate_title"] = title_match.group(0).strip()

        # 3. Issue Date
        date_match = re.search(r"(?:Date|Issued\s*on)[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", text, re.IGNORECASE)
        if date_match:
            fields["issue_date"] = date_match.group(1).strip()

        # 4. Issuer / Institution
        inst_match = re.search(r"(?:University|Institute|Academy|College)\s*of\s*[A-Za-z\s]+", text, re.IGNORECASE)
        if inst_match:
            fields["institution"] = inst_match.group(0).strip()

        return fields

    def _extract_generic_fields(self, text: str) -> Dict[str, Any]:
        fields: Dict[str, Any] = {}

        # Generic dates
        dates: List[str] = []
        for p in self.DATE_PATTERNS:
            found = re.findall(p, text, re.IGNORECASE)
            dates.extend(found)
        if dates:
            fields["dates_detected"] = list(dict.fromkeys(dates))[:3]

        # Generic email
        email_match = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", text)
        if email_match:
            fields["contact_email"] = email_match.group(0)

        # Generic reference numbers
        ref_match = re.search(r"(?:Ref|Reference|Doc\s*ID)[:\s]*([A-Za-z0-9\-_]+)", text, re.IGNORECASE)
        if ref_match:
            fields["reference_number"] = ref_match.group(1).strip()

        return fields


field_extractor = DocumentFieldExtractor()
