import os
import re
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import joblib

from backend.services.document_signatures import DOCUMENT_SIGNATURES
from backend.services.text_normalizer import text_normalizer
from backend.config import MODELS_DIR, PROJECT_ROOT
from backend.utils.logger import logger


@dataclass
class ClassificationResult:
    document_type: str
    confidence: float
    method: str
    matched_signals: List[str]
    alternative_types: List[Dict[str, Any]]
    classification_status: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BaseDocumentClassifier:
    """
    Abstract interface for document classifiers.
    Permits hot-swapping rule-based logic with ML/deep-learning models.
    """
    def classify(self, text: str) -> ClassificationResult:
        raise NotImplementedError


class RuleBasedDocumentClassifier(BaseDocumentClassifier):
    """
    Phase 2A Multi-Signal Rule-Based Document Classifier.
    - Uses normalized text for robust OCR matching.
    - Evaluates primary, secondary, and structural pattern signals.
    - Enforces minimum signal counts to avoid single-word false triggers.
    - Identifies ambiguous / conflicting document types.
    - Returns transparent confidence and matched signal evidence.
    """

    def __init__(self, signatures: Optional[Dict[str, Dict[str, Any]]] = None):
        self.signatures = signatures or DOCUMENT_SIGNATURES

    def classify(self, text: str) -> ClassificationResult:
        # 1. Check for empty or negligible text
        if not text or len(text.strip()) < 5:
            return ClassificationResult(
                document_type="Unknown",
                confidence=0.0,
                method="rule_based",
                matched_signals=[],
                alternative_types=[],
                classification_status="insufficient_evidence",
            )

        # 2. Normalize text (preserves original for caller)
        normalized = text_normalizer.normalize(text)

        category_evaluations: List[Dict[str, Any]] = []

        # 3. Evaluate each document category against signatures
        for doc_type, sig in self.signatures.items():
            matched_signals: List[str] = []
            primary_matches: List[str] = []
            secondary_matches: List[str] = []
            pattern_matches: List[str] = []

            # A. Primary signals (high weight)
            for phrase in sig.get("primary_signals", []):
                if phrase in normalized:
                    primary_matches.append(phrase)
                    matched_signals.append(phrase)

            # B. Secondary signals (supporting weight)
            for term in sig.get("secondary_signals", []):
                # Word boundary check for short terms
                pattern = r"\b" + re.escape(term) + r"\b"
                if re.search(pattern, normalized):
                    secondary_matches.append(term)
                    if term not in matched_signals:
                        matched_signals.append(term)

            # C. Structural regex patterns
            for regex_str in sig.get("structural_patterns", []):
                match = re.search(regex_str, text, re.IGNORECASE) or re.search(regex_str, normalized)
                if match:
                    pattern_matches.append(regex_str)
                    matched_signals.append(f"pattern({match.group(0)[:20]})")

            total_distinct_signals = len(matched_signals)
            min_required = sig.get("min_signals_required", 2)

            # If minimum required signals are not met, disqualify from claiming this category
            if total_distinct_signals < min_required:
                continue

            # Calculate weighted evidence points
            evidence_points = (
                len(primary_matches) * 3.0 +
                len(secondary_matches) * 1.0 +
                len(pattern_matches) * 2.5
            )

            # Weight category modifier
            cat_weight = sig.get("category_weight", 1.0)
            raw_score = evidence_points * cat_weight

            # Compute normalized confidence score:
            # Saturation curve that requires strong multiple evidence to reach 0.85-0.95
            confidence = round(min(0.35 + (raw_score / (raw_score + 5.0)) * 0.60, 0.95), 2)

            category_evaluations.append({
                "document_type": doc_type,
                "confidence": confidence,
                "raw_score": raw_score,
                "matched_signals": matched_signals,
            })

        # 4. Handle case with no qualifying categories
        if not category_evaluations:
            words = text.split()
            # If document has substantial readable content but no specific domain match
            if len(words) > 25:
                return ClassificationResult(
                    document_type="Other Document",
                    confidence=0.30,
                    method="rule_based",
                    matched_signals=[],
                    alternative_types=[],
                    classification_status="insufficient_evidence",
                )
            return ClassificationResult(
                document_type="Unknown",
                confidence=0.15,
                method="rule_based",
                matched_signals=[],
                alternative_types=[],
                classification_status="insufficient_evidence",
            )

        # 5. Sort candidate categories by confidence descending
        category_evaluations.sort(key=lambda x: (x["confidence"], x["raw_score"]), reverse=True)
        top = category_evaluations[0]

        # 6. Check for Ambiguity / Close competing categories
        if len(category_evaluations) > 1:
            second = category_evaluations[1]
            diff = top["confidence"] - second["confidence"]

            # If top two candidates are within margin of 0.12 and second is substantial (>= 0.40)
            if diff < 0.12 and second["confidence"] >= 0.40:
                logger.info(
                    f"Ambiguity detected between {top['document_type']} ({top['confidence']}) "
                    f"and {second['document_type']} ({second['confidence']}). Returning Unknown."
                )
                alternatives = [
                    {"document_type": c["document_type"], "confidence": c["confidence"]}
                    for c in category_evaluations[:3]
                ]
                return ClassificationResult(
                    document_type="Unknown",
                    confidence=round((top["confidence"] + second["confidence"]) / 2, 2),
                    method="rule_based",
                    matched_signals=top["matched_signals"][:4],
                    alternative_types=alternatives,
                    classification_status="insufficient_evidence",
                )

        # 7. Low confidence threshold check
        if top["confidence"] < 0.35:
            return ClassificationResult(
                document_type="Unknown",
                confidence=top["confidence"],
                method="rule_based",
                matched_signals=top["matched_signals"],
                alternative_types=[],
                classification_status="insufficient_evidence",
            )

        # 8. Clear, unambiguous classification
        alternative_types = [
            {"document_type": c["document_type"], "confidence": c["confidence"]}
            for c in category_evaluations[1:3]
            if c["confidence"] >= 0.30
        ]

        return ClassificationResult(
            document_type=top["document_type"],
            confidence=top["confidence"],
            method="rule_based",
            matched_signals=top["matched_signals"],
            alternative_types=alternative_types,
            classification_status="classified",
        )


