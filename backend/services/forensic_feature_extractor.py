"""
Forensic Feature Extractor.
Extracts a standardized, deterministic 22-dimensional numerical feature vector
from multi-modal forensic checks (image, PDF, copy-move, and consistency checks)
for machine learning document tampering risk detection.
"""

from typing import List, Dict, Any, Optional
import numpy as np


FORENSIC_FEATURE_NAMES = [
    # 1. Image Compression & Error Level Analysis
    "ela_mean_error",
    "ela_std_error",
    "ela_max_error",
    "ela_anomaly_pixel_ratio",
    # 2. Local Noise & Block Texture
    "noise_mean_laplacian_var",
    "noise_median_var",
    "noise_min_var",
    "noise_flat_blocks_ratio",
    # 3. Global Sharpness & Defocus Blur
    "sharpness_laplacian_var",
    "sharpness_is_defocused",
    # 4. Splicing & Patch Boundary Gradients
    "splicing_patch_corners",
    # 5. Copy-Move Forgery Clones
    "copy_move_clustered_vectors",
    "copy_move_candidate_matches",
    "copy_move_total_keypoints",
    # 6. Metadata & Editing Tool Signatures
    "has_editing_software_signature",
    # 7. PDF Layer & Structural Forensics
    "pdf_timestamp_delta_days",
    "pdf_timestamp_anomaly_flag",
    "pdf_embedded_fonts_count",
    "pdf_has_digital_text",
    # 8. Content & Logical Consistency
    "date_chronology_issues_count",
    "invoice_math_discrepancy",
    "identifier_syntax_valid",
    # 9. Bank Statement & Financial Arithmetic
    "bank_running_balance_discrepancies",
    "bank_identity_conflict_flag",
]


