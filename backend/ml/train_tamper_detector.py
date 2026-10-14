"""
Document Tampering Risk Classifier Training Script.
Generates multi-modal forensic feature samples (clean vs tampered),
trains a calibrated ensemble classifier, and serializes the model to models/tamper_risk_classifier_v1.joblib.
"""

import json
import os
import random
from datetime import datetime
from typing import Dict, Any, Tuple, List

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    confusion_matrix,
    classification_report,
    brier_score_loss,
)

from backend.services.forensic_feature_extractor import (
    FORENSIC_FEATURE_NAMES,
    forensic_feature_extractor,
)
from backend.utils.logger import logger


MODEL_OUTPUT_PATH = os.path.join("models", "tamper_risk_classifier_v1.joblib")
METADATA_OUTPUT_PATH = os.path.join("models", "tamper_model_metadata.json")


def _generate_clean_sample() -> Dict[str, float]:
    """Generates synthetic feature vector for a genuine, untampered document."""
    is_pdf = random.random() < 0.5
    has_web_resave = random.random() < 0.20
    has_camera_compression = random.random() < 0.35
    has_slight_blur = random.random() < 0.06

    return {
        "ela_mean_error": float(random.uniform(0.05, 12.0)),
        "ela_std_error": float(random.uniform(0.1, 8.0)),
        "ela_max_error": float(random.uniform(25.0, 72.0)) if has_camera_compression else float(random.uniform(5.0, 45.0)),
        "ela_anomaly_pixel_ratio": float(random.uniform(0.02, 0.45)) if has_camera_compression else float(random.uniform(0.0, 0.015)),
        "noise_mean_laplacian_var": float(random.uniform(25.0, 3200.0)),
        "noise_median_var": float(random.uniform(0.0, 120.0)),
        "noise_min_var": float(random.uniform(0.0, 10.0)),
        "noise_flat_blocks_ratio": float(random.uniform(0.0, 0.95)),
        "sharpness_laplacian_var": float(random.uniform(25.0, 75.0)) if has_slight_blur else float(random.uniform(85.0, 3500.0)),
        "sharpness_is_defocused": 1.0 if has_slight_blur else 0.0,
        "splicing_patch_corners": float(random.choice([0, 0, 0, 1, 2, 4])),  # Authentic ID cards/forms have photo/table box corners
        "copy_move_clustered_vectors": float(random.randint(0, 18)),
        "copy_move_candidate_matches": float(random.randint(0, 420)),
        "copy_move_total_keypoints": float(random.randint(80, 1400)),
        "has_editing_software_signature": 1.0 if has_web_resave else 0.0,  # Legitimate PDF/web exports happen
        "pdf_timestamp_delta_days": float(random.uniform(0.0, 180.0)) if is_pdf else 0.0,
        "pdf_timestamp_anomaly_flag": 0.0,
        "pdf_embedded_fonts_count": float(random.randint(2, 9)) if is_pdf else 0.0,
        "pdf_has_digital_text": 1.0 if is_pdf else 0.0,
        "date_chronology_issues_count": 0.0,
        "invoice_math_discrepancy": 0.0,
        "identifier_syntax_valid": 1.0,
        "bank_running_balance_discrepancies": 0.0,
        "bank_identity_conflict_flag": 0.0,
    }


def _generate_tampered_sample() -> Dict[str, float]:
    """Generates synthetic feature vector for a tampered/fraudulent document."""
    sample = _generate_clean_sample()
    tamper_types = [
        "splicing",
        "copy_move",
        "metadata_injection",
        "chronology_anomaly",
        "math_discrepancy",
        "timestamp_manipulation",
        "bank_running_balance_fraud",
        "bank_identity_fraud",
    ]
    # Apply 1 to 3 concurrent tampering artifacts
    selected_tampers = random.sample(tamper_types, k=random.randint(1, 3))

    for t in selected_tampers:
        if t == "splicing":
            sample["splicing_patch_corners"] = float(random.randint(6, 36))
            sample["ela_max_error"] = float(random.uniform(80.0, 240.0))
            sample["ela_anomaly_pixel_ratio"] = float(random.uniform(0.04, 0.30))
        elif t == "copy_move":
            sample["copy_move_clustered_vectors"] = float(random.randint(28, 95))
            sample["copy_move_candidate_matches"] = float(random.randint(80, 520))
        elif t == "metadata_injection":
            sample["has_editing_software_signature"] = 1.0
            sample["ela_max_error"] = float(random.uniform(65.0, 160.0))
        elif t == "chronology_anomaly":
            sample["date_chronology_issues_count"] = float(random.randint(1, 4))
        elif t == "math_discrepancy":
            sample["invoice_math_discrepancy"] = float(random.uniform(45.0, 4500.0))
        elif t == "timestamp_manipulation":
            sample["pdf_timestamp_delta_days"] = float(random.uniform(90.0, 450.0))
            sample["pdf_timestamp_anomaly_flag"] = 1.0
        elif t == "bank_running_balance_fraud":
            sample["bank_running_balance_discrepancies"] = float(random.randint(1, 8))
        elif t == "bank_identity_fraud":
            sample["bank_identity_conflict_flag"] = 1.0

    return sample


