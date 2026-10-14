import json
import uuid
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status, Query, Response
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models.schemas import HealthResponse, UploadResponse, AnalysisResponse, DocumentMetadataResponse
from backend.models.database import DocumentRecord, AnalysisRecord
from backend.api.deps import get_db
from backend.services.upload_service import upload_service
from backend.services.pdf_service import pdf_service
from backend.services.ocr_service import ocr_service
from backend.services.document_classifier import document_classifier
from backend.services.text_normalizer import text_normalizer
from backend.services.field_extractor import field_extractor
from backend.services.fraud_detector import fraud_detector
from backend.services.verification_engine import verification_engine
from backend.services.preview_service import preview_service
from backend.utils.logger import logger

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health_check():
    """Return backend status and OCR engine health."""
    ocr_ready = ocr_service.is_available()
    return HealthResponse(
        status="healthy",
        version=settings.VERSION,
        project_name=settings.PROJECT_NAME,
        ocr_available=ocr_ready,
        tesseract_path=str(ocr_service._cmd_path) if ocr_service._cmd_path else None,
        environment=settings.ENVIRONMENT,
    )


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Upload a document (PDF, JPG, JPEG, PNG).
    Validates extension, size, and magic bytes, generates safe UUID, and stores to disk.
    """
    return await upload_service.save_upload(file, db)


@router.get("/documents/{file_id}/metadata", response_model=DocumentMetadataResponse)
def get_document_metadata(
    file_id: str,
    db: Session = Depends(get_db),
):
    """
    Returns document file type, page count, and preview availability.
    Does not expose physical server directory paths.
    """
    return preview_service.get_metadata(file_id, db)


@router.get("/documents/{file_id}/preview")
def get_document_preview(
    file_id: str,
    page: int = Query(1, ge=1, description="1-indexed page number for multi-page PDFs"),
    thumbnail: bool = Query(False, description="Whether to render a lower-resolution thumbnail"),
    db: Session = Depends(get_db),
):
    """
    Renders and serves an in-memory visual preview of the requested document page.
    PDF pages are rendered via PyMuPDF; images are scaled within safe preview bounds.
    """
    image_bytes, media_type = preview_service.render_preview(
        file_id=file_id,
        page=page,
        thumbnail=thumbnail,
        db=db,
    )
    return Response(
        content=image_bytes,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.post("/analyze/{file_id}", response_model=AnalysisResponse)
async def analyze_document(
    file_id: str,
    db: Session = Depends(get_db),
):
    """
    Process an uploaded document:
    1. Extract text (PyMuPDF for text PDFs, Tesseract OCR for scans and images)
    2. Classify document type using baseline rule engine
    3. Extract structural fields
    4. Run fraud detector interface (Not available in MVP)
    5. Aggregate findings and return verification status ('Unable to Verify')
    """
    # 1. Fetch document record from DB
    doc_record = db.query(DocumentRecord).filter(DocumentRecord.id == file_id).first()
    if not doc_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with file_id '{file_id}' not found.",
        )

    file_path = Path(doc_record.file_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stored document file could not be found on server disk.",
        )

    # 2. Extract text & classify source type
    extracted_text = ""
    ocr_diag = {}
    doc_source_type, raw_digital_text = pdf_service.determine_document_source_type(file_path)

    try:
        if doc_source_type == "text-based PDF":
            # Coherent digital text layer exists
            extracted_text = raw_digital_text
            ocr_diag = {
                "source": "digital_text_layer",
                "character_count": len(extracted_text),
                "preprocessing_method": "none_digital_stream",
                "psm_used": 0,
            }
        elif doc_source_type in ["scanned PDF", "rendered PDF page"]:
            # PDF is either scanned images or has scrambled/disordered digital text stream
            if ocr_service.is_available():
                logger.info(f"PDF {file_id} classified as '{doc_source_type}'. Rendering pages at 300 DPI for OCR...")
                images = pdf_service.convert_pdf_to_images(file_path, max_pages=3, dpi=300)
                ocr_text, ocr_diag = ocr_service.extract_text_from_images_with_diagnostics(images)

                # Prefer structured visual OCR text if it captured content cleanly
                if doc_source_type == "rendered PDF page" and raw_digital_text:
                    if len(ocr_text.strip()) >= 50:
                        extracted_text = ocr_text
                    else:
                        extracted_text = raw_digital_text
                else:
                    extracted_text = ocr_text
            else:
                logger.warning(f"OCR not available for PDF {file_id}. Falling back to digital text.")
                extracted_text = raw_digital_text
                ocr_diag = {"source": "digital_text_layer_fallback", "character_count": len(extracted_text)}
        else:
            # Direct Image file (JPG, PNG)
            doc_source_type = "image"
            if ocr_service.is_available():
                extracted_text, ocr_diag = ocr_service.extract_text_with_diagnostics(file_path)
            else:
                logger.warning(f"OCR not available for image {file_id}.")
                extracted_text = ""
                ocr_diag = {"source": "ocr_unavailable"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Text extraction failed for {file_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to extract text from document: {str(e)}",
        )

    raw_text = extracted_text

    # 3. Document classification (maintains exact unchanged text input)
    classification = document_classifier.classify(raw_text)
    doc_type = classification.document_type
    confidence = classification.confidence

    # 4. Clean post-OCR normalization
    normalized_text = text_normalizer.normalize_ocr_text(raw_text)

    # 5. Field extraction (uses normalized text with raw text fallback)
    fields = field_extractor.extract_fields(normalized_text, doc_type, raw_text=raw_text)

    # 6. Fraud detection & Forensic analysis pipeline
    fraud_result = fraud_detector.analyze(
        file_path=file_path,
        extracted_text=raw_text,
        document_type=doc_type,
        fields=fields,
    )

    # 7. Verification engine evaluation (decoupled classification, authenticity, manipulation, authoritative)
    ver_res = verification_engine.evaluate(
        document_type=doc_type,
        confidence=confidence,
        fields=fields,
        fraud_analysis=fraud_result,
        extracted_text_len=len(raw_text),
        matched_signals=classification.matched_signals,
        classification_status=classification.classification_status,
        alternative_types=classification.alternative_types,
        extracted_text=raw_text,
        file_path=file_path,
    )
    verification_status = ver_res.verdict
    findings = ver_res.findings
    decision_reasons = ver_res.decision_reasons

    # 8. Persist analysis results in DB
    analysis_record = AnalysisRecord(
        id=str(uuid.uuid4()),
        document_id=file_id,
        document_type=doc_type,
        classification_confidence=confidence,
        verification_status=verification_status,
        extracted_text=raw_text,
        fields_json=json.dumps(fields),
        findings_json=json.dumps(findings),
        created_at=datetime.utcnow(),
    )
    db.add(analysis_record)
    doc_record.status = "analyzed"
    db.commit()

    return AnalysisResponse(
        file_id=file_id,
        document_type=doc_type,
        classification_confidence=confidence,
        document_classification_confidence=confidence,
        classification_method=classification.method,
        classification_status=classification.classification_status,
        matched_signals=classification.matched_signals,
        alternative_types=classification.alternative_types,
        verification_status=verification_status,
        authenticity_evidence_score=ver_res.authenticity_evidence_score,
        manipulation_evidence_score=ver_res.manipulation_evidence_score,
        authoritative_verification_status=ver_res.authoritative_verification_status,
        authenticity_findings=ver_res.authenticity_findings,
        manipulation_findings=ver_res.manipulation_findings,
        risk_score=ver_res.manipulation_evidence_score,
        risk_level=fraud_result.get("risk_level"),
        forensic_report=fraud_result,
        extracted_text=raw_text,
        raw_text=raw_text,
        normalized_text=normalized_text,
        fields=fields,
        findings=findings,
        decision_reasons=decision_reasons,
        ocr_diagnostics=ocr_diag,
        document_source_type=doc_source_type,
    )
