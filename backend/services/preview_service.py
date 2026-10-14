import io
from pathlib import Path
from typing import Tuple, Dict, Any, Optional
from PIL import Image
import fitz  # PyMuPDF
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.models.database import DocumentRecord
from backend.utils.logger import logger


class PreviewService:
    """
    Secure in-memory document preview generation service.
    Renders PDF pages and image uploads directly to memory buffers.
    Never exposes physical upload paths and never writes preview caches to public directories.
    """

    MAX_PREVIEW_DIMENSION = 1800
    THUMBNAIL_DIMENSION = 200

    def _get_document(self, file_id: str, db: Session) -> Tuple[DocumentRecord, Path]:
        """Validates file_id and returns the DocumentRecord and resolved Path."""
        record = db.query(DocumentRecord).filter(DocumentRecord.id == file_id).first()
        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document with ID '{file_id}' not found.",
            )

        file_path = Path(record.file_path)
        if not file_path.exists():
            logger.error(f"Document file missing from disk: {file_path}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Uploaded document file could not be found on server storage.",
            )

        return record, file_path

    def get_metadata(self, file_id: str, db: Session) -> Dict[str, Any]:
        """
        Determines file type, page count, and preview availability.
        Handles corrupted or password-protected files gracefully without raising unhandled 500 errors.
        """
        record, file_path = self._get_document(file_id, db)
        is_pdf = file_path.suffix.lower() == ".pdf"
        file_type = "pdf" if is_pdf else "image"
        page_count = 1
        preview_available = True
        error_msg = None

        if is_pdf:
            try:
                doc = fitz.open(str(file_path))
                if doc.is_encrypted:
                    preview_available = False
                    error_msg = "Encrypted / password-protected PDF"
                    page_count = 0
                else:
                    page_count = max(len(doc), 1)
                doc.close()
            except Exception as e:
                logger.warning(f"Could not read PDF structure for preview metadata {file_id}: {e}")
                preview_available = False
                error_msg = "Corrupted or unreadable PDF structure"
                page_count = 0
        else:
            try:
                with Image.open(str(file_path)) as img:
                    img.verify()
                page_count = 1
                preview_available = True
            except Exception as e:
                logger.warning(f"Could not verify image file {file_id}: {e}")
                preview_available = False
                error_msg = "Invalid or corrupted image format"

        return {
            "file_id": file_id,
            "file_type": file_type,
            "mime_type": record.file_type,
            "original_filename": record.original_filename,
            "file_size": record.file_size,
            "page_count": page_count,
            "preview_available": preview_available,
            "error_detail": error_msg,
        }

    def render_preview(
        self, file_id: str, page: int = 1, thumbnail: bool = False, db: Session = None
    ) -> Tuple[bytes, str]:
        """
        Renders a specific page (for PDF) or optimized preview (for images) in-memory.
        Returns (image_bytes, mime_type).
        """
        record, file_path = self._get_document(file_id, db)
        is_pdf = file_path.suffix.lower() == ".pdf"

        if is_pdf:
            return self._render_pdf_page(file_path, page, thumbnail)
        else:
            return self._render_image(file_path, thumbnail)

    def _render_pdf_page(self, pdf_path: Path, page_number: int, thumbnail: bool) -> Tuple[bytes, str]:
        """Renders 1-indexed page of PDF using PyMuPDF to PNG bytes."""
        try:
            doc = fitz.open(str(pdf_path))
        except Exception as e:
            logger.error(f"Failed to open PDF for rendering: {e}")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Unable to render preview: PDF file appears corrupted or invalid.",
            )

        if doc.is_encrypted:
            doc.close()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot preview encrypted or password-protected PDF document.",
            )

        total_pages = len(doc)
        if total_pages == 0:
            doc.close()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="PDF document contains zero pages.",
            )

        if page_number < 1 or page_number > total_pages:
            doc.close()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid page number {page_number}. Document contains {total_pages} page(s).",
            )

        try:
            page = doc.load_page(page_number - 1)
            rect = page.rect

            if thumbnail:
                scale = min(self.THUMBNAIL_DIMENSION / max(rect.width, 1.0), 1.0)
            else:
                # 150 DPI render scale (1.5x - 2.0x) capped to max dimension
                max_dim = max(rect.width, rect.height, 1.0)
                scale = min(self.MAX_PREVIEW_DIMENSION / max_dim, 2.0)
                scale = max(scale, 0.5)

            matrix = fitz.Matrix(scale, scale)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            png_bytes = pix.tobytes("png")
            doc.close()
            return png_bytes, "image/png"
        except Exception as e:
            doc.close()
            logger.error(f"Error rendering PDF page {page_number}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to render preview for page {page_number}: {str(e)}",
            )

    def _render_image(self, image_path: Path, thumbnail: bool) -> Tuple[bytes, str]:
        """Loads image, enforces safe resolution bounds, and returns memory bytes."""
        try:
            with Image.open(str(image_path)) as img:
                img_format = img.format or "JPEG"
                out_mime = "image/png" if img_format == "PNG" else "image/jpeg"
                save_format = "PNG" if img_format == "PNG" else "JPEG"

                # Convert mode for clean web rendering
                if img.mode in ("RGBA", "LA") and save_format == "JPEG":
                    rgb_img = Image.new("RGB", img.size, (255, 255, 255))
                    rgb_img.paste(img, mask=img.split()[-1])
                    img = rgb_img
                elif img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGB")

                w, h = img.size
                target_max = self.THUMBNAIL_DIMENSION if thumbnail else self.MAX_PREVIEW_DIMENSION

                if max(w, h) > target_max:
                    scale = target_max / float(max(w, h))
                    new_size = (int(w * scale), int(h * scale))
                    img = img.resize(new_size, Image.Resampling.BILINEAR)

                buf = io.BytesIO()
                if save_format == "JPEG":
                    img.save(buf, format="JPEG", quality=85, optimize=True)
                else:
                    img.save(buf, format="PNG", optimize=True)

                return buf.getvalue(), out_mime
        except Exception as e:
            logger.error(f"Error preparing image preview: {e}")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Unable to generate image preview: corrupted or unsupported image content.",
            )


preview_service = PreviewService()
