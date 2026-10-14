from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime

class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str
    project_name: str
    ocr_available: bool
    tesseract_path: Optional[str] = None
    environment: str

class UploadResponse(BaseModel):
    file_id: str
    filename: str
    original_filename: str
    file_type: str
    file_size: int
    upload_time: str
    message: str = "File uploaded successfully"
    page_count: Optional[int] = 1
    preview_available: bool = True

class DocumentMetadataResponse(BaseModel):
    file_id: str
    file_type: str
    mime_type: str
    original_filename: str
    file_size: int
    page_count: int
    preview_available: bool
    error_detail: Optional[str] = None

class ForensicCheck(BaseModel):
    check: str
    status: str  # "pass", "warning", "info"
    severity: str  # "low", "medium", "high"
    message: str
    evidence: Dict[str, Any] = Field(default_factory=dict)

class ForensicReport(BaseModel):
    overall_status: str
    risk_score: float = Field(..., ge=0.0, le=1.0)
    risk_level: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    checks: List[ForensicCheck] = Field(default_factory=list)
    findings: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    ml_risk_score: Optional[float] = None
    detection_method: Optional[str] = "rule_based"

class AnalysisResponse(BaseModel):
    file_id: str
    document_type: str
    classification_confidence: float = Field(..., ge=0.0, le=1.0)
    document_classification_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    classification_method: str = "rule_based"
    classification_status: str = "classified"  # "classified" or "insufficient_evidence"
    matched_signals: List[str] = Field(default_factory=list)
    alternative_types: List[Dict[str, Any]] = Field(default_factory=list)
    verification_status: str
    authenticity_evidence_score: float = Field(0.0, ge=0.0, le=1.0)
    manipulation_evidence_score: float = Field(0.0, ge=0.0, le=1.0)
    authoritative_verification_status: str = "NOT_AVAILABLE"
    authenticity_findings: List[str] = Field(default_factory=list)
    manipulation_findings: List[str] = Field(default_factory=list)
    risk_score: Optional[float] = None
    risk_level: Optional[str] = None
    forensic_report: Optional[ForensicReport] = None
    extracted_text: str
    raw_text: Optional[str] = None
    normalized_text: Optional[str] = None
    fields: Dict[str, Any] = Field(default_factory=dict)
    findings: List[str] = Field(default_factory=list)
    decision_reasons: List[str] = Field(default_factory=list)
    ocr_diagnostics: Optional[Dict[str, Any]] = None
    document_source_type: Optional[str] = None

class ErrorResponse(BaseModel):
    detail: str
    error_code: Optional[str] = None
