import uuid
from datetime import datetime
from pathlib import Path
from fastapi import UploadFile, HTTPException, status
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models.database import DocumentRecord
from backend.models.schemas import UploadResponse
from backend.utils.file_utils import (
    sanitize_filename,
    get_file_extension,
    validate_file_extension,
    validate_magic_bytes,
)
from backend.utils.logger import logger

class UploadService:
    def __init__(self, upload_dir: Path = settings.UPLOAD_DIR):
        self.upload_dir = upload_dir
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    async def save_upload(self, file: UploadFile, db: Session) -> UploadResponse:
        original_name = file.filename or "unnamed_file"
        sanitized_name = sanitize_filename(original_name)
        ext = get_file_extension(sanitized_name)

        # 1. Validate file extension
        if not validate_file_extension(sanitized_name):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file extension '{ext}'. Allowed types: {settings.ALLOWED_EXTENSIONS}",
            )

        # 2. Read first chunk to inspect header and validate magic bytes
        header = await file.read(2048)
        if not header:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty (0 bytes).",
            )

        is_valid_header, detected_mime = validate_magic_bytes(header)
        if not is_valid_header:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File signature does not match any supported document type (PDF, JPEG, PNG).",
            )

        # 3. Read remaining content and enforce size limit
        remaining = await file.read()
        total_content = header + remaining
        file_size = len(total_content)

        if file_size > settings.max_file_size_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds maximum allowed size of {settings.MAX_FILE_SIZE_MB}MB.",
            )

        # 4. Generate safe unique ID and filename (never execute, store with unique name)
        file_id = str(uuid.uuid4())
        safe_filename = f"{file_id}{ext}"
        destination_path = self.upload_dir / safe_filename

        # 5. Persist to disk securely
        try:
            with open(destination_path, "wb") as f:
                f.write(total_content)
        except Exception as e:
            logger.error(f"Failed to write file to disk: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to store uploaded file on the server.",
            )

        # 6. Record metadata in database
        doc_record = DocumentRecord(
            id=file_id,
            filename=safe_filename,
            original_filename=sanitized_name,
            file_type=detected_mime,
            file_size=file_size,
            file_path=str(destination_path),
            status="uploaded",
            created_at=datetime.utcnow(),
        )
        db.add(doc_record)
        db.commit()
        db.refresh(doc_record)

        # 7. Determine initial page count & preview availability
        page_count = 1
        preview_available = True
        if detected_mime == "application/pdf" or ext == ".pdf":
            try:
                import fitz
                doc = fitz.open(str(destination_path))
                if doc.is_encrypted:
                    preview_available = False
                    page_count = 0
                else:
                    page_count = max(len(doc), 1)
                doc.close()
            except Exception as pdf_err:
                logger.warning(f"Could not read PDF page count on upload: {pdf_err}")
                preview_available = False
                page_count = 0

        logger.info(f"File uploaded successfully: ID={file_id}, Size={file_size}B, Type={detected_mime}, Pages={page_count}")

        return UploadResponse(
            file_id=file_id,
            filename=safe_filename,
            original_filename=sanitized_name,
            file_type=detected_mime,
            file_size=file_size,
            upload_time=doc_record.created_at.isoformat(),
            message="Document uploaded and stored successfully.",
            page_count=page_count,
            preview_available=preview_available,
        )

upload_service = UploadService()