class MLDocumentClassifier(BaseDocumentClassifier):
    """
    Trained Machine Learning Document Classifier.
    Evaluates documents using TF-IDF n-grams and Logistic Regression probability distribution.
    Extracts contributing n-gram signals for explainability.
    """

    def __init__(self, model_path: Optional[str] = None):
        if model_path:
            self.model_path = str(model_path)
        else:
            primary_path = MODELS_DIR / "document_classifier_v1.joblib"
            fallback_path = PROJECT_ROOT / "models" / "document_classifier_v1.joblib"
            if primary_path.exists():
                self.model_path = str(primary_path)
            elif fallback_path.exists():
                self.model_path = str(fallback_path)
            else:
                self.model_path = str(primary_path)
        self.pipeline = None
        self._load_model()

    def _load_model(self) -> bool:
        if os.path.exists(self.model_path):
            try:
                self.pipeline = joblib.load(self.model_path)
                logger.info(f"Loaded ML document classifier from {self.model_path}")
                return True
            except Exception as e:
                logger.error(f"Error loading ML model from {self.model_path}: {e}")
                self.pipeline = None
        return False

    def is_available(self) -> bool:
        return self.pipeline is not None

    def classify(self, text: str) -> ClassificationResult:
        if not text or len(text.strip()) < 5:
            return ClassificationResult(
                document_type="Unknown",
                confidence=0.0,
                method="machine_learning",
                matched_signals=[],
                alternative_types=[],
                classification_status="insufficient_evidence",
            )

        if not self.is_available():
            raise RuntimeError("ML model pipeline is not available.")

        normalized = text_normalizer.normalize(text)
        probs = self.pipeline.predict_proba([normalized])[0]
        classes = self.pipeline.classes_

        ranked = sorted(zip(classes, probs), key=lambda x: x[1], reverse=True)
        top_class, top_prob = ranked[0]
        top_confidence = round(float(top_prob), 2)

        matched_signals = self._extract_contributing_features(normalized, top_class)

        alternative_types = [
            {"document_type": c, "confidence": round(float(p), 2)}
            for c, p in ranked[1:4]
            if p >= 0.10 and c not in ["Other Document", "Unknown"]
        ]

        if top_class == "Other Document" or top_confidence < 0.35:
            doc_type = "Other Document" if len(text.split()) > 25 else "Unknown"
            return ClassificationResult(
                document_type=doc_type,
                confidence=top_confidence,
                method="machine_learning",
                matched_signals=matched_signals,
                alternative_types=alternative_types,
                classification_status="insufficient_evidence",
            )

        if len(ranked) > 1:
            second_class, second_prob = ranked[1]
            diff = top_prob - second_prob
            if diff < 0.12 and second_prob >= 0.35 and second_class not in ["Other Document", "Unknown"]:
                logger.info(
                    f"ML ambiguity detected between {top_class} ({top_prob:.2f}) and {second_class} ({second_prob:.2f})"
                )
                return ClassificationResult(
                    document_type="Unknown",
                    confidence=round(float((top_prob + second_prob) / 2), 2),
                    method="machine_learning",
                    matched_signals=matched_signals,
                    alternative_types=alternative_types,
                    classification_status="insufficient_evidence",
                )

        return ClassificationResult(
            document_type=top_class,
            confidence=top_confidence,
            method="machine_learning",
            matched_signals=matched_signals,
            alternative_types=alternative_types,
            classification_status="classified",
        )

    def _extract_contributing_features(self, text: str, target_class: str, top_k: int = 5) -> List[str]:
        try:
            tfidf = self.pipeline.named_steps["tfidf"]
            clf = self.pipeline.named_steps["clf"]
            class_idx = list(clf.classes_).index(target_class)
            weights = clf.coef_[class_idx]
            feature_names = tfidf.get_feature_names_out()

            vec = tfidf.transform([text]).toarray()[0]
            present_indices = [i for i, v in enumerate(vec) if v > 0 and weights[i] > 0]
            sorted_indices = sorted(present_indices, key=lambda i: vec[i] * weights[i], reverse=True)
            return [feature_names[i] for i in sorted_indices[:top_k]]
        except Exception:
            return []


