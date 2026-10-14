import re
import io
from pathlib import Path
from typing import List, Tuple, Optional
from PIL import Image
import fitz  # PyMuPDF
from fastapi import HTTPException, status
from backend.utils.logger import logger


class PDFService:
    @staticmethod
    def is_pdf(file_path: Path) -> bool:
        return file_path.suffix.lower() == ".pdf"

    def extract_text(self, pdf_path: Path) -> Tuple[str, int]:
        """
        Extracts digital text layer from a PDF file.
        Returns a tuple of (extracted_text, page_count).
        Raises HTTPException if PDF is corrupted or encrypted.
        """
        try:
            doc = fitz.open(str(pdf_path))
        except Exception as e:
            logger.error(f"Failed to open PDF {pdf_path.name}: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unable to open document: the PDF file appears corrupted or invalid.",
            )

        if doc.is_encrypted:
            doc.close()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password-protected / encrypted PDFs are not supported.",
            )

        page_texts = []
        page_count = len(doc)
        for page_num in range(page_count):
            page = doc.load_page(page_num)
            text = page.get_text("text")
            if text and text.strip():
                page_texts.append(text.strip())

        doc.close()
        full_text = "\n\n".join(page_texts).strip()
        return full_text, page_count

    def convert_pdf_to_images(
        self, pdf_path: Path, max_pages: int = 5, dpi: int = 300
    ) -> List[Image.Image]:
        """
        Renders PDF pages as PIL Images for OCR processing at high resolution (default 300 DPI).
        Limits to max_pages to preserve performance.
        """
        images = []
        try:
            doc = fitz.open(str(pdf_path))
            pages_to_process = min(len(doc), max_pages)
            for i in range(pages_to_process):
                page = doc.load_page(i)
                # 300 DPI rendering ensures fine document text, small fonts, and digits are sharply resolved
                pix = page.get_pixmap(dpi=dpi)
                img_data = pix.tobytes("png")
                image = Image.open(io.BytesIO(img_data)).convert("RGB")
                images.append(image)
            doc.close()
        except Exception as e:
            logger.error(f"Error rendering PDF pages to images: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to render PDF pages for OCR scanning.",
            )
        return images

    def determine_document_source_type(self, file_path: Path) -> Tuple[str, str]:
        """
        Classifies the document into one of 4 source types:
        - "text-based PDF": Digital text layer exists with coherent reading structure
        - "scanned PDF": PDF with minimal or no digital text (scanned image inside PDF)
        - "rendered PDF page": PDF where digital text stream is fragmented, scrambled,
                               or contains repeated lone colons without values
        - "image": Direct image file (JPEG, PNG)
        Returns: (source_type, digital_text)
        """
        if not self.is_pdf(file_path):
            return "image", ""

        try:
            digital_text, _ = self.extract_text(file_path)
        except Exception:
            return "scanned PDF", ""

        cleaned = digital_text.strip()
        if len(cleaned) < 50:
            return "scanned PDF", digital_text

        # Analyze structure for scrambled / disordered stream
        # E.g. Form-based PDFs with isolated colon lines (': \n : \n :') or high line fragmentation
        lone_colons = len(re.findall(r"^\s*[:;]\s*$", digital_text, re.MULTILINE))
        lines = [l.strip() for l in digital_text.splitlines() if l.strip()]
        short_lines = [l for l in lines if len(l) <= 2]
        fragmentation_ratio = len(short_lines) / max(len(lines), 1)

        if lone_colons >= 2 or fragmentation_ratio >= 0.25:
            return "rendered PDF page", digital_text

        return "text-based PDF", digital_text


pdf_service = PDFService()