def generate_forensic_dataset(
    n_samples: int = 1600, seed: int = 42
) -> Tuple[np.ndarray, np.ndarray]:
    """Generates a balanced dataset of clean (0) and tampered (1) feature vectors."""
    random.seed(seed)
    np.random.seed(seed)

    X_list: List[List[float]] = []
    y_list: List[int] = []

    half = n_samples // 2

    for _ in range(half):
        feat_dict = _generate_clean_sample()
        vec = [feat_dict[k] for k in FORENSIC_FEATURE_NAMES]
        X_list.append(vec)
        y_list.append(0)

    for _ in range(half):
        feat_dict = _generate_tampered_sample()
        vec = [feat_dict[k] for k in FORENSIC_FEATURE_NAMES]
        X_list.append(vec)
        y_list.append(1)

    # Introduce ~1.5% soft boundary noise to prevent over-optimizing to sharp step edges
    noise_count = int(n_samples * 0.015)
    noise_indices = random.sample(range(n_samples), noise_count)
    for idx in noise_indices:
        y_list[idx] = 1 - y_list[idx]

    # Shuffle
    combined = list(zip(X_list, y_list))
    random.shuffle(combined)
    X_shuffled, y_shuffled = zip(*combined)

    return np.array(X_shuffled, dtype=np.float32), np.array(y_shuffled, dtype=np.int32)


def train_and_evaluate_tamper_detector(
    n_samples: int = 1400,
    model_path: str = MODEL_OUTPUT_PATH,
    metadata_path: str = METADATA_OUTPUT_PATH,
    seed: int = 42,
) -> Dict[str, Any]:
    """Trains a calibrated Gradient Boosting tampering classifier and evaluates performance."""
    logger.info(f"Generating synthetic forensic tampering dataset ({n_samples} samples)...")
    X, y = generate_forensic_dataset(n_samples=n_samples, seed=seed)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=seed, stratify=y
    )
    logger.info(f"Split: {len(X_train)} train, {len(X_test)} test.")

    # Base estimator: Regularized Gradient Boosting Classifier
    base_clf = GradientBoostingClassifier(
        n_estimators=100,
        learning_rate=0.08,
        max_depth=4,
        subsample=0.85,
        random_state=seed,
    )

    # Calibrated Classifier: ensures predict_proba maps strictly to true posterior risk probability
    calibrated_clf = CalibratedClassifierCV(
        estimator=base_clf,
        method="sigmoid",
        cv=5,
    )

    logger.info("Fitting Calibrated Gradient Boosting Tamper Risk Classifier...")
    calibrated_clf.fit(X_train, y_train)

    # Also fit base estimator standalone to extract feature importances
    base_clf.fit(X_train, y_train)
    raw_importances = base_clf.feature_importances_
    sorted_feat_indices = np.argsort(raw_importances)[::-1]
    feature_ranking = [
        {"feature": FORENSIC_FEATURE_NAMES[i], "importance": round(float(raw_importances[i]), 4)}
        for i in sorted_feat_indices
    ]

    # Test set evaluation
    y_pred = calibrated_clf.predict(X_test)
    y_prob = calibrated_clf.predict_proba(X_test)[:, 1]

    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred)
    rec = recall_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred)
    auc = roc_auc_score(y_test, y_prob)
    brier = brier_score_loss(y_test, y_prob)
    cm = confusion_matrix(y_test, y_pred).tolist()

    print("\n" + "=" * 65)
    print("TAMPERING RISK MODEL EVALUATION ON HELD-OUT TEST SPLIT (20%):")
    print("=" * 65)
    print(f"Accuracy         : {acc * 100:.2f}%")
    print(f"ROC-AUC Score    : {auc:.4f}")
    print(f"Precision        : {prec * 100:.2f}%")
    print(f"Recall           : {rec * 100:.2f}%")
    print(f"F1-Score         : {f1:.4f}")
    print(f"Brier Loss       : {brier:.4f} (lower is better calibrated)")
    print("\nConfusion Matrix (Rows=True, Cols=Pred):")
    print(f"  [Clean:    {cm[0][0]:3d}  (FP: {cm[0][1]:3d})]")
    print(f"  [Tampered: {cm[1][1]:3d}  (FN: {cm[1][0]:3d})]\n")

    print("Top 8 Forensic Features Driving Risk Decisions:")
    for f in feature_ranking[:8]:
        print(f"  - {f['feature']:<32} : {f['importance'] * 100:.2f}%")
    print("=" * 65 + "\n")

    # Serialize trained model pipeline
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    joblib.dump(calibrated_clf, model_path)
    logger.info(f"Tamper risk model saved to: {model_path}")

    metadata = {
        "model_name": "tamper_risk_calibrated_gradient_boosting_v1",
        "algorithm": "CalibratedClassifierCV(GradientBoostingClassifier(n_estimators=100, max_depth=4))",
        "feature_count": len(FORENSIC_FEATURE_NAMES),
        "feature_names": FORENSIC_FEATURE_NAMES,
        "feature_importances": feature_ranking,
        "total_samples": len(X),
        "train_samples": len(X_train),
        "test_samples": len(X_test),
        "metrics": {
            "accuracy": round(float(acc), 4),
            "roc_auc": round(float(auc), 4),
            "precision": round(float(prec), 4),
            "recall": round(float(rec), 4),
            "f1_score": round(float(f1), 4),
            "brier_score": round(float(brier), 4),
        },
        "confusion_matrix": cm,
        "saved_path": model_path,
        "trained_at": datetime.utcnow().isoformat() + "Z",
    }

    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    logger.info(f"Metadata saved to: {metadata_path}")

    return metadata


if __name__ == "__main__":
    train_and_evaluate_tamper_detector()
