import cv2
import numpy as np
from PIL import Image
from pathlib import Path
from typing import Dict, Any, List, Optional
from backend.utils.logger import logger

class CopyMoveDetectorService:
    """
    Baseline Copy-Move Forgery Detection using OpenCV ORB feature matching.
    Identifies cloned or duplicated regions (e.g. copied stamps, duplicate digits, cloned signatures).
    """

    MAX_DIMENSION = 1800

    def detect(self, image_input: Any) -> Dict[str, Any]:
        try:
            if isinstance(image_input, (str, Path)):
                img = cv2.imread(str(image_input))
            elif isinstance(image_input, Image.Image):
                img = cv2.cvtColor(np.array(image_input), cv2.COLOR_RGB2BGR)
            elif isinstance(image_input, np.ndarray):
                img = image_input
            else:
                return {
                    "check": "copy_move_detection",
                    "status": "info",
                    "severity": "low",
                    "message": "Unsupported image format for copy-move detection.",
                    "evidence": {},
                }

            if img is None:
                return {
                    "check": "copy_move_detection",
                    "status": "info",
                    "severity": "low",
                    "message": "Could not read image for copy-move analysis.",
                    "evidence": {},
                }

            # Downsample if image is excessively large for speed
            h, w = img.shape[:2]
            if max(h, w) > self.MAX_DIMENSION:
                scale = self.MAX_DIMENSION / float(max(h, w))
                img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # 1. Detect ORB keypoints & descriptors
            orb = cv2.ORB_create(nfeatures=1200, fastThreshold=15)
            keypoints, descriptors = orb.detectAndCompute(gray, None)

            if descriptors is None or len(descriptors) < 20:
                return {
                    "check": "copy_move_detection",
                    "status": "pass",
                    "severity": "low",
                    "message": "No duplicated regions detected; keypoint density is low.",
                    "evidence": {"keypoints_found": len(keypoints) if keypoints else 0},
                }

            # 2. Match descriptors against themselves using BFMatcher
            bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
            # Find 3 nearest neighbors for each descriptor
            matches = bf.knnMatch(descriptors, descriptors, k=3)

            valid_cloned_pairs: List[Dict[str, Any]] = []
            displacement_vectors: List[Tuple[int, int]] = []

            for match_group in matches:
                if len(match_group) < 2:
                    continue

                # match_group[0] is self-match (distance == 0)
                # match_group[1] is the closest non-identical descriptor
                m = match_group[1]
                idx1, idx2 = m.queryIdx, m.trainIdx

                if idx1 == idx2:
                    continue

                pt1 = keypoints[idx1].pt
                pt2 = keypoints[idx2].pt

                # Calculate spatial Euclidean distance between the two keypoints
                spatial_dist = np.sqrt((pt1[0] - pt2[0])**2 + (pt1[1] - pt2[1])**2)

                # Filter: must be spatially distant (> 60px) to prevent local texture false positives
                # and have strong descriptor similarity (Hamming distance < 24)
                if spatial_dist > 60.0 and m.distance < 24:
                    dx = int(round(pt2[0] - pt1[0]))
                    dy = int(round(pt2[1] - pt1[1]))
                    displacement_vectors.append((dx, dy))
                    valid_cloned_pairs.append({
                        "pt1": [int(pt1[0]), int(pt1[1])],
                        "pt2": [int(pt2[0]), int(pt2[1])],
                        "hamming_distance": int(m.distance),
                        "spatial_distance": round(float(spatial_dist), 1),
                        "dx": dx,
                        "dy": dy,
                    })

            # 3. Cluster displacement vectors: true copy-move operations share identical displacement vectors
            # AND must form a cohesive 2D spatial region (not a 1D line of text characters)
            clustered_clones = 0
            if len(valid_cloned_pairs) >= 6:
                vector_bins: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
                for pair in valid_cloned_pairs:
                    bin_key = (pair["dx"] // 25, pair["dy"] // 25)
                    vector_bins.setdefault(bin_key, []).append(pair)

                for bin_key, pairs_in_bin in vector_bins.items():
                    if len(pairs_in_bin) >= 12:
                        pts1 = np.array([p["pt1"] for p in pairs_in_bin])
                        span_x = float(pts1[:, 0].max() - pts1[:, 0].min())
                        span_y = float(pts1[:, 1].max() - pts1[:, 1].min())
                        # 2D patch requirement (prevents font glyphs on 1D horizontal text lines from triggering)
                        if span_x >= 20.0 and span_y >= 20.0 and span_x < 500.0 and span_y < 500.0:
                            clustered_clones = max(clustered_clones, len(pairs_in_bin))

            # Evaluate verdict
            # A threshold of 25 ensures repeated typographical labels (like "Account", "Date") 
            # on successive lines do not trigger false positives, while cloned stamps, signatures, or photos are caught.
            if clustered_clones >= 45:
                status = "warning"
                severity = "high"
                message = f"Strong copy-move duplication evidence detected: {clustered_clones} matching 2D keypoint clusters."
            elif clustered_clones >= 25:
                status = "warning"
                severity = "medium"
                message = f"Possible duplicated region detected: {clustered_clones} matching 2D keypoint clusters."
            else:
                status = "pass"
                severity = "low"
                message = "No copy-move evidence detected."

            return {
                "check": "copy_move_detection",
                "status": status,
                "severity": severity,
                "message": message,
                "evidence": {
                    "candidate_matches": len(valid_cloned_pairs),
                    "clustered_vector_count": clustered_clones,
                    "total_keypoints": len(keypoints),
                },
            }
        except Exception as e:
            logger.error(f"Copy-move detection failed: {e}")
            return {
                "check": "copy_move_detection",
                "status": "info",
                "severity": "low",
                "message": "Copy-move detection could not be executed.",
                "evidence": {"error": str(e)},
            }

copy_move_detector = CopyMoveDetectorService()
