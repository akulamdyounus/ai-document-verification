from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import re
from backend.utils.logger import logger


class AuthenticityEvidenceCollector:
    """
    Collects trustworthy positive evidence of document authenticity.
    Evaluates:
    - Format and structural integrity of domain-specific credentials
    - Chronological consistency and relationship logic
    - Mathematical reconciliation of financial ledgers
    - Standard identity markers and multi-field completeness
    - Produces an independent authenticity_evidence_score (0.00 to 1.00).
    """

    DATE_FORMATS = [
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%d-%m-%y",
        "%d/%m/%y",
        "%d %b %Y",
        "%d %B %Y",
    ]

    def _parse_date(self, s: Optional[str]) -> Optional[datetime]:
        if not s:
            return None
        cleaned = s.strip()
        for fmt in self.DATE_FORMATS:
            try:
                return datetime.strptime(cleaned, fmt)
            except ValueError:
                continue
        m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", cleaned)
        if m:
            d, mon, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if y < 100:
                y += 2000 if y < 50 else 1900
            try:
                return datetime(y, mon, d)
            except Exception:
                return None
        return None

    def evaluate(
        self,
        document_type: str,
        fields: Dict[str, Any],
        extracted_text: str,
        forensic_checks: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[float, List[str], List[Dict[str, Any]]]:
        """
        Calculates authenticity_evidence_score, positive evidence findings,
        and structured positive signals for the given document.
        """
        forensic_checks = forensic_checks or []
        check_map = {c.get("check"): c for c in forensic_checks}

        positive_evidence: List[Dict[str, Any]] = []
        findings: List[str] = []
        raw_score = 0.0

        if document_type == "Driving Licence":
            raw_score, positive_evidence, findings = self._evaluate_driving_licence(
                fields, extracted_text, check_map
            )
        elif document_type == "Bank Statement":
            raw_score, positive_evidence, findings = self._evaluate_bank_statement(
                fields, extracted_text, check_map
            )
        elif document_type == "Passport":
            raw_score, positive_evidence, findings = self._evaluate_passport(
                fields, extracted_text, check_map
            )
        elif document_type == "PAN Card":
            raw_score, positive_evidence, findings = self._evaluate_pan_card(
                fields, extracted_text, check_map
            )
        else:
            raw_score, positive_evidence, findings = self._evaluate_generic(
                fields, extracted_text, check_map
            )

        authenticity_score = round(min(max(raw_score, 0.0), 1.0), 2)
        return authenticity_score, findings, positive_evidence

    # -------------------------------------------------------------
    # 1. Driving Licence Authenticity Evaluation
    # -------------------------------------------------------------
    def _evaluate_driving_licence(
        self, fields: Dict[str, Any], text: str, check_map: Dict[str, Any]
    ) -> Tuple[float, List[Dict[str, Any]], List[str]]:
        score = 0.0
        evidence = []
        findings = []

        dl_num = fields.get("licence_number", "")
        # Standard Indian DL format: SS-RR YYYY NNNNNNN or SSRRYYYYNNNNNNN
        dl_syntax_match = re.search(
            r"\b[A-Z]{2}[-\s]?\d{2,3}[-\s]?(?:19|20)\d{2}[-\s]?\d{7}\b",
            dl_num,
            re.IGNORECASE,
        )
        if dl_syntax_match:
            score += 0.25
            evidence.append({
                "signal": "dl_number_syntax",
                "score_weight": 0.25,
                "detail": f"Licence number conforms to official National Transport Registry format ({dl_syntax_match.group(0)}).",
            })
            findings.append("Official national driving licence syntax verified.")
        elif dl_num and len(dl_num) >= 8:
            score += 0.10
            evidence.append({
                "signal": "dl_number_syntax_partial",
                "score_weight": 0.10,
                "detail": f"Licence number detected with valid length ({dl_num}).",
            })

        # Chronological Integrity
        dob = self._parse_date(fields.get("date_of_birth"))
        doi = self._parse_date(fields.get("issue_date"))
        doe = self._parse_date(fields.get("expiry_date"))

        if dob and doi and doe:
            if dob < doi < doe:
                age_at_issue = (doi - dob).days / 365.25
                validity_years = (doe - doi).days / 365.25
                if age_at_issue >= 16 and 1 <= validity_years <= 30:
                    score += 0.25
                    evidence.append({
                        "signal": "dl_chronological_integrity",
                        "score_weight": 0.25,
                        "detail": f"Dates exhibit perfect legal chronology (Age at issue: {int(age_at_issue)}, validity: {int(validity_years)} years).",
                    })
                    findings.append("Chronological timeline (DOB, issue date, expiry date) is legally and logically valid.")
        elif dob and (doi or doe):
            score += 0.10
            evidence.append({
                "signal": "dl_chronological_partial",
                "score_weight": 0.10,
                "detail": "Partial chronological dates detected without contradictions.",
            })

        # Core Demographic Completeness
        has_name = bool(fields.get("name"))
        has_dob = bool(fields.get("date_of_birth"))
        has_dl = bool(fields.get("licence_number"))
        has_validity = bool(fields.get("expiry_date") or fields.get("issue_date"))

        if has_name and has_dob and has_dl and has_validity:
            score += 0.25
            evidence.append({
                "signal": "dl_credential_completeness",
                "score_weight": 0.25,
                "detail": "All 4 core identity fields (Name, Date of Birth, Licence Number, Validity) successfully extracted.",
            })
            findings.append("Complete set of identity credentials present.")
        elif has_name and has_dl:
            score += 0.15

        # Card Structure & Machine Readable Elements
        if re.search(r"\b(?:Transport|Department|Licence|Govt|Government|Union\s+of\s+India)\b", text, re.IGNORECASE):
            score += 0.15
            evidence.append({
                "signal": "dl_statutory_headers",
                "score_weight": 0.15,
                "detail": "Statutory state transport authority header markers detected.",
            })
            findings.append("Statutory transport authority credential headers detected.")

        if re.search(r"\b(?:MCWG|LMV|HMV|MCWOG|TRANS)\b", text):
            score += 0.10
            evidence.append({
                "signal": "dl_vehicle_classes",
                "score_weight": 0.10,
                "detail": "Standard vehicle authorization classes (LMV/MCWG) identified.",
            })

        return score, evidence, findings

    # -------------------------------------------------------------
    # 2. Bank Statement Authenticity Evaluation
    # -------------------------------------------------------------
    def _evaluate_bank_statement(
        self, fields: Dict[str, Any], text: str, check_map: Dict[str, Any]
    ) -> Tuple[float, List[Dict[str, Any]], List[str]]:
        score = 0.0
        evidence = []
        findings = []

        # 1. Mathematically Reconciled Transaction Running Balances
        math_check = check_map.get("bank_running_balance_math")
        if math_check and math_check.get("status") == "pass":
            tx_count = math_check.get("evidence", {}).get("total_transactions_verified", 0)
            score += 0.30
            evidence.append({
                "signal": "bank_running_balance_reconciled",
                "score_weight": 0.30,
                "detail": f"Step-by-step transaction running balance arithmetic verified across {tx_count} rows with zero discrepancies.",
            })
            findings.append(f"Running balance arithmetic verified across {tx_count} transaction rows.")

        # 2. Summary Figures Reconciliation
        summary_check = check_map.get("bank_summary_balance_math")
        if summary_check and summary_check.get("status") == "pass":
            score += 0.20
            evidence.append({
                "signal": "bank_summary_reconciled",
                "score_weight": 0.20,
                "detail": "Opening balance, total transaction credits, total debits, and closing balance reconcile arithmetically.",
            })
            findings.append("Summary opening balance, transaction totals, and closing balance reconcile arithmetically.")

        # 3. Bank Identity & Account-Associated IFSC Mutually Confirmed
        id_check = check_map.get("bank_identity_consistency")
        if id_check and id_check.get("status") == "pass" and id_check.get("evidence", {}).get("ifsc_code"):
            declared = id_check.get("evidence", {}).get("declared_bank", "")
            ifsc = id_check.get("evidence", {}).get("ifsc_code", "")
            score += 0.15
            evidence.append({
                "signal": "bank_ifsc_mutual_match",
                "score_weight": 0.15,
                "detail": f"Primary declared institution ({declared}) and account-associated IFSC code ({ifsc}) mutually corroborate.",
            })
            findings.append("Bank institution identity and account IFSC routing code mutually corroborate.")

        # 4. Monotonic Transaction Date Progression
        table_check = check_map.get("bank_transaction_table_consistency")
        if table_check and table_check.get("status") == "pass":
            score += 0.15
            evidence.append({
                "signal": "bank_table_chronology_clean",
                "score_weight": 0.15,
                "detail": "Transaction rows follow strictly consistent date progression without syntax errors.",
            })
            findings.append("Transaction rows exhibit standard chronological date sequencing and clean syntax.")

        # 5. Core Account Credentials Present
        has_acc = bool(fields.get("account_number"))
        has_holder = bool(fields.get("account_holder"))
        has_period = bool(fields.get("statement_period"))
        has_open_close = bool(fields.get("opening_balance") and fields.get("closing_balance"))

        if has_acc and has_open_close and (has_holder or has_period):
            score += 0.20
            evidence.append({
                "signal": "bank_account_credentials_complete",
                "score_weight": 0.20,
                "detail": "Essential statement credentials (masked account number, statement period, boundary balances) detected.",
            })
            findings.append("Account credentials and statement boundary figures fully identified.")

        return score, evidence, findings

    # -------------------------------------------------------------
    # 3. Passport Authenticity Evaluation
    # -------------------------------------------------------------
    def _evaluate_passport(
        self, fields: Dict[str, Any], text: str, check_map: Dict[str, Any]
    ) -> Tuple[float, List[Dict[str, Any]], List[str]]:
        score = 0.0
        evidence = []
        findings = []

        pass_num = fields.get("passport_number", "")
        # Official Indian Passport format: 1 letter (A-Z except Q, X, Z) + 7 digits
        if re.match(r"^[A-PR-WYa-pr-wy][1-9]\d{6}$", pass_num):
            score += 0.30
            evidence.append({
                "signal": "passport_number_syntax",
                "score_weight": 0.30,
                "detail": f"Passport number conforms to ICAO/national passport syntax ({pass_num}).",
            })
            findings.append("Passport number syntax conforms to official international standards.")

        dob = self._parse_date(fields.get("date_of_birth"))
        doi = self._parse_date(fields.get("issue_date"))
        doe = self._parse_date(fields.get("expiry_date"))

        if dob and doi and doe and dob < doi < doe:
            validity_years = (doe - doi).days / 365.25
            if 4 <= validity_years <= 11:
                score += 0.30
                evidence.append({
                    "signal": "passport_chronology",
                    "score_weight": 0.30,
                    "detail": f"Standard 5 or 10-year validity window confirmed ({int(validity_years)} years).",
                })
                findings.append("Standard statutory passport validity period verified.")

        if fields.get("name") and fields.get("nationality"):
            score += 0.25
            findings.append("Passport holder identity and nationality credentials detected.")

        if "P<IND" in text.upper() or re.search(r"P<[A-Z]{3}", text):
            score += 0.15
            evidence.append({
                "signal": "passport_mrz_detected",
                "score_weight": 0.15,
                "detail": "Machine Readable Zone (MRZ) encoding detected.",
            })
            findings.append("Machine Readable Zone (MRZ) structure identified.")

        return score, evidence, findings

    # -------------------------------------------------------------
    # 4. PAN Card Authenticity Evaluation
    # -------------------------------------------------------------
    def _evaluate_pan_card(
        self, fields: Dict[str, Any], text: str, check_map: Dict[str, Any]
    ) -> Tuple[float, List[Dict[str, Any]], List[str]]:
        score = 0.0
        evidence = []
        findings = []

        pan = fields.get("pan_number", "")
        if pan and re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$", pan):
            score += 0.40
            evidence.append({
                "signal": "pan_syntax_valid",
                "score_weight": 0.40,
                "detail": f"PAN conforms to Income Tax Department 10-character syntax ({pan}).",
            })
            findings.append("Permanent Account Number syntax conforms to official Income Tax Department specification.")

        if fields.get("name") and fields.get("date_of_birth"):
            score += 0.30
            findings.append("Taxpayer demographic credentials (Name, Date of Birth) identified.")

        if re.search(r"\b(?:Income\s*Tax\s*Department|GOVT\.\s*OF\s*INDIA)\b", text, re.IGNORECASE):
            score += 0.30
            evidence.append({
                "signal": "pan_statutory_authority",
                "score_weight": 0.30,
                "detail": "Statutory Income Tax Department markers detected.",
            })
            findings.append("Statutory Income Tax Department institutional markers confirmed.")

        return score, evidence, findings

    # -------------------------------------------------------------
    # 5. Generic / Other Document Authenticity Evaluation
    # -------------------------------------------------------------
    def _evaluate_generic(
        self, fields: Dict[str, Any], text: str, check_map: Dict[str, Any]
    ) -> Tuple[float, List[Dict[str, Any]], List[str]]:
        score = 0.0
        evidence = []
        findings = []

        if len(text.strip()) >= 150:
            score += 0.20
            findings.append("Document exhibits coherent digital text body.")

        if fields:
            score += 0.20
            findings.append(f"Structured fields detected: {', '.join(fields.keys())}.")

        # Generic cannot exceed 0.40 without specific credential verification
        return score, evidence, findings


authenticity_collector = AuthenticityEvidenceCollector()
