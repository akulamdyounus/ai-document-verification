import re
from typing import Dict, Any, List, Optional

class TextNormalizer:
    """
    Normalizes OCR and digital text for reliable feature matching
    and post-OCR structured field extraction.
    """

    @staticmethod
    def normalize(text: str) -> str:
        """
        Legacy lowercase normalization used for keyword signature matching.
        Preserved for classifier backward-compatibility.
        """
        if not text:
            return ""

        # 1. Convert to lowercase
        normalized = text.lower()

        # 2. Repair hyphenated line breaks (e.g. 'state-\nment' -> 'statement')
        normalized = re.sub(r"(\w+)-\s*\n\s*(\w+)", r"\1\2", normalized)

        # 3. Replace non-standard whitespace / multiple linebreaks with single spaces or standard newlines
        normalized = re.sub(r"[\r\t\f\v]+", " ", normalized)
        normalized = re.sub(r" +", " ", normalized)

        # 4. Normalize common spaced-out OCR tokens (e.g. 'p a n' -> 'pan', 'd o b' -> 'dob')
        normalized = re.sub(r"\b([a-z])\s+([a-z])\s+([a-z])\b", r"\1\2\3", normalized)
        normalized = re.sub(r"\b([a-z])\s+([a-z])\s+([a-z])\s+([a-z])\b", r"\1\2\3\4", normalized)

        # 5. Fix common OCR character confusions in keyword contexts
        normalized = re.sub(r"\bacc0unt\b", "account", normalized)
        normalized = re.sub(r"\b5tatement\b", "statement", normalized)
        normalized = re.sub(r"\btransacti0n\b", "transaction", normalized)
        normalized = re.sub(r"\binv0ice\b", "invoice", normalized)
        normalized = re.sub(r"\bp0ssport\b", "passport", normalized)

        # 6. Normalize punctuation around colons/labels
        normalized = re.sub(r"\s*:\s*", ": ", normalized)

        return normalized.strip()

    @staticmethod
    def normalize_ocr_text(text: str) -> str:
        """
        Cleans raw Tesseract OCR output:
        - Removes isolated noise tokens (e.g. o, aN, Ox), ), @, e, 5, Q)
        - Preserves alphanumeric identifiers, dates, names, addresses
        - Normalizes whitespace and line breaks
        - Preserves label-value relationships even across line breaks
        """
        if not text:
            return ""

        lines = text.splitlines()
        cleaned_lines: List[str] = []

        LABEL_KEYS = [
            "name", "holder", "signature", "date of birth", "dob", "blood group", "bg",
            "issue date", "date of issue", "valid till", "validity", "expiry date", "valid upto",
            "address", "permanent address", "present address", "licence no", "license no", "dl no",
            "issued by", "licencing authority", "organ donor", "son/daughter/wife of", "s/w/d", "s/o",
            "emergency contact", "account number", "opening balance", "closing balance", "ifsc",
            "passport no", "given name", "aadhaar", "pan", "invoice no", "branch", "statement"
        ]

        def line_has_label(l_str: str) -> bool:
            lower = l_str.lower()
            return any(re.search(r"\b" + re.escape(lbl) + r"\b", lower) for lbl in LABEL_KEYS)

        for line in lines:
            l = line.strip()
            if not l:
                continue

            # 1. Clean unicode noise artifacts (replacement char, copyright, degree, em/en-dashes)
            l = re.sub(r"[\ufffd\u00a9\u00ae\u00b0\u2014\u2013]", "", l).strip()

            # 2. Remove trailing margin noise after 3+ spaces (e.g. '   @', '   e', '   5', '   Q', '   2', '   aw')
            l = re.sub(r"\s{3,}[^a-zA-Z0-9\s]?([a-zA-Z0-9]{1,2}|[@|)(><=~_])\s*$", "", l).strip()

            # 3. Remove leading margin noise before 3+ spaces (e.g. 'o   ', 'aN   ', 'Ox)   ')
            l = re.sub(r"^[a-zA-Z0-9]{1,2}[^a-zA-Z0-9\s]?\s{3,}", "", l).strip()

            # 4. Remove isolated trailing noise punctuation like ' @', ' |', ' )'
            l = re.sub(r"\s+[@|)]\s*$", "", l).strip()

            # 5. Discard lines with no alphanumeric characters
            if not re.search(r"[a-zA-Z0-9]", l):
                continue

            # 6. Check if entire line is an isolated noise token (1-2 characters)
            alnum_only = re.sub(r"[^a-zA-Z0-9]", "", l)
            if len(alnum_only) <= 2:
                # Keep only recognized acronyms/labels/short codes
                if alnum_only.upper() not in {"DL", "NO", "NT", "TR", "DOB", "S/O", "D/O", "W/O", "A+", "B+", "O+", "AB", "MC", "IN"}:
                    continue

            # 7. Discard lines with repeated character junk (e.g. 'a ee ee ee eee ee')
            if re.match(r"^(?:[a-zA-Z]{1,3}\s+){3,}[a-zA-Z]{1,3}$", l):
                tokens = set(l.lower().split())
                if len(tokens) <= 3 and not line_has_label(l):
                    continue

            # 8. Check if line is meaningless short junk (< 4 letters, no numbers, no labels)
            words = re.findall(r"[a-zA-Z]{2,}", l)
            has_lbl = line_has_label(l)
            has_id = bool(re.search(r"[A-Z]{2}\d{12,15}|\b\d{10,16}\b|\b\d{6}\b|\d+/\d+", l))
            has_dt = bool(re.search(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", l))
            has_amount = bool(re.search(r"[\d,]+\.\d{2}", l))

            if not (has_lbl or has_id or has_dt or has_amount):
                total_letters = sum(len(w) for w in words)
                if total_letters < 6 and len(words) <= 1:
                    continue
                if len(words) > 0 and all(len(w) <= 3 for w in words):
                    continue

            # 9. Clean trailing operator noise like ' | > = F a' or ' iy ae deal ='
            l = re.sub(r"\s{4,}[|>=~<].*$", "", l).strip()
            l = re.sub(r"\s{4,}(?:iy|ae|deal|Re|oe|aim)\b.*$", "", l, flags=re.IGNORECASE).strip()

            # 10. Clean internal spacing around colons
            l = re.sub(r"\s*:\s*", ": ", l)
            l = re.sub(r"\s+", " ", l).strip()

            cleaned_lines.append(l)

        # Label-value consolidation pass
        merged_lines: List[str] = []
        idx = 0
        while idx < len(cleaned_lines):
            curr = cleaned_lines[idx]

            # Check if line is just a label: e.g. 'Name:', 'Name', 'Date of Birth:', 'DOB'
            m_label = re.match(
                r"^(Name|Holder'?s\s*Name|Date\s*of\s*Birth|DOB|Licence\s*No|License\s*No|DL\s*No|Issue\s*Date|Expiry\s*Date)[:\s]*$",
                curr,
                re.IGNORECASE,
            )
            if m_label and idx + 1 < len(cleaned_lines):
                nxt = cleaned_lines[idx + 1]
                if not line_has_label(nxt):
                    lbl_name = m_label.group(1).strip()
                    merged_lines.append(f"{lbl_name} = {nxt}")
                    idx += 2
                    continue

            # Check for Address: on separate line followed by address lines
            m_addr = re.match(r"^(Address|Permanent\s*Address|Present\s*Address)[:\s]*$", curr, re.IGNORECASE)
            if m_addr and idx + 1 < len(cleaned_lines):
                lbl_name = m_addr.group(1).strip()
                addr_parts = []
                lookahead = idx + 1
                while lookahead < len(cleaned_lines):
                    candidate = cleaned_lines[lookahead]
                    if line_has_label(candidate) or re.search(r"DL No|Driving Licence|Issued by|Emergency", candidate, re.IGNORECASE):
                        break
                    addr_parts.append(candidate)
                    lookahead += 1
                if addr_parts:
                    merged_lines.append(f"{lbl_name}: " + " ".join(addr_parts))
                    idx = lookahead
                    continue

            merged_lines.append(curr)
            idx += 1

        return "\n".join(merged_lines)

text_normalizer = TextNormalizer()