class ForensicFeatureExtractor:
    """
    Transforms structured forensic check reports into numerical feature vectors
    suitable for training and real-time inference with tabular ML models.
    """

    FEATURE_NAMES = FORENSIC_FEATURE_NAMES

    def extract_features(self, checks: List[Dict[str, Any]]) -> Dict[str, float]:
        """
        Parses raw forensic checks and returns a complete dictionary of numerical features.
        Provides safe neutral defaults for missing checks or document-type-specific checks.
        """
        check_map = {c.get("check", ""): c for c in checks if isinstance(c, dict)}

        features: Dict[str, float] = {}

        # -------------------------------------------------------------
        # 1. Error Level Analysis (ELA)
        # -------------------------------------------------------------
        ela = check_map.get("error_level_analysis", {}).get("evidence", {})
        features["ela_mean_error"] = float(ela.get("mean_error", 0.0) or 0.0)
        features["ela_std_error"] = float(ela.get("std_error", 0.0) or 0.0)
        features["ela_max_error"] = float(ela.get("max_error", 0.0) or 0.0)
        features["ela_anomaly_pixel_ratio"] = float(ela.get("anomaly_pixel_ratio", 0.0) or 0.0)

        # -------------------------------------------------------------
        # 2. Local Noise & Block Variance
        # -------------------------------------------------------------
        noise = check_map.get("noise_variance", {}).get("evidence", {})
        features["noise_mean_laplacian_var"] = float(noise.get("mean_laplacian_variance", 50.0) or 50.0)
        features["noise_median_var"] = float(noise.get("median_variance", 20.0) or 20.0)
        features["noise_min_var"] = float(noise.get("min_variance", 0.0) or 0.0)
        features["noise_flat_blocks_ratio"] = float(noise.get("flat_blocks_ratio", 0.0) or 0.0)

        # -------------------------------------------------------------
        # 3. Global Sharpness & Blur
        # -------------------------------------------------------------
        sharpness = check_map.get("image_sharpness", {}).get("evidence", {})
        features["sharpness_laplacian_var"] = float(sharpness.get("laplacian_variance", 200.0) or 200.0)
        features["sharpness_is_defocused"] = 1.0 if sharpness.get("is_defocused", False) else 0.0

        # -------------------------------------------------------------
        # 4. Splicing / Patch Boundary Gradients
        # -------------------------------------------------------------
        splicing = check_map.get("splicing_detection", {}).get("evidence", {})
        features["splicing_patch_corners"] = float(splicing.get("suspicious_patch_corners", 0) or 0)

        # -------------------------------------------------------------
        # 5. Copy-Move Cloned Features
        # -------------------------------------------------------------
        cm = check_map.get("copy_move_detection", {}).get("evidence", {})
        features["copy_move_clustered_vectors"] = float(cm.get("clustered_vector_count", 0) or 0)
        features["copy_move_candidate_matches"] = float(cm.get("candidate_matches", 0) or 0)
        features["copy_move_total_keypoints"] = float(cm.get("total_keypoints", 0) or 0)

        # -------------------------------------------------------------
        # 6. Editing Software Signatures (Image or PDF)
        # -------------------------------------------------------------
        img_meta = check_map.get("image_metadata", {}).get("evidence", {})
        pdf_meta = check_map.get("pdf_metadata", {}).get("evidence", {})

        has_img_editor = len(img_meta.get("detected_editing_tools", []) or []) > 0
        has_pdf_editor = len(pdf_meta.get("detected_editing_tools", []) or []) > 0
        features["has_editing_software_signature"] = 1.0 if (has_img_editor or has_pdf_editor) else 0.0

        # -------------------------------------------------------------
        # 7. PDF Layer & Timestamp Forensics
        # -------------------------------------------------------------
        pdf_time = check_map.get("pdf_timestamps", {})
        time_msg = pdf_time.get("message", "")
        # Parse delta days if present in warning message, else 0
        delta_days = 0.0
        if "days after original creation" in time_msg:
            try:
                import re
                m = re.search(r"(\d+)\s+days", time_msg)
                if m:
                    delta_days = float(m.group(1))
            except Exception:
                delta_days = 0.0
        features["pdf_timestamp_delta_days"] = float(delta_days)
        features["pdf_timestamp_anomaly_flag"] = (
            1.0 if ("precedes creation date" in time_msg or pdf_time.get("severity") == "medium") else 0.0
        )

        pdf_struct = check_map.get("pdf_structure", {}).get("evidence", {})
        features["pdf_embedded_fonts_count"] = float(pdf_struct.get("embedded_fonts_count", 0) or 0)
        features["pdf_has_digital_text"] = 1.0 if pdf_struct.get("has_digital_text", False) else 0.0

        # -------------------------------------------------------------
        # 8. Content & Logical Consistency
        # -------------------------------------------------------------
        chrono = check_map.get("date_chronology", {}).get("evidence", {})
        features["date_chronology_issues_count"] = float(len(chrono.get("issues", []) or []))

        inv_math = check_map.get("invoice_math", {}).get("evidence", {})
        subtotal = float(inv_math.get("subtotal", 0.0) or 0.0)
        total = float(inv_math.get("total", 0.0) or 0.0)
        features["invoice_math_discrepancy"] = float(max(0.0, subtotal - total) if (subtotal and total) else 0.0)

        pan_syntax = check_map.get("identifier_syntax", {})
        # 1.0 if pass (or check not present/applicable), 0.0 if explicitly warning
        features["identifier_syntax_valid"] = 0.0 if pan_syntax.get("status") == "warning" else 1.0

        # -------------------------------------------------------------
        # 9. Bank Statement & Financial Arithmetic
        # -------------------------------------------------------------
        rb_check = check_map.get("bank_running_balance_math", {})
        rb_disc = float(rb_check.get("evidence", {}).get("total_discrepancies", 0) or 0)
        if rb_check.get("status") == "warning" and rb_disc == 0:
            rb_disc = 1.0
        features["bank_running_balance_discrepancies"] = float(rb_disc)

        id_check = check_map.get("bank_identity_consistency", {})
        features["bank_identity_conflict_flag"] = 1.0 if id_check.get("status") == "warning" else 0.0

        return features

    def extract_vector(self, checks: List[Dict[str, Any]]) -> np.ndarray:
        """Extracts the ordered NumPy feature vector."""
        feat_dict = self.extract_features(checks)
        return np.array([feat_dict[k] for k in self.FEATURE_NAMES], dtype=np.float32)


forensic_feature_extractor = ForensicFeatureExtractor()
