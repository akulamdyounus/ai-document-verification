from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path
from backend.services.authenticity_collector import authenticity_collector
from backend.services.authoritative_service import authoritative_service, AuthoritativeStatus
from backend.utils.logger import logger


class VerificationResult:
    """
    Rich verification result structure.
    Backwards-compatible: can be unpacked directly as (verdict, findings, decision_reasons).
    Also provides dedicated accessors for all independent scores.
    """

    def __init__(
        self,
        verdict: str,
        findings: List[str],
        decision_reasons: List[str],
        document_classification_confidence: float = 0.0,
        authenticity_evidence_score: float = 0.0,
        manipulation_evidence_score: float = 0.0,
        authoritative_verification_status: str = "NOT_AVAILABLE",
        authenticity_findings: Optional[List[str]] = None,
        manipulation_findings: Optional[List[str]] = None,
    ):
        self.verdict = verdict
        self.findings = findings
        self.decision_reasons = decision_reasons
        self.document_classification_confidence = document_classification_confidence
        self.authenticity_evidence_score = authenticity_evidence_score
        self.manipulation_evidence_score = manipulation_evidence_score
        self.authoritative_verification_status = authoritative_verification_status
        self.authenticity_findings = authenticity_findings or []
        self.manipulation_findings = manipulation_findings or []

    def __iter__(self):
        # Enables backwards-compatible 3-item unpacking: verdict, findings, reasons = result
        return iter([self.verdict, self.findings, self.decision_reasons])

    def __getitem__(self, idx):
        return [self.verdict, self.findings, self.decision_reasons][idx]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "document_classification_confidence": self.document_classification_confidence,
            "authenticity_evidence_score": self.authenticity_evidence_score,
            "manipulation_evidence_score": self.manipulation_evidence_score,
            "authoritative_verification_status": self.authoritative_verification_status,
            "findings": self.findings,
            "decision_reasons": self.decision_reasons,
            "authenticity_findings": self.authenticity_findings,
            "manipulation_findings": self.manipulation_findings,
        }


