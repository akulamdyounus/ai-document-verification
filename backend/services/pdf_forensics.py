from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import re
import fitz  # PyMuPDF
from backend.utils.logger import logger

class PDFForensicsService:
    """
    Forensic analysis service for PDF documents:
    - Extracts PDF metadata (Creator, Producer, CreationDate, ModDate, Title, Author)
    - Checks for third-party graphics/design editing software signatures
    - Evaluates timestamp discrepancy between creation and modification dates
    - Inspects structural layer composition (embedded fonts, image streams vs text)
    """

    # Software tools frequently associated with ad-hoc editing or template modification
    EDITING_SOFTWARE_INDICATORS = [
        "photoshop",
        "canva",
        "illustrator",
        "indesign",
        "gimp",
        "ilovepdf",
        "smallpdf",
        "sejda",
        "pdf24",
        "pdfescape",
        "inkscape",
        "coreldraw",
    ]

    def _parse_pdf_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parses PDF date format D:YYYYMMDDHHmmSS..."""
        if not date_str:
            return None
        clean = re.sub(r"^D:", "", date_str)
        # Take first 14 digits (YYYYMMDDHHMMSS)
        digits = re.sub(r"[^\d]", "", clean)[:14]
        try:
            if len(digits) >= 8:
                year = int(digits[0:4])
                month = int(digits[4:6]) if len(digits) >= 6 else 1
                day = int(digits[6:8]) if len(digits) >= 8 else 1
                hour = int(digits[8:10]) if len(digits) >= 10 else 0
                minute = int(digits[10:12]) if len(digits) >= 12 else 0
                second = int(digits[12:14]) if len(digits) >= 14 else 0
                return datetime(year, month, day, hour, minute, second)
        except Exception:
            return None
        return None

    def analyze(self, pdf_path: Path) -> List[Dict[str, Any]]:
        checks: List[Dict[str, Any]] = []

        try:
            doc = fitz.open(str(pdf_path))
        except Exception as e:
            logger.error(f"Failed to open PDF for forensic inspection: {e}")
            return [{
                "check": "pdf_integrity",
                "status": "warning",
                "severity": "medium",
                "message": "PDF could not be opened or parsed for forensic inspection.",
                "evidence": {"error": str(e)},
            }]

        meta = doc.metadata or {}
        creator = (meta.get("creator") or "").strip()
        producer = (meta.get("producer") or "").strip()
        creation_date_raw = meta.get("creationDate") or ""
        mod_date_raw = meta.get("modDate") or ""
        pdf_format = meta.get("format") or f"PDF {doc.metadata.get('version', '1.4')}"

        creation_dt = self._parse_pdf_date(creation_date_raw)
        mod_dt = self._parse_pdf_date(mod_date_raw)

        # 1. Metadata & Editing Software Check
        matched_indicators = []
        combined_tools = f"{creator.lower()} {producer.lower()}"
        for tool in self.EDITING_SOFTWARE_INDICATORS:
            if tool in combined_tools:
                matched_indicators.append(tool.capitalize())

        meta_status = "pass"
        meta_severity = "low"
        meta_msg = "PDF metadata structure and producing software appear standard."

        if matched_indicators:
            meta_status = "info"
            meta_severity = "low"
            meta_msg = (
                f"Common PDF conversion/editing tool signature identified ({', '.join(matched_indicators)}). "
                "This is a contextual indicator and does not by itself indicate tampering."
            )
        elif not creator and not producer:
            meta_status = "info"
            meta_severity = "low"
            meta_msg = "PDF producer and creator metadata are stripped or empty."

        checks.append({
            "check": "pdf_metadata",
            "status": meta_status,
            "severity": meta_severity,
            "message": meta_msg,
            "evidence": {
                "producer": producer or "None",
                "creator": creator or "None",
                "creation_date": creation_dt.isoformat() if creation_dt else creation_date_raw,
                "modification_date": mod_dt.isoformat() if mod_dt else mod_date_raw,
                "detected_editing_tools": matched_indicators,
                "format": pdf_format,
            },
        })

        # 2. Timestamp Discrepancy Check
        time_status = "pass"
        time_severity = "low"
        time_msg = "Creation and modification timestamps are consistent."

        if creation_dt and mod_dt:
            delta_days = (mod_dt - creation_dt).total_seconds() / 86400.0
            if delta_days > 30.0:
                time_status = "warning"
                time_severity = "low"
                time_msg = f"Document was modified {int(delta_days)} days after original creation."
            elif delta_days < -1.0:
                time_status = "warning"
                time_severity = "medium"
                time_msg = "Anomalous timestamps: Modification date precedes creation date."

        checks.append({
            "check": "pdf_timestamps",
            "status": time_status,
            "severity": time_severity,
            "message": time_msg,
            "evidence": {
                "creation_date_parsed": bool(creation_dt),
                "modification_date_parsed": bool(mod_dt),
            },
        })

        # 3. Structural Layer & Font Analysis
        total_pages = len(doc)
        total_images = 0
        embedded_fonts = set()
        has_text_layer = False

        pages_to_scan = min(total_pages, 5)  # Scan up to 5 pages for performance
        for p in range(pages_to_scan):
            page = doc.load_page(p)
            imgs = page.get_images()
            total_images += len(imgs)
            fonts = page.get_fonts()
            for f in fonts:
                if len(f) > 3:
                    embedded_fonts.add(f[3])
            if page.get_text().strip():
                has_text_layer = True

        doc.close()

        struct_status = "pass"
        struct_severity = "low"
        struct_msg = "PDF structure contains valid embedded fonts and standard text stream."

        if total_images > 0 and not has_text_layer:
            struct_status = "info"
            struct_severity = "low"
            struct_msg = "PDF is a scanned image raster without an embedded digital text layer."

        checks.append({
            "check": "pdf_structure",
            "status": struct_status,
            "severity": struct_severity,
            "message": struct_msg,
            "evidence": {
                "pages": total_pages,
                "images_found": total_images,
                "embedded_fonts_count": len(embedded_fonts),
                "has_digital_text": has_text_layer,
            },
        })

        return checks

pdf_forensics_service = PDFForensicsService()
