from typing import Dict, Any, List, Optional
from datetime import datetime
import re
from backend.utils.logger import logger

class ContentConsistencyService:
    """
    Validates logical, chronological, and structural relationships
    across extracted fields according to document type.
    """

    DATE_FORMATS = [
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d/%m/%y",
        "%d-%m-%y",
        "%d %b %Y",
        "%d %B %Y",
    ]

    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        if not date_str:
            return None
        cleaned = date_str.strip()
        for fmt in self.DATE_FORMATS:
            try:
                return datetime.strptime(cleaned, fmt)
            except ValueError:
                continue
        # Fallback regex for standard DD/MM/YYYY
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

    def _parse_currency(self, amount_str: Optional[str]) -> Optional[float]:
        if not amount_str:
            return None
        cleaned = amount_str.strip()
        is_negative = cleaned.startswith("-") or (cleaned.startswith("(") and cleaned.endswith(")"))
        clean = re.sub(r"[^\d\.]", "", cleaned.replace(",", ""))
        try:
            val = float(clean)
            return -val if is_negative else val
        except ValueError:
            return None

    def validate(self, fields: Dict[str, Any], document_type: str) -> List[Dict[str, Any]]:
        checks: List[Dict[str, Any]] = []

        # 1. Chronological Date Consistency (Issue Date vs Expiry Date vs Date of Birth)
        dob = self._parse_date(fields.get("date_of_birth"))
        doi = self._parse_date(fields.get("issue_date") or fields.get("invoice_date"))
        doe = self._parse_date(fields.get("expiry_date") or fields.get("due_date"))

        date_issues: List[str] = []

        if doi and doe and doi > doe:
            date_issues.append(
                f"Contradictory dates: Issue date ({doi.strftime('%Y-%m-%d')}) is after Expiry/Due date ({doe.strftime('%Y-%m-%d')})."
            )

        if dob and doi and dob > doi:
            date_issues.append(
                f"Impossible dates: Date of Birth ({dob.strftime('%Y-%m-%d')}) is after Issue date ({doi.strftime('%Y-%m-%d')})."
            )

        if doi and doi.year > datetime.now().year + 1:
            date_issues.append(
                f"Future issue date detected: {doi.strftime('%Y-%m-%d')}."
            )

        if date_issues:
            checks.append({
                "check": "date_chronology",
                "status": "warning",
                "severity": "high",
                "message": "Chronological inconsistency detected in document dates.",
                "evidence": {"issues": date_issues},
            })
        else:
            checks.append({
                "check": "date_chronology",
                "status": "pass",
                "severity": "low",
                "message": "Extracted dates exhibit logical chronological progression.",
                "evidence": {},
            })

        # 2. Statement Period Consistency (For Bank Statement)
        if document_type == "Bank Statement":
            period_str = fields.get("statement_period", "")
            dates_in_period = re.findall(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", period_str)
            if len(dates_in_period) >= 2:
                p_start = self._parse_date(dates_in_period[0])
                p_end = self._parse_date(dates_in_period[1])
                if p_start and p_end and p_start > p_end:
                    checks.append({
                        "check": "statement_period_logic",
                        "status": "warning",
                        "severity": "medium",
                        "message": "Statement period start date is after end date.",
                        "evidence": {"period_text": period_str},
                    })
                else:
                    checks.append({
                        "check": "statement_period_logic",
                        "status": "pass",
                        "severity": "low",
                        "message": "Statement period boundaries are logically consistent.",
                        "evidence": {},
                    })

        # 3. Invoice Financial Balance Consistency
        if document_type == "Invoice":
            subtotal = self._parse_currency(fields.get("subtotal"))
            total = self._parse_currency(fields.get("total_amount"))
            if subtotal is not None and total is not None:
                if total < 0 or subtotal < 0:
                    checks.append({
                        "check": "invoice_math",
                        "status": "warning",
                        "severity": "medium",
                        "message": "Negative invoice amount detected.",
                        "evidence": {"subtotal": subtotal, "total": total},
                    })
                elif subtotal > total and (subtotal - total) > 1.0:
                    # Unless a large discount exists, subtotal generally <= total
                    checks.append({
                        "check": "invoice_math",
                        "status": "warning",
                        "severity": "low",
                        "message": "Subtotal exceeds total invoice amount.",
                        "evidence": {"subtotal": subtotal, "total": total},
                    })
                else:
                    checks.append({
                        "check": "invoice_math",
                        "status": "pass",
                        "severity": "low",
                        "message": "Invoice amounts are within plausible arithmetic range.",
                        "evidence": {"subtotal": subtotal, "total": total},
                    })

        # 4. Identity Number Structural Integrity
        if document_type == "PAN Card":
            pan = fields.get("pan_number", "")
            if pan and not re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$", pan):
                checks.append({
                    "check": "identifier_syntax",
                    "status": "warning",
                    "severity": "high",
                    "message": "PAN number does not match official 10-character syntax (AAAAA9999A).",
                    "evidence": {"pan": pan},
                })
            else:
                checks.append({
                    "check": "identifier_syntax",
                    "status": "pass",
                    "severity": "low",
                    "message": "PAN identifier syntax conforms to standard format.",
                    "evidence": {},
                })

        return checks

content_consistency_service = ContentConsistencyService()
