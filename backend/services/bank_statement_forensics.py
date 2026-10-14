from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import re
import fitz  # PyMuPDF
from backend.utils.logger import logger


class BankStatementForensicsService:
    """
    Forensic verification service for Bank Statements.
    Implements multi-dimensional consistency checks:
    1. Transaction arithmetic consistency (running balance & summary balance)
    2. Transaction table consistency (date ordering, syntax, duplicates)
    3. Extracted-field & bank identity consistency (IFSC prefix vs bank name, footer branding)
    4. Multi-page consistency (account number across pages, layout continuity)
    5. PDF text forensics (overlapping text spans, font family deviations)
    """

    BANK_IFSC_MAP = {
        "HDFC": ("HDFC Bank", "HDFC"),
        "UTIB": ("Axis Bank", "UTIB"),
        "SBIN": ("State Bank of India", "SBIN"),
        "ICIC": ("ICICI Bank", "ICIC"),
        "KKBK": ("Kotak Mahindra Bank", "KKBK"),
        "BARB": ("Bank of Baroda", "BARB"),
        "PUNB": ("Punjab National Bank", "PUNB"),
        "CNRB": ("Canara Bank", "CNRB"),
        "UBIN": ("Union Bank of India", "UBIN"),
        "INDB": ("IndusInd Bank", "INDB"),
        "YESB": ("Yes Bank", "YESB"),
        "IBKL": ("IDBI Bank", "IBKL"),
        "SCBL": ("Standard Chartered Bank", "SCBL"),
        "HSBC": ("HSBC", "HSBC"),
        "CITI": ("Citibank", "CITI"),
    }

    DATE_FORMATS = [
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%d-%m-%y",
        "%d/%m/%y",
        "%d %b %Y",
        "%d %B %Y",
    ]

    def _parse_date(self, s: str) -> Optional[datetime]:
        if not s:
            return None
        cleaned = s.strip()
        for fmt in self.DATE_FORMATS:
            try:
                return datetime.strptime(cleaned, fmt)
            except ValueError:
                continue
        # Fallback regex
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

    def _parse_amount(self, token: str) -> Tuple[Optional[float], bool]:
        """
        Parses monetary string.
        Returns (amount, has_syntax_error).
        Detects amateur fraud typos such as '150000..00' (multiple decimal points).
        """
        if not token:
            return None, False
        cleaned = token.strip().replace(",", "")
        has_double_dot = ".." in cleaned or cleaned.count(".") > 1
        if has_double_dot:
            # Replace double dots with single dot for arithmetic recovery
            cleaned = re.sub(r"\.+", ".", cleaned)
        clean_num = re.sub(r"[^\d\.-]", "", cleaned)
        try:
            val = float(clean_num)
            return val, has_double_dot
        except Exception:
            return None, False

    def _get_font_family(self, font_name: str) -> str:
        """Normalizes font name to core family (e.g. 'Times New Roman,Bold' -> 'times new roman')."""
        clean = re.sub(r"[,+-].*", "", font_name)
        clean = re.sub(r"^(?:[A-Z]{6}\+)", "", clean)  # Strip PDF subset prefix
        return clean.strip().lower()

    # -------------------------------------------------------------
    # 1. Transaction Table Extraction
    # -------------------------------------------------------------

    def _extract_transactions_from_pdf(self, doc: fitz.Document) -> List[Dict[str, Any]]:
        """
        Extracts structured transaction rows from PDF page word geometry.
        Reconstructs multiline wrapped cells reliably.
        """
        date_regex = re.compile(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$")
        transactions: List[Dict[str, Any]] = []

        max_pages = min(len(doc), 10)
        for pno in range(max_pages):
            page = doc[pno]
            words = page.get_text("words")
            if not words:
                continue

            lines_dict: Dict[float, List[Any]] = {}
            for w in words:
                y_approx = round(w[1], 0)
                matched_y = None
                for y in lines_dict:
                    if abs(y - y_approx) <= 3.5:
                        matched_y = y
                        break
                if matched_y is None:
                    matched_y = y_approx
                    lines_dict[matched_y] = []
                lines_dict[matched_y].append(w)

            sorted_y = sorted(lines_dict.keys())
            current_tx: Optional[Dict[str, Any]] = None

            for y in sorted_y:
                line_words = sorted(lines_dict[y], key=lambda w: w[0])
                first_word = line_words[0][4].strip()
                line_str = " ".join(w[4].strip() for w in line_words)

                if date_regex.match(first_word):
                    if current_tx:
                        transactions.append(current_tx)
                    current_tx = {
                        "date": first_word,
                        "words": line_words,
                        "text": line_str,
                        "page": pno + 1,
                    }
                elif current_tx:
                    if any(
                        k in line_str.upper()
                        for k in [
                            "TRANSACTION TOTAL",
                            "CLOSING BALANCE",
                            "CHARGE BREAKUP",
                            "STATEMENT SUMMARY",
                        ]
                    ):
                        transactions.append(current_tx)
                        current_tx = None
                    else:
                        current_tx["words"].extend(line_words)
                        current_tx["text"] += " " + line_str

            if current_tx:
                transactions.append(current_tx)

        return transactions

    def _extract_transactions_from_text(self, text: str) -> List[Dict[str, Any]]:
        """Fallback transaction extractor from plain/OCR text lines."""
        date_regex = re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b")
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        transactions: List[Dict[str, Any]] = []
        current_tx: Optional[Dict[str, Any]] = None

        for line in lines:
            m = date_regex.search(line)
            tokens = line.split()
            if m and (line.startswith(m.group(1)) or (tokens and date_regex.match(tokens[0]))):
                d_str = m.group(1)
                if current_tx:
                    transactions.append(current_tx)
                current_tx = {
                    "date": d_str,
                    "text": line,
                    "page": 1,
                }
            elif current_tx:
                if any(
                    k in line.upper()
                    for k in [
                        "TRANSACTION TOTAL",
                        "CLOSING BALANCE",
                        "CHARGE BREAKUP",
                        "STATEMENT SUMMARY",
                    ]
                ):
                    transactions.append(current_tx)
                    current_tx = None
                else:
                    current_tx["text"] += " " + line

        if current_tx:
            transactions.append(current_tx)

        return transactions

    # -------------------------------------------------------------
    # 2. Consistency Checks Implementation
    # -------------------------------------------------------------

    def check_running_balance_and_table(
        self,
        transactions: List[Dict[str, Any]],
        opening_balance: Optional[float] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Validates:
        1. Mathematical continuity of running balances from transaction to transaction.
        2. Transaction table integrity (malformed syntax like '150000..00', date chronology, duplicates).
        """
        running_discrepancies: List[Dict[str, Any]] = []
        malformed_syntax_issues: List[str] = []
        parsed_dates: List[Tuple[datetime, str, int]] = []
        date_inversions: List[str] = []
        seen_rows: Dict[str, int] = {}
        duplicate_rows: List[str] = []

        curr_balance = opening_balance

        for i, tx in enumerate(transactions):
            t_text = tx["text"]
            t_date_str = tx["date"]
            t_page = tx.get("page", 1)

            # Date check
            dt = self._parse_date(t_date_str)
            if dt:
                parsed_dates.append((dt, t_date_str, t_page))
            else:
                malformed_syntax_issues.append(f"Invalid transaction date '{t_date_str}' on page {t_page}")

            # Duplicate row check
            normalized_row = re.sub(r"\s+", " ", t_text.strip())
            seen_rows[normalized_row] = seen_rows.get(normalized_row, 0) + 1
            if seen_rows[normalized_row] == 2:
                duplicate_rows.append(f"{t_date_str}: {normalized_row[:60]}")

            # Extract numbers from row
            tokens = t_text.split()
            nums: List[float] = []
            for tok in tokens:
                if re.search(r"(?:\d+\.\d+|\.\d+|\d+\.\.\d+)", tok):
                    stripped = tok.strip(";,()")
                    val, has_syntax_err = self._parse_amount(stripped)
                    if has_syntax_err:
                        malformed_syntax_issues.append(
                            f"Syntax error '{stripped}' (multiple decimal points) in transaction on page {t_page}"
                        )
                    if val is not None:
                        nums.append(val)

            # Running balance validation
            # Standard row layout: [..., Amount, Balance]
            if len(nums) >= 2:
                row_amount = nums[-2]
                row_balance = nums[-1]

                if curr_balance is not None:
                    exp_credit = round(curr_balance + row_amount, 2)
                    exp_debit = round(curr_balance - row_amount, 2)

                    matches_credit = abs(row_balance - exp_credit) < 0.05
                    matches_debit = abs(row_balance - exp_debit) < 0.05

                    if not (matches_credit or matches_debit):
                        disc = round(
                            abs(row_balance - exp_credit)
                            if abs(row_balance - exp_credit) < abs(row_balance - exp_debit)
                            else abs(row_balance - exp_debit),
                            2,
                        )
                        running_discrepancies.append({
                            "tx_index": i + 1,
                            "page": t_page,
                            "date": t_date_str,
                            "prev_balance": curr_balance,
                            "row_amount": row_amount,
                            "row_balance": row_balance,
                            "expected_credit": exp_credit,
                            "expected_debit": exp_debit,
                            "discrepancy": disc,
                        })

                curr_balance = row_balance

        # Date ordering validation (allow same-day transactions)
        if len(parsed_dates) >= 4:
            asc_reversals = 0
            desc_reversals = 0
            for idx in range(len(parsed_dates) - 1):
                d1 = parsed_dates[idx][0]
                d2 = parsed_dates[idx + 1][0]
                if d1 > d2:
                    asc_reversals += 1
                if d1 < d2:
                    desc_reversals += 1

            if asc_reversals > 0 and desc_reversals > 0:
                reversals = min(asc_reversals, desc_reversals)
                if reversals >= 2:
                    date_inversions.append(
                        f"Non-monotonic transaction date sequencing: dates reverse chronological direction {reversals} times."
                    )

        # 1. Running balance check result
        if running_discrepancies:
            sample_disc = running_discrepancies[0]
            math_check = {
                "check": "bank_running_balance_math",
                "status": "warning",
                "severity": "high",
                "message": (
                    f"Mathematical inconsistency detected in transaction running balance: {len(running_discrepancies)} row(s) "
                    f"do not reconcile with previous balance and transaction amount (e.g. {sample_disc['date']} row balance "
                    f"{sample_disc['row_balance']} vs expected {sample_disc['expected_credit']} / {sample_disc['expected_debit']})."
                ),
                "evidence": {
                    "total_discrepancies": len(running_discrepancies),
                    "discrepant_rows": running_discrepancies[:4],
                },
            }
        elif len(transactions) >= 3 and curr_balance is not None:
            math_check = {
                "check": "bank_running_balance_math",
                "status": "pass",
                "severity": "low",
                "message": f"Transaction running balance progression is mathematically consistent across {len(transactions)} rows.",
                "evidence": {"total_transactions_verified": len(transactions)},
            }
        else:
            math_check = {
                "check": "bank_running_balance_math",
                "status": "info",
                "severity": "low",
                "message": "Insufficient structured transaction rows to verify running balance arithmetic.",
                "evidence": {},
            }

        # 2. Table consistency check result
        table_issues = []
        if malformed_syntax_issues:
            table_issues.extend(malformed_syntax_issues)
        if date_inversions:
            table_issues.extend(date_inversions)

        if table_issues:
            table_check = {
                "check": "bank_transaction_table_consistency",
                "status": "warning",
                "severity": "high",
                "message": f"Transaction table structural anomalies detected: {'; '.join(table_issues[:2])}",
                "evidence": {
                    "issues": table_issues,
                    "malformed_syntax_count": len(malformed_syntax_issues),
                    "date_inversions": len(date_inversions),
                },
            }
        elif duplicate_rows and len(duplicate_rows) >= 3:
            table_check = {
                "check": "bank_transaction_table_consistency",
                "status": "warning",
                "severity": "medium",
                "message": f"Suspicious repeated identical transaction rows ({len(duplicate_rows)} duplicates found).",
                "evidence": {"duplicates": duplicate_rows[:3]},
            }
        else:
            table_check = {
                "check": "bank_transaction_table_consistency",
                "status": "pass",
                "severity": "low",
                "message": "Transaction table formatting, date sequencing, and numeric syntax are consistent.",
                "evidence": {"duplicate_count": len(duplicate_rows)},
            }

        return math_check, table_check

    def check_bank_identity(self, text: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates identity consistency between declared bank, IFSC code, and legal branding/disclaimers.
        Detects template splicing where a statement from Bank A has Bank B's IFSC or footer disclaimers.
        """
        header_bank_match = re.search(
            r"(?:Statement\s+of\s+([A-Za-z]+)\s+Account|Account\s+Statement\s*-\s*([A-Za-z]+))",
            text,
            re.IGNORECASE,
        )
        declared_bank = fields.get("bank_name") or ""
        if header_bank_match:
            declared_bank = (header_bank_match.group(1) or header_bank_match.group(2)).strip()

        ifsc_code = fields.get("ifsc_code", "")
        if not ifsc_code:
            m = re.search(r"\b([A-Z]{4}0[A-Z0-9]{6})\b", text)
            if m:
                ifsc_code = m.group(1)

        conflicts: List[str] = []

        # 1. IFSC vs Declared Bank
        if ifsc_code:
            prefix = ifsc_code[:4].upper()
            if prefix in self.BANK_IFSC_MAP:
                actual_bank_name, _ = self.BANK_IFSC_MAP[prefix]
                if (
                    declared_bank
                    and declared_bank.upper() not in actual_bank_name.upper()
                    and actual_bank_name.upper() not in declared_bank.upper()
                ):
                    conflicts.append(
                        f"IFSC prefix '{prefix}' belongs to {actual_bank_name}, conflicting with declared bank '{declared_bank}'."
                    )

        # 2. Conflicting Branding / Disclaimers
        for b_code, (b_name, b_prefix) in self.BANK_IFSC_MAP.items():
            if (
                declared_bank
                and declared_bank.upper() not in b_name.upper()
                and b_name.upper() not in declared_bank.upper()
            ):
                pattern = (
                    rf"\b(?:service@{b_name.lower().replace(' ', '')}\.com|"
                    rf"{re.escape(b_name)}\s+never\s+asks|"
                    rf"REGISTERED\s+OFFICE\s*-\s*{re.escape(b_name)})\b"
                )
                if re.search(pattern, text, re.IGNORECASE):
                    conflicts.append(
                        f"Document header specifies '{declared_bank}', but footer disclaimers reference competing bank '{b_name}'."
                    )
                    break

        if conflicts:
            return {
                "check": "bank_identity_consistency",
                "status": "warning",
                "severity": "high",
                "message": f"Bank identity conflict: {conflicts[0]}",
                "evidence": {
                    "conflicts": conflicts,
                    "declared_bank": declared_bank,
                    "ifsc_code": ifsc_code,
                },
            }
        else:
            return {
                "check": "bank_identity_consistency",
                "status": "pass",
                "severity": "low",
                "message": "Bank institution identity and IFSC code are mutually consistent.",
                "evidence": {"declared_bank": declared_bank, "ifsc_code": ifsc_code},
            }

    def check_summary_balance_math(self, text: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates Opening Balance + Total Credits - Total Debits = Closing Balance.
        """
        open_val = None
        close_val = None
        tot_deb = None
        tot_cred = None

        if fields.get("opening_balance"):
            open_val, _ = self._parse_amount(str(fields["opening_balance"]))
        if fields.get("closing_balance"):
            close_val, _ = self._parse_amount(str(fields["closing_balance"]))

        tot_match = re.search(
            r"TRANSACTION\s+TOTAL\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})",
            text,
            re.IGNORECASE,
        )
        if tot_match:
            d_val, _ = self._parse_amount(tot_match.group(1))
            c_val, _ = self._parse_amount(tot_match.group(2))
            tot_deb = d_val
            tot_cred = c_val
        else:
            if fields.get("total_debits"):
                tot_deb, _ = self._parse_amount(str(fields["total_debits"]))
            if fields.get("total_credits"):
                tot_cred, _ = self._parse_amount(str(fields["total_credits"]))

        if open_val is not None and close_val is not None and tot_deb is not None and tot_cred is not None:
            calc_close = round(open_val + tot_cred - tot_deb, 2)
            calc_close_alt = round(open_val + tot_deb - tot_cred, 2)

            matches = abs(calc_close - close_val) < 1.0 or abs(calc_close_alt - close_val) < 1.0
            if not matches:
                return {
                    "check": "bank_summary_balance_math",
                    "status": "warning",
                    "severity": "high",
                    "message": (
                        f"Summary balance arithmetic mismatch: Opening balance ({open_val}) + Total Credits ({tot_cred}) "
                        f"- Total Debits ({tot_deb}) = {calc_close}, but Stated Closing balance is {close_val}."
                    ),
                    "evidence": {
                        "opening_balance": open_val,
                        "closing_balance": close_val,
                        "total_credits": tot_cred,
                        "total_debits": tot_deb,
                        "calculated_closing": calc_close,
                    },
                }
            else:
                return {
                    "check": "bank_summary_balance_math",
                    "status": "pass",
                    "severity": "low",
                    "message": "Opening balance, transaction totals, and closing balance reconcile arithmetically.",
                    "evidence": {
                        "opening_balance": open_val,
                        "closing_balance": close_val,
                        "total_credits": tot_cred,
                        "total_debits": tot_deb,
                    },
                }
        else:
            return {
                "check": "bank_summary_balance_math",
                "status": "info",
                "severity": "low",
                "message": "Summary transaction totals or boundary balances not fully specified for reconciliation.",
                "evidence": {},
            }

    def check_multipage_and_pdf_forensics(self, doc: fitz.Document) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Inspects multi-page layout, account numbers across pages, text overlays, and font family consistency.
        """
        page_count = len(doc)
        page_acc_numbers: Dict[int, str] = {}
        overlays: List[str] = []
        font_families: Dict[str, int] = {}

        max_pages = min(page_count, 10)
        for pno in range(max_pages):
            page = doc[pno]

            # 1. Account number per page
            p_text = page.get_text()
            acc_m = re.search(
                r"(?:Account\s*(?:No|Number|#)|A/C\s*(?:No|Number)?)[:\s]*(\d{9,18})",
                p_text,
                re.IGNORECASE,
            )
            if acc_m:
                page_acc_numbers[pno + 1] = acc_m.group(1)

            # 2. Text Spans inspection
            text_dict = page.get_text("dict")
            spans = []
            for b in text_dict.get("blocks", []):
                if "lines" in b:
                    for line in b["lines"]:
                        for span in line["spans"]:
                            txt = span["text"].strip()
                            if txt:
                                spans.append(
                                    (
                                        fitz.Rect(span["bbox"]),
                                        txt,
                                        span.get("font", ""),
                                        span.get("size", 0),
                                    )
                                )
                                # Track font family for monetary numbers in transaction rows
                                if re.match(r"^[\d,]+\.\d{2}$", txt):
                                    fam = self._get_font_family(span.get("font", ""))
                                    font_families[fam] = font_families.get(fam, 0) + 1

            # 3. Overlapping text spans (>70% overlap with distinct text)
            for i in range(len(spans)):
                r1, t1, _, _ = spans[i]
                for j in range(i + 1, min(i + 30, len(spans))):
                    r2, t2, _, _ = spans[j]
                    intersect = r1 & r2
                    if not intersect.is_empty:
                        min_area = min(r1.get_area(), r2.get_area())
                        if min_area > 40 and (intersect.get_area() / min_area) > 0.70:
                            if t1 != t2:
                                overlays.append(
                                    f"Overlapping text spans on page {pno + 1}: '{t1}' overlapping '{t2}'"
                                )

        # Multi-page credentials check
        multipage_issues = []
        unique_accs = set(page_acc_numbers.values())
        if len(unique_accs) > 1:
            multipage_issues.append(
                f"Contradictory account numbers detected across document pages: {page_acc_numbers}"
            )

        if multipage_issues:
            multipage_check = {
                "check": "bank_cross_page_consistency",
                "status": "warning",
                "severity": "high",
                "message": multipage_issues[0],
                "evidence": {"page_account_numbers": page_acc_numbers},
            }
        else:
            multipage_check = {
                "check": "bank_cross_page_consistency",
                "status": "pass",
                "severity": "low",
                "message": f"Multi-page account credentials and structure are consistent across {page_count} page(s).",
                "evidence": {"page_account_numbers": page_acc_numbers},
            }

        # PDF layout & font check
        pdf_issues = []
        if overlays:
            pdf_issues.extend(overlays)

        # Detect conflicting font families in table amounts (e.g. Courier or Comic Sans injected into Arial)
        if len(font_families) > 1:
            total_num_spans = sum(font_families.values())
            for fam, count in font_families.items():
                if count / total_num_spans < 0.15 and total_num_spans >= 6:
                    pdf_issues.append(
                        f"Unusual font substitution anomaly in numeric figures: font family '{fam}' used only in {count} amount(s)."
                    )

        if pdf_issues:
            pdf_layout_check = {
                "check": "pdf_text_overlay_and_font",
                "status": "warning",
                "severity": "high",
                "message": f"PDF typography / overlay anomaly detected: {pdf_issues[0]}",
                "evidence": {"issues": pdf_issues},
            }
        else:
            pdf_layout_check = {
                "check": "pdf_text_overlay_and_font",
                "status": "pass",
                "severity": "low",
                "message": "Typography and text layer alignment conform to standard rendering specifications.",
                "evidence": {"number_font_families": list(font_families.keys())},
            }

        return multipage_check, pdf_layout_check

    # -------------------------------------------------------------
    # 3. Main Analyzer Entry Point
    # -------------------------------------------------------------

    def analyze(
        self,
        file_path: Path,
        extracted_text: str,
        fields: Dict[str, Any],
        is_pdf: bool,
    ) -> List[Dict[str, Any]]:
        """
        Coordinates the complete bank statement consistency analysis pipeline.
        """
        checks: List[Dict[str, Any]] = []

        # 1. Opening Balance extraction
        opening_balance = None
        if fields.get("opening_balance"):
            opening_balance, _ = self._parse_amount(str(fields["opening_balance"]))
        if opening_balance is None:
            open_m = re.search(r"OPENING\s+BALANCE\s+([\d,]+\.\d{2})", extracted_text, re.IGNORECASE)
            if open_m:
                opening_balance, _ = self._parse_amount(open_m.group(1))

        # 2. Extract transaction rows
        transactions: List[Dict[str, Any]] = []
        doc: Optional[fitz.Document] = None

        if is_pdf:
            try:
                doc = fitz.open(str(file_path))
                transactions = self._extract_transactions_from_pdf(doc)
            except Exception as e:
                logger.warning(f"Could not extract transactions via PDF layout: {e}")

        if not transactions:
            transactions = self._extract_transactions_from_text(extracted_text)

        # 3. Running Balance and Table checks
        math_check, table_check = self.check_running_balance_and_table(transactions, opening_balance)
        checks.append(math_check)
        checks.append(table_check)

        # 4. Bank Identity Consistency
        id_check = self.check_bank_identity(extracted_text, fields)
        checks.append(id_check)

        # 5. Summary Balance Arithmetic
        summary_check = self.check_summary_balance_math(extracted_text, fields)
        checks.append(summary_check)

        # 6. Multi-page and PDF layout checks
        if doc is not None and len(doc) > 0:
            multipage_check, pdf_layout_check = self.check_multipage_and_pdf_forensics(doc)
            checks.append(multipage_check)
            checks.append(pdf_layout_check)
            doc.close()

        return checks


bank_statement_forensics_service = BankStatementForensicsService()