class HybridDocumentClassifier(BaseDocumentClassifier):
    """
    Ensemble Hybrid Document Classifier combining:
    1. Machine Learning (Statistical TF-IDF classification)
    2. Rule-Based Signatures (Deterministic keyword & regex pattern matching)

    Guarantees seamless fallback to rule-based classification if the ML model
    is unavailable, fails to load, or produces low-confidence predictions.
    """

    def __init__(
        self,
        ml_model_path: Optional[str] = None,
        signatures: Optional[Dict[str, Dict[str, Any]]] = None,
    ):
        self.rule_classifier = RuleBasedDocumentClassifier(signatures=signatures)
        self.ml_classifier = MLDocumentClassifier(model_path=ml_model_path)

    def classify(self, text: str) -> ClassificationResult:
        # Fallback to rule-based if ML model is unavailable
        if not self.ml_classifier.is_available():
            return self.rule_classifier.classify(text)

        rule_res = self.rule_classifier.classify(text)

        try:
            ml_res = self.ml_classifier.classify(text)
        except Exception as e:
            logger.warning(f"ML classification failed, falling back to rule-based: {e}")
            return rule_res

        # If both agree on insufficient evidence
        if (
            ml_res.classification_status == "insufficient_evidence"
            and rule_res.classification_status == "insufficient_evidence"
        ):
            return ml_res

        # Mutual agreement: Both successfully classified as the same document type
        if ml_res.classification_status == "classified" and rule_res.classification_status == "classified":
            if ml_res.document_type == rule_res.document_type:
                # Merge matched signals (rule signals + ML feature n-grams)
                combined_signals = list(dict.fromkeys(rule_res.matched_signals + ml_res.matched_signals))
                # Boost confidence slightly for mutual corroboration
                hybrid_conf = round(min(0.98, max(rule_res.confidence, ml_res.confidence) + 0.05), 2)
                return ClassificationResult(
                    document_type=ml_res.document_type,
                    confidence=hybrid_conf,
                    method="hybrid",
                    matched_signals=combined_signals,
                    alternative_types=rule_res.alternative_types or ml_res.alternative_types,
                    classification_status="classified",
                )
            else:
                # Conflict: higher confidence wins, prioritizing rule-based when confident
                if rule_res.confidence >= 0.70:
                    return rule_res
                return ml_res

        # ML recognized format where rule-based signals were incomplete (e.g. OCR noise)
        if ml_res.classification_status == "classified" and rule_res.classification_status == "insufficient_evidence":
            if ml_res.confidence >= 0.50:
                return ml_res
            return rule_res

        # Rule-based matched structural signals where ML had low confidence
        if rule_res.classification_status == "classified":
            return rule_res

        return rule_res


document_classifier = HybridDocumentClassifier()
