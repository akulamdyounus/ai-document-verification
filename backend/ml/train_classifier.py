"""
Document Classifier Training Script.
Trains a TF-IDF + Logistic Regression classification pipeline on a privacy-safe synthetic corpus.
Saves the serialized pipeline to models/document_classifier_v1.joblib with full evaluation metrics.
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, Any, Tuple

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score, confusion_matrix

from backend.ml.dataset_generator import generate_dataset
from backend.services.text_normalizer import text_normalizer
from backend.utils.logger import logger


MODEL_OUTPUT_PATH = os.path.join("models", "document_classifier_v1.joblib")
METADATA_OUTPUT_PATH = os.path.join("models", "model_metadata.json")


def prepare_data(samples_per_class: int = 120, seed: int = 42) -> Tuple[list, list]:
    """Generates synthetic dataset and normalizes text for training."""
    raw_dataset = generate_dataset(samples_per_class=samples_per_class, seed=seed)
    texts = []
    labels = []
    for item in raw_dataset:
        normalized_text = text_normalizer.normalize(item["text"])
        texts.append(normalized_text)
        labels.append(item["label"])
    return texts, labels


def train_and_evaluate(
    samples_per_class: int = 120,
    model_path: str = MODEL_OUTPUT_PATH,
    metadata_path: str = METADATA_OUTPUT_PATH,
    seed: int = 42,
) -> Dict[str, Any]:
    """
    Executes end-to-end training, cross-validation evaluation, and model serialization.
    """
    logger.info(f"Generating synthetic dataset with {samples_per_class} samples per class...")
    texts, labels = prepare_data(samples_per_class=samples_per_class, seed=seed)

    # 80/20 Stratified train/test split
    X_train, X_test, y_train, y_test = train_test_split(
        texts,
        labels,
        test_size=0.20,
        random_state=seed,
        stratify=labels,
    )

    logger.info(f"Dataset split: {len(X_train)} train samples, {len(X_test)} test samples.")

    # Build Pipeline: TF-IDF n-grams (1-2) + Regularized Logistic Regression
    pipeline = Pipeline([
        (
            "tfidf",
            TfidfVectorizer(
                ngram_range=(1, 2),
                max_features=10000,
                sublinear_tf=True,
                lowercase=True,
                strip_accents="unicode",
            ),
        ),
        (
            "clf",
            LogisticRegression(
                C=5.0,
                max_iter=1000,
                class_weight="balanced",
                random_state=seed,
            ),
        ),
    ])

    logger.info("Fitting TF-IDF + Logistic Regression pipeline...")
    pipeline.fit(X_train, y_train)

    # Evaluation on held-out test split
    y_pred = pipeline.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    report = classification_report(y_test, y_pred, output_dict=True)
    report_text = classification_report(y_test, y_pred)
    cm = confusion_matrix(y_test, y_pred, labels=pipeline.classes_).tolist()

    print("\n" + "=" * 60)
    print("CLASSIFICATION REPORT ON HELD-OUT TEST SPLIT (20%):")
    print("=" * 60)
    print(report_text)
    print(f"Overall Accuracy: {acc * 100:.2f}%\n")

    # Serialize trained pipeline
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    joblib.dump(pipeline, model_path)
    logger.info(f"Model saved to: {model_path}")

    # Build metadata artifact
    metadata = {
        "model_name": "tfidf_logistic_regression_v1",
        "algorithm": "TfidfVectorizer(ngram_range=(1, 2), max_features=10000) + LogisticRegression(C=5.0)",
        "classes": pipeline.classes_.tolist(),
        "total_samples": len(texts),
        "train_samples": len(X_train),
        "test_samples": len(X_test),
        "metrics": {
            "accuracy": round(float(acc), 4),
            "macro_avg_f1": round(float(report["macro avg"]["f1-score"]), 4),
            "weighted_avg_f1": round(float(report["weighted avg"]["f1-score"]), 4),
            "per_class": {
                cls: {
                    "precision": round(float(metrics["precision"]), 4),
                    "recall": round(float(metrics["recall"]), 4),
                    "f1-score": round(float(metrics["f1-score"]), 4),
                    "support": metrics["support"],
                }
                for cls, metrics in report.items()
                if cls in pipeline.classes_
            },
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
    meta = train_and_evaluate()
    print("Training successfully completed!")
    print(f"Accuracy: {meta['metrics']['accuracy'] * 100:.2f}% | Macro F1: {meta['metrics']['macro_avg_f1']:.4f}")