class VerificationEngine:
    """
    Redesigned Document Verification Decision Engine.
    Adheres strictly to core product principles:

    A. Separate Scores:
       - document_classification_confidence (identity match != authenticity)
       - authenticity_evidence_score (positive signals of genuine origin)
       - manipulation_evidence_score (forensic & tamper indicators)
       - authoritative_verification_status (issuer registry / PKI verification)

    B. Verification Verdict Hierarchy:
       - 'Verified Authentic': Authoritative check confirmed credential
       - 'Verified Invalid': Authoritative check proved credential invalid/revoked
       - 'Likely Genuine': Sufficient positive authenticity evidence (>= 0.65) AND low manipulation (<= 0.15)
       - 'Suspicious': Meaningful anomalies exist, but insufficient for Likely Fake
       - 'Likely Fake': Multiple strong independent manipulation indicators
       - 'Unable to Verify': Insufficient evidence or internally normal without enough positive proof

    C. False Positive Safeguards:
       - Canva/Adobe/iLovePDF metadata, weak ELA, or isolated footer mentions NEVER trigger Fake/Suspicious.
       - Classification confidence NEVER directly drives authenticity verdict.
       - The system NEVER claims 100% authenticity or 100% fraud.
    """

    def _get_check_domain(self, check_name: str) -> str:
        if check_name in [
            "error_level_analysis",
            "noise_variance",
            "image_sharpness",
            "splicing_detection",
        ]:
            return "visual_forensics"
        if check_name == "image_metadata":
            return "image_metadata"
        if check_name == "copy_move_detection":
            return "copy_move"
        if check_name.startswith("bank_running_balance") or check_name.startswith("bank_summary"):
            return "bank_arithmetic"
        if check_name.startswith("bank_transaction") or check_name.startswith("bank_table") or check_name.startswith("bank_malformed"):
            return "bank_table"
        if check_name.startswith("bank_identity") or check_name.startswith("bank_account") or check_name.startswith("bank_holder"):
            return "bank_identity"
        if check_name.startswith("pdf_text_overlay") or check_name.startswith("pdf_font"):
            return "pdf_text_forensics"
        if check_name.startswith("bank_cross_page") or check_name.startswith("multipage_"):
            return "multipage_consistency"
        if check_name.startswith("pdf_"):
            return "pdf_structure"
        if check_name in ["date_chronology", "statement_period_logic", "invoice_math", "identifier_syntax"]:
            return "content_consistency"
        return "general"

    def evaluate(
        self,
        document_type: str,
        confidence: float,
        fields: Dict[str, Any],
        fraud_analysis: Dict[str, Any],
        extracted_text_len: int,
        matched_signals: Optional[List[str]] = None,
        classification_status: str = "classified",
        alternative_types: Optional[List[Dict[str, Any]]] = None,
        extracted_text: str = "",
        file_path: Optional[Path] = None,
        authoritative_override: Optional[str] = None,
    ) -> VerificationResult:
        findings: List[str] = []
        decision_reasons: List[str] = []
        matched_signals = matched_signals or []
        alternative_types = alternative_types or []

        # -------------------------------------------------------------
        # 1. Authoritative Verification Layer
        # -------------------------------------------------------------
        auth_res = authoritative_service.verify(
            document_type=document_type,
            fields=fields,
            file_path=file_path,
            override_status=authoritative_override,
        )
        auth_status = auth_res.get("status", AuthoritativeStatus.NOT_AVAILABLE)

        # -------------------------------------------------------------
        # 2. Manipulation Evidence Evaluation
        # -------------------------------------------------------------
        checks = fraud_analysis.get("checks", [])
        manipulation_score = fraud_analysis.get("risk_score", 0.0)

        high_warnings = [
            c for c in checks
            if c.get("status") == "warning" and c.get("severity") in ["high", "critical"]
        ]
        medium_warnings = [
            c for c in checks
            if c.get("status") == "warning" and c.get("severity") == "medium"
        ]
        low_warnings = [
            c for c in checks
            if c.get("status") == "warning" and c.get("severity") == "low"
        ]

        warning_domains = set()
        for c in (high_warnings + medium_warnings):
            warning_domains.add(self._get_check_domain(c.get("check", "")))

        manipulation_findings: List[str] = []
        for c in (high_warnings + medium_warnings):
            msg = c.get("message", "")
            sev = c.get("severity", "medium").upper()
            manipulation_findings.append(f"[{sev}] {msg}")

        # -------------------------------------------------------------
        # 3. Positive Authenticity Evidence Evaluation
        # -------------------------------------------------------------
        authenticity_score, authenticity_findings, positive_evidence = authenticity_collector.evaluate(
            document_type=document_type,
            fields=fields,
            extracted_text=extracted_text,
            forensic_checks=checks,
        )

        # -------------------------------------------------------------
        # 4. Informational Findings Generation
        # -------------------------------------------------------------
        if document_type == "Unknown":
            if alternative_types and len(alternative_types) > 1:
                alt_summary = ", ".join([f"{a['document_type']} ({int(a['confidence'] * 100)}%)" for a in alternative_types[:2]])
                findings.append(f"Classification ambiguous between competing categories: {alt_summary}.")
            else:
                findings.append("Document classification inconclusive: insufficient characteristic category signals.")
        elif document_type == "Other Document":
            findings.append("Document text contains general content without specific identity or financial credentials.")
        else:
            findings.append(
                f"Identified as '{document_type}' with category classification confidence of {int(confidence * 100)}%."
            )

        findings.append("Important: Classification confidence reflects category identification, not document authenticity.")

        if fields:
            findings.append(f"Extracted document fields: {', '.join(fields.keys())}.")

        # Append positive authenticity findings
        for af in authenticity_findings:
            if af not in findings:
                findings.append(f"[AUTHENTICITY] {af}")

        # Append manipulation findings
        for mf in fraud_analysis.get("findings", []):
            if mf not in findings and "No active forensic anomalies" not in mf:
                findings.append(mf)

        # -------------------------------------------------------------
        # 5. Verification Decision Policy Hierarchy
        # -------------------------------------------------------------

        # Policy 1: Authoritative Override
        if auth_status == AuthoritativeStatus.VERIFIED_AUTHENTIC:
            verdict = "Verified Authentic"
            findings.append("Verification verdict: Credential validated successfully against authoritative issuer registry.")
            decision_reasons.append("Credential validated successfully against official authoritative issuer database.")
            decision_reasons.append("Authoritative confirmation establishes verified legal status.")
            return VerificationResult(
                verdict=verdict,
                findings=findings,
                decision_reasons=decision_reasons,
                document_classification_confidence=confidence,
                authenticity_evidence_score=max(authenticity_score, 0.95),
                manipulation_evidence_score=0.0,
                authoritative_verification_status=auth_status,
                authenticity_findings=authenticity_findings,
                manipulation_findings=manipulation_findings,
            )

        if auth_status == AuthoritativeStatus.VERIFIED_INVALID:
            verdict = "Verified Invalid"
            findings.append("Verification verdict: Authoritative verification proved document credential is invalid or nonexistent.")
            decision_reasons.append("Authoritative issuer registry confirmed document record is invalid, revoked, or nonexistent.")
            decision_reasons.append("Document credential rejected by issuing authority.")
            return VerificationResult(
                verdict=verdict,
                findings=findings,
                decision_reasons=decision_reasons,
                document_classification_confidence=confidence,
                authenticity_evidence_score=0.0,
                manipulation_evidence_score=1.0,
                authoritative_verification_status=auth_status,
                authenticity_findings=authenticity_findings,
                manipulation_findings=manipulation_findings,
            )

        # Policy 2: Inconclusive Classification or Insufficient Text Content
        if document_type in ["Unknown", "Other Document"] or extracted_text_len < 30 or classification_status != "classified":
            verdict = "Unable to Verify"
            findings.append("Verification verdict: Insufficient document evidence to perform reliable verification.")
            decision_reasons.append("Document classification was inconclusive or text content was insufficient.")
            decision_reasons.append("Authenticity cannot be established without adequate structural credentials.")
            return VerificationResult(
                verdict=verdict,
                findings=findings,
                decision_reasons=decision_reasons,
                document_classification_confidence=confidence,
                authenticity_evidence_score=authenticity_score,
                manipulation_evidence_score=manipulation_score,
                authoritative_verification_status=auth_status,
                authenticity_findings=authenticity_findings,
                manipulation_findings=manipulation_findings,
            )

        # Policy 3: Likely Fake
        # Requires multiple independent strong manipulation indicators
        has_multiple_strong_evidence = (
            (len(high_warnings) >= 2 and len(warning_domains) >= 2)
            or (len(high_warnings) >= 1 and len(medium_warnings) >= 2 and len(warning_domains) >= 2)
            or (manipulation_score >= 0.75 and len(warning_domains) >= 2 and (len(high_warnings) >= 2 or len(medium_warnings) >= 2))
        )
        if has_multiple_strong_evidence:
            verdict = "Likely Fake"
            findings.append("Verification verdict: Multiple concurring forensic anomalies and structural contradictions detected.")
            decision_reasons.append("Multiple strong independent manipulation indicators detected across distinct document layers.")
            for hw in high_warnings:
                decision_reasons.append(f"Critical indicator: {hw.get('message', '')}")
            for mw in medium_warnings[:2]:
                decision_reasons.append(f"Supporting anomaly: {mw.get('message', '')}")
            decision_reasons.append("High probability of digital manipulation or fabricated credential.")
            decision_reasons.append("Note: Automated analysis cannot claim 100% legal fraud without official authoritative confirmation.")
            return VerificationResult(
                verdict=verdict,
                findings=findings,
                decision_reasons=decision_reasons,
                document_classification_confidence=confidence,
                authenticity_evidence_score=min(authenticity_score, 0.20),
                manipulation_evidence_score=manipulation_score,
                authoritative_verification_status=auth_status,
                authenticity_findings=authenticity_findings,
                manipulation_findings=manipulation_findings,
            )

        # Policy 4: Suspicious
        # Used when meaningful anomalies exist, but evidence is insufficient for Likely Fake
        is_suspicious = (
            len(high_warnings) >= 1
            or (len(medium_warnings) >= 2 and len(warning_domains) >= 2)
            or (manipulation_score >= 0.35 and len(medium_warnings) >= 1)
        )
        if is_suspicious:
            verdict = "Suspicious"
            findings.append("Verification verdict: Document exhibits suspicious characteristics or anomalies warranting manual review.")
            if len(high_warnings) > 0:
                decision_reasons.append("High-severity anomaly detected warranting manual review.")
                for hw in high_warnings:
                    decision_reasons.append(f"Suspicious indicator: {hw.get('message', '')}")
            else:
                decision_reasons.append("Multiple independent medium-severity anomalies detected.")
                for mw in medium_warnings:
                    decision_reasons.append(f"Suspicious indicator: {mw.get('message', '')}")

            decision_reasons.append("Document exhibits suspicious characteristics, but evidence is insufficient for a Likely Fake verdict.")
            return VerificationResult(
                verdict=verdict,
                findings=findings,
                decision_reasons=decision_reasons,
                document_classification_confidence=confidence,
                authenticity_evidence_score=authenticity_score,
                manipulation_evidence_score=manipulation_score,
                authoritative_verification_status=auth_status,
                authenticity_findings=authenticity_findings,
                manipulation_findings=manipulation_findings,
            )

        # Policy 5: Likely Genuine
        # Strict Rule: Only return Likely Genuine when:
        # - No meaningful manipulation indicators exist (manipulation score <= 0.15)
        # - Internal consistency checks pass
        # - Document structure/layout is coherent
        # - Important fields are internally consistent
        # - AND there is enough positive authenticity evidence for the document type (>= 0.65)
        is_clean_of_manipulation = manipulation_score <= 0.15 and len(high_warnings) == 0 and len(medium_warnings) == 0
        has_sufficient_positive_evidence = authenticity_score >= 0.65

        if is_clean_of_manipulation and has_sufficient_positive_evidence:
            verdict = "Likely Genuine"
            findings.append(
                "Verification verdict: Likely Genuine — Comprehensive positive authenticity evidence verified with zero manipulation anomalies."
            )
            decision_reasons.append("Zero manipulation indicators or forensic anomalies detected.")
            decision_reasons.append("Document structure, layout, and credential syntax conform to authentic standards.")
            for af in authenticity_findings:
                decision_reasons.append(f"Authenticity evidence: {af}")
            decision_reasons.append("Classification confidence reflects category identification, independently corroborated by forensic authenticity evidence.")
            decision_reasons.append("Note: Automated analysis cannot claim 100% legal authenticity without authoritative issuer registry verification.")
            return VerificationResult(
                verdict=verdict,
                findings=findings,
                decision_reasons=decision_reasons,
                document_classification_confidence=confidence,
                authenticity_evidence_score=authenticity_score,
                manipulation_evidence_score=manipulation_score,
                authoritative_verification_status=auth_status,
                authenticity_findings=authenticity_findings,
                manipulation_findings=manipulation_findings,
            )

        # Policy 6: Unable to Verify (Conservative Default)
        # When document appears internally normal, but positive authenticity evidence is insufficient
        verdict = "Unable to Verify"
        findings.append(
            "Verification verdict: Unable to Verify — No significant manipulation indicators were detected, "
            "but automated forensic analysis cannot establish document authenticity without authoritative verification."
        )

        decision_reasons.append("No high-severity forensic indicators detected.")
        if authenticity_score < 0.65:
            decision_reasons.append(
                f"Positive authenticity evidence score ({int(authenticity_score * 100)}%) is below the threshold (65%) required for Likely Genuine."
            )
        decision_reasons.append("Authenticity cannot be established without authoritative verification.")
        decision_reasons.append("Classification confidence reflects category match only, not authenticity confidence.")

        return VerificationResult(
            verdict=verdict,
            findings=findings,
            decision_reasons=decision_reasons,
            document_classification_confidence=confidence,
            authenticity_evidence_score=authenticity_score,
            manipulation_evidence_score=manipulation_score,
            authoritative_verification_status=auth_status,
            authenticity_findings=authenticity_findings,
            manipulation_findings=manipulation_findings,
        )


verification_engine = VerificationEngine()
