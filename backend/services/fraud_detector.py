from pathlib import Path
from typing import Dict, Any, List, Optional
import os
import joblib
from PIL import Image

from backend.services.pdf_service import pdf_service
from backend.services.image_forensics import image_forensics_service
from backend.services.copy_move_detector import copy_move_detector
from backend.services.pdf_forensics import pdf_forensics_service
from backend.services.content_consistency import content_consistency_service
from backend.services.forensic_feature_extractor import forensic_feature_extractor
from backend.config import MODELS_DIR, PROJECT_ROOT
from backend.utils.logger import logger


class BaseFraudDetector:
    def analyze(
        self,
        file_path: Path,
        extracted_text: str,
        document_type: str,
        fields: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        raise NotImplementedError


class UnifiedForensicDetector(BaseFraudDetector):
    """
    Phase 2B Multi-Dimensional Forensic & Tampering Detector.
    Coordinates:
    - Image Forensics (ELA, noise variance, sharpness, splicing)
    - Copy-Move Cloned Region Detection
    - PDF Structural & Metadata Forensics
    - Content & Chronological Consistency
    - Calibrated Machine Learning Tampering Risk Estimation
    - Mathematical Evidence Aggregation into Risk Score
    """

    LIMITATIONS = [
        "Automated forensic analysis cannot establish legal authenticity without authoritative verification.",
        "Compression and ELA anomalies may occur naturally through camera processing, messaging app forwarding, or multi-generation resaving.",
        "Absence of detected anomalies is not definitive proof of authentic origin.",
    ]

    def __init__(self, model_path: Optional[str] = None):
        if model_path:
            self.model_path = str(model_path)
        else:
            primary_path = MODELS_DIR / "tamper_risk_classifier_v1.joblib"
            fallback_path = PROJECT_ROOT / "models" / "tamper_risk_classifier_v1.joblib"
            if primary_path.exists():
                self.model_path = str(primary_path)
            elif fallback_path.exists():
                self.model_path = str(fallback_path)
            else:
                self.model_path = str(primary_path)
        self.ml_model = None
        self._load_ml_model()

    def _load_ml_model(self):
        try:
            if os.path.exists(self.model_path):
                self.ml_model = joblib.load(self.model_path)
                logger.info(f"Loaded ML tampering risk classifier from {self.model_path}")
            else:
                logger.info(f"ML tampering risk classifier not found at {self.model_path}, using rule-based fallback")
        except Exception as e:
            logger.warning(f"Failed to load ML tampering risk classifier from {self.model_path}: {e}")
            self.ml_model = None

    def is_ml_available(self) -> bool:
        return self.ml_model is not None

    def analyze(
        self,
        file_path: Path,
        extracted_text: str,
        document_type: str,
        fields: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        checks: List[Dict[str, Any]] = []
        is_pdf = pdf_service.is_pdf(file_path)
        fields = fields or {}

        # 1. PDF Forensics (if document is a PDF)
        if is_pdf:
            pdf_checks = pdf_forensics_service.analyze(file_path)
            checks.extend(pdf_checks)

        # 2. Extract image representation for visual forensics
        primary_image: Optional[Image.Image] = None
        try:
            if is_pdf:
                # Render first page as image for ELA and copy-move checks
                rendered_pages = pdf_service.convert_pdf_to_images(file_path, max_pages=1)
                if rendered_pages:
                    primary_image = rendered_pages[0]
            else:
                primary_image = Image.open(str(file_path)).convert("RGB")
        except Exception as img_err:
            logger.warning(f"Could not load image for visual forensics on {file_path.name}: {img_err}")

        # 3. Image Forensics (ELA, Noise, Metadata, Blur, Splicing)
        if primary_image:
            image_checks = image_forensics_service.analyze(
                primary_image, include_extended=True, file_path=file_path
            )
            checks.extend(image_checks)

            # 4. Copy-Move Detection
            cm_check = copy_move_detector.detect(primary_image)
            checks.append(cm_check)

        # 5. Content Consistency & Chronology Validation
        consistency_checks = content_consistency_service.validate(fields, document_type)
        checks.extend(consistency_checks)

        # 6. Bank-Statement-Specific Forensic Verification (Arithmetic, Table, Identity, PDF Layout)
        if document_type == "Bank Statement":
            try:
                from backend.services.bank_statement_forensics import bank_statement_forensics_service
                bs_checks = bank_statement_forensics_service.analyze(
                    file_path=file_path,
                    extracted_text=extracted_text,
                    fields=fields,
                    is_pdf=is_pdf,
                )
                checks.extend(bs_checks)
            except Exception as bs_err:
                logger.error(f"Bank statement forensics execution failed for {file_path.name}: {bs_err}")

        # 6. Mathematical Evidence Aggregation & Risk Calculation
        risk_score, confidence, findings, ml_risk_score, detection_method = self._aggregate_evidence(checks)

        # Map risk score to risk level following conservative policy thresholds
        if risk_score >= 0.75:
            risk_level = "Very High"
            overall_status = "Suspicious"
        elif risk_score >= 0.50:
            risk_level = "High"
            overall_status = "Suspicious"
        elif risk_score > 0.20:
            risk_level = "Medium"
            overall_status = "Review Needed"
        else:
            risk_level = "Low"
            overall_status = "Clean"

        return {
            "overall_status": overall_status,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "confidence": confidence,
            "checks": checks,
            "findings": findings,
            "limitations": self.LIMITATIONS,
            "ml_risk_score": ml_risk_score,
            "detection_method": detection_method,
        }

    def _aggregate_evidence(self, checks: List[Dict[str, Any]]) -> tuple:
        """
        Derives an objective, evidence-based risk score (0.0 to 1.0).
        Strictly avoids fabricated or arbitrary numbers.
        Combines rule-based forensic severity weighting with Calibrated ML
        tampering risk probability when the trained model is active.
        """
        severity_weights = {
            "critical": 0.50,
            "high": 0.35,
            "medium": 0.18,
            "low": 0.08,
        }

        total_risk = 0.0
        findings: List[str] = []
        valid_checks_count = len(checks)

        for c in checks:
            status = c.get("status", "pass")
            severity = c.get("severity", "low")
            msg = c.get("message", "")

            if status == "warning":
                weight = severity_weights.get(severity, 0.10)
                total_risk += weight
                findings.append(f"[{severity.upper()}] {msg}")
            elif status == "info":
                # Informational checks do not contribute to risk
                pass

        # Rule-based bounded risk score
        rule_risk = round(min(total_risk, 0.95), 2)

        ml_risk_score: Optional[float] = None
        detection_method = "rule_based"

        # Apply ML tampering risk scoring if model is loaded
        if self.is_ml_available():
            try:
                feat_vec = forensic_feature_extractor.extract_vector(checks)
                # CalibratedClassifierCV predict_proba returns posterior probability [P(clean), P(tampered)]
                prob_tampered = float(self.ml_model.predict_proba([feat_vec])[0][1])
                ml_risk_score = round(prob_tampered, 2)
                detection_method = "hybrid_ml"

                # Blended risk calculation: 60% ML calibrated risk + 40% rule-based severity
                blended_risk = round(0.60 * ml_risk_score + 0.40 * rule_risk, 2)

                # Safeguards:
                # 1. If rule-based forensic analysis flagged critical/high risk (>= 0.75),
                #    ensure combined risk never drops below 0.75.
                # 2. If rule-based detected severe tampering (>= 0.50), maintain at least 85% of rule risk.
                if rule_risk >= 0.75:
                    risk_score = max(blended_risk, rule_risk)
                elif rule_risk >= 0.50:
                    risk_score = max(blended_risk, round(rule_risk * 0.85, 2))
                else:
                    risk_score = blended_risk

                if ml_risk_score >= 0.60:
                    findings.append(f"[ML FORENSICS] Machine learning tampering risk probability: {int(ml_risk_score * 100)}%.")
            except Exception as ml_err:
                logger.warning(f"ML tampering risk inference error, falling back to rule-based: {ml_err}")
                risk_score = rule_risk
                detection_method = "rule_based_fallback"
        else:
            risk_score = rule_risk
            detection_method = "rule_based"

        risk_score = round(min(max(risk_score, 0.0), 0.95), 2)

        # Confidence: derived from completeness of checks executed
        confidence = round(min(0.50 + (valid_checks_count / 10.0) * 0.40, 0.90), 2)

        if not findings:
            findings.append("No active forensic anomalies or tampering signals were identified.")

        return risk_score, confidence, findings, ml_risk_score, detection_method


fraud_detector = UnifiedForensicDetector()
