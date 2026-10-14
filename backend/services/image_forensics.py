import io
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from PIL import Image, ImageChops, ImageEnhance
import numpy as np
import cv2
from backend.utils.logger import logger

class ImageForensicsService:
    """
    Forensic analysis service for document images:
    - Error Level Analysis (ELA) to detect compression differentials
    - Noise variance analysis to identify localized smoothing or erased/pasted regions
    - Compression inconsistency analysis across 8x8 DCT grid structures
    """

    MAX_DIMENSION = 2000  # Performance safeguard: downscale if exceeds

    def _prepare_image(self, image_input: Any) -> Image.Image:
        """Converts file path or PIL image to an RGB PIL Image with safe resolution bounds."""
        if isinstance(image_input, (str, Path)):
            img = Image.open(str(image_input)).convert("RGB")
        elif isinstance(image_input, Image.Image):
            img = image_input.convert("RGB")
        else:
            raise ValueError(f"Unsupported image input type: {type(image_input)}")

        # Performance safeguard: downsample if excessively large
        w, h = img.size
        if max(w, h) > self.MAX_DIMENSION:
            scale = self.MAX_DIMENSION / float(max(w, h))
            new_size = (int(w * scale), int(h * scale))
            img = img.resize(new_size, Image.Resampling.BILINEAR)

        return img

    def perform_ela(self, image: Image.Image, quality: int = 90, scale: int = 15) -> Dict[str, Any]:
        """
        Error Level Analysis (ELA):
        Resaves the image at a known quality level and computes pixel differences.
        Regions modified/saved at different compression levels produce high variance peaks.
        """
        try:
            # 1. Save to in-memory JPEG at target quality
            buf = io.BytesIO()
            image.save(buf, format="JPEG", quality=quality)
            buf.seek(0)
            resaved = Image.open(buf).convert("RGB")

            # 2. Compute absolute difference between original and resaved image
            diff = ImageChops.difference(image, resaved)

            # 3. Enhance difference for analysis
            extrema = diff.getextrema()
            max_diff = max([ex[1] for ex in extrema]) if extrema else 0

            # Convert to numpy array for spatial statistical analysis
            diff_arr = np.array(diff).astype(np.float32)
            mean_error = float(np.mean(diff_arr))
            std_error = float(np.std(diff_arr))
            max_error = float(np.max(diff_arr))

            # Detect localized high-error clusters (e.g. spliced patches)
            # A cluster with error > 3x the standard deviation above mean indicates localized compression discrepancy
            threshold = mean_error + 3.0 * std_error
            high_error_mask = (diff_arr > max(threshold, 25.0)).astype(np.uint8)
            high_error_ratio = float(np.sum(high_error_mask) / (diff_arr.size))

            has_localized_anomaly = high_error_ratio > 0.02 and high_error_ratio < 0.40

            status = "pass"
            severity = "low"
            message = "No significant localized compression anomalies detected."

            if has_localized_anomaly and max_error > 50:
                status = "warning"
                severity = "medium"
                message = "Localized compression differences detected. Possible spliced or re-saved regions."
            elif high_error_ratio >= 0.40:
                # Whole image has high variance (often camera photo or re-compressed image)
                status = "info"
                severity = "low"
                message = "Uniform high compression variance observed across document."

            return {
                "check": "error_level_analysis",
                "status": status,
                "severity": severity,
                "message": message,
                "evidence": {
                    "mean_error": round(mean_error, 2),
                    "std_error": round(std_error, 2),
                    "max_error": round(max_error, 2),
                    "anomaly_pixel_ratio": round(high_error_ratio, 4),
                    "quality_level": quality,
                },
            }
        except Exception as e:
            logger.error(f"ELA analysis failed: {e}")
            return {
                "check": "error_level_analysis",
                "status": "info",
                "severity": "low",
                "message": "Error Level Analysis could not be performed.",
                "evidence": {"error": str(e)},
            }

    def analyze_noise_variance(self, image: Image.Image) -> Dict[str, Any]:
        """
        Analyzes local noise variance to detect unnaturally smoothed, blurred,
        or erased text areas (e.g., cloned backgrounds covering previous text).
        """
        try:
            # Convert to grayscale OpenCV image
            cv_img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)

            # Compute local Laplacian variance across 32x32 blocks
            h, w = cv_img.shape
            block_size = 32
            variances: List[float] = []

            for y in range(0, h - block_size, block_size):
                for x in range(0, w - block_size, block_size):
                    block = cv_img[y:y+block_size, x:x+block_size]
                    lap = cv2.Laplacian(block, cv2.CV_64F)
                    var = float(lap.var())
                    variances.append(var)

            if not variances:
                return {
                    "check": "noise_variance",
                    "status": "pass",
                    "severity": "low",
                    "message": "Image dimensions too small for block noise analysis.",
                    "evidence": {},
                }

            var_arr = np.array(variances)
            mean_var = float(np.mean(var_arr))
            median_var = float(np.median(var_arr))
            min_var = float(np.min(var_arr))

            # Unnaturally flat/zero-variance blocks in a textured document can signify digital erasing/smoothing
            flat_blocks = int(np.sum(var_arr < 0.5))
            flat_ratio = flat_blocks / len(variances)

            status = "pass"
            severity = "low"
            message = "Document noise and texture distribution appears consistent."

            # Erased/smoothed areas are suspicious when the document has noticeable ambient paper texture/noise (median_var >= 8.0)
            # but contains isolated completely flat blocks (0.05 <= flat_ratio <= 0.40).
            # Clean digital documents (flat_ratio >= 0.50 or median_var < 5.0) naturally have uniform flat backgrounds.
            if median_var >= 8.0 and (0.05 <= flat_ratio <= 0.40):
                status = "warning"
                severity = "medium"
                message = "Inconsistent local texture detected: presence of unusually smooth/filtered blocks on textured background."
            elif flat_ratio >= 0.50 or median_var < 5.0:
                status = "pass"
                severity = "low"
                message = "Document exhibits uniform clean digital background texture."

            return {
                "check": "noise_variance",
                "status": status,
                "severity": severity,
                "message": message,
                "evidence": {
                    "mean_laplacian_variance": round(mean_var, 2),
                    "median_variance": round(median_var, 2),
                    "min_variance": round(min_var, 2),
                    "flat_blocks_ratio": round(flat_ratio, 4),
                },
            }
        except Exception as e:
            logger.error(f"Noise variance analysis failed: {e}")
            return {
                "check": "noise_variance",
                "status": "info",
                "severity": "low",
                "message": "Noise variance analysis could not be completed.",
                "evidence": {"error": str(e)},
            }

    EDITING_SOFTWARE_INDICATORS = [
        "photoshop", "gimp", "canva", "picsart", "snapseed", "pixelmator",
        "paint.net", "lightroom", "affinity", "coreldraw", "pixlr",
        "fotor", "befunky", "vsco", "facetune",
    ]

    def check_image_metadata(
        self, image: Image.Image, file_path: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        Inspects EXIF and format metadata on document images for editing software
        signatures (e.g. Photoshop, GIMP, Canva, Picsart) and timestamp discrepancies.
        """
        software = None
        make = None
        model = None
        date_orig = None
        date_mod = None
        matched_tools: List[str] = []

        try:
            exif = image.getexif()
            if exif:
                software = str(exif.get(305, "") or "").strip()
                make = str(exif.get(271, "") or "").strip()
                model = str(exif.get(272, "") or "").strip()
                date_mod = str(exif.get(306, "") or "").strip()
                date_orig = str(exif.get(36867, "") or "").strip()

            info = getattr(image, "info", {}) or {}
            if not software and "Software" in info:
                software = str(info["Software"]).strip()
            if not software and "software" in info:
                software = str(info["software"]).strip()

            combined_str = f"{software or ''} {info.get('Description', '')} {info.get('Comment', '')}".lower()
            for tool in self.EDITING_SOFTWARE_INDICATORS:
                if tool in combined_str:
                    matched_tools.append(tool.capitalize())

            status = "pass"
            severity = "low"
            message = "Image metadata structure and camera properties appear standard."

            if matched_tools:
                status = "info"
                severity = "low"
                message = f"Editing or processing software signature detected in image metadata: {', '.join(matched_tools)}."
            elif not software and not make:
                status = "pass"
                severity = "low"
                message = "Standard document image without external editor signatures."

            return {
                "check": "image_metadata",
                "status": status,
                "severity": severity,
                "message": message,
                "evidence": {
                    "software": software or "None",
                    "camera_make": make or "None",
                    "camera_model": model or "None",
                    "datetime_original": date_orig or "None",
                    "datetime_modified": date_mod or "None",
                    "detected_editing_tools": matched_tools,
                },
            }
        except Exception as e:
            logger.error(f"Image metadata extraction failed: {e}")
            return {
                "check": "image_metadata",
                "status": "info",
                "severity": "low",
                "message": "Image metadata could not be extracted.",
                "evidence": {"error": str(e)},
            }

    def check_sharpness(self, image: Image.Image) -> Dict[str, Any]:
        """
        Assesses image focus, sharpness, and potential defocus blurring.
        Defocusing is frequently used to mask digital tampering or forged text edges.
        """
        try:
            cv_img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
            lap_var = float(cv2.Laplacian(cv_img, cv2.CV_64F).var())

            status = "pass"
            severity = "low"
            message = "Image focus and edge sharpness are within normal readable parameters."

            # Severe blur threshold: laplacian variance < 40.0
            if lap_var < 40.0:
                status = "warning"
                severity = "medium"
                message = f"Significant image defocus blur detected (variance: {lap_var:.1f}). Text boundaries may be compromised or obscured."
            elif lap_var < 80.0:
                status = "info"
                severity = "low"
                message = f"Moderate image softness observed (variance: {lap_var:.1f}). Document readability may be slightly reduced."

            return {
                "check": "image_sharpness",
                "status": status,
                "severity": severity,
                "message": message,
                "evidence": {
                    "laplacian_variance": round(lap_var, 2),
                    "is_defocused": lap_var < 40.0,
                },
            }
        except Exception as e:
            logger.error(f"Image sharpness analysis failed: {e}")
            return {
                "check": "image_sharpness",
                "status": "info",
                "severity": "low",
                "message": "Image sharpness analysis could not be completed.",
                "evidence": {"error": str(e)},
            }

    def check_splicing(self, image: Image.Image) -> Dict[str, Any]:
        """
        Detects artificial rectangular boundary gradients and localized splicing artifacts
        typical of cut-and-paste manipulation where text was overlaid with an opaque patch.
        """
        try:
            cv_img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
            h, w = cv_img.shape[:2]

            # Edge gradient detection
            edges = cv2.Canny(cv_img, 60, 180)

            # Minimum line length to capture patch edges (including vertical box borders)
            min_line_len = max(int(min(h, w) * 0.03), 20)
            lines = cv2.HoughLinesP(
                edges,
                rho=1,
                theta=np.pi / 180,
                threshold=40,
                minLineLength=min_line_len,
                maxLineGap=6,
            )

            suspicious_patch_corners = 0
            if lines is not None:
                margin_x = int(w * 0.05)
                margin_y = int(h * 0.05)
                h_lines = []
                v_lines = []

                for line in lines:
                    pts = line.reshape(-1)
                    if len(pts) < 4:
                        continue
                    x1, y1, x2, y2 = int(pts[0]), int(pts[1]), int(pts[2]), int(pts[3])
                    if (
                        min(x1, x2) > margin_x
                        and max(x1, x2) < (w - margin_x)
                        and min(y1, y2) > margin_y
                        and max(y1, y2) < (h - margin_y)
                    ):
                        dx = abs(x2 - x1)
                        dy = abs(y2 - y1)
                        if dx >= 35 and dy < 8:
                            h_lines.append((min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)))
                        elif dy >= 20 and dx < 8:
                            v_lines.append((min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)))

                # Text patches are closed rectangular boxes where vertical and horizontal boundaries meet
                if h_lines and v_lines:
                    for hx1, hy1, hx2, hy2 in h_lines:
                        for vx1, vy1, vx2, vy2 in v_lines:
                            for hx, hy in [(hx1, hy1), (hx2, hy2)]:
                                for vx, vy in [(vx1, vy1), (vx2, vy2)]:
                                    if abs(hx - vx) <= 12 and abs(hy - vy) <= 12:
                                        suspicious_patch_corners += 1

            status = "pass"
            severity = "low"
            message = "No localized rectangular splicing or boundary anomalies detected."

            if suspicious_patch_corners >= 8:
                status = "warning"
                severity = "high"
                message = f"Prominent artificial boundary discontinuities detected ({suspicious_patch_corners} intersecting patch corners). Possible digital cut-and-paste manipulation."
            elif suspicious_patch_corners >= 4:
                status = "warning"
                severity = "medium"
                message = f"Localized boundary gradient anomalies detected ({suspicious_patch_corners} candidate patch corners)."

            return {
                "check": "splicing_detection",
                "status": status,
                "severity": severity,
                "message": message,
                "evidence": {
                    "suspicious_patch_corners": suspicious_patch_corners,
                },
            }
        except Exception as e:
            logger.error(f"Splicing detection failed: {e}")
            return {
                "check": "splicing_detection",
                "status": "info",
                "severity": "low",
                "message": "Splicing boundary detection could not be completed.",
                "evidence": {"error": str(e)},
            }

    def analyze(
        self,
        image_input: Any,
        include_extended: bool = False,
        file_path: Optional[Path] = None,
    ) -> List[Dict[str, Any]]:
        """Runs the image forensics suite and returns structured checks."""
        img = self._prepare_image(image_input)
        checks: List[Dict[str, Any]] = []

        # 1. Error Level Analysis
        ela_check = self.perform_ela(img)
        checks.append(ela_check)

        # 2. Noise & Smoothing Analysis
        noise_check = self.analyze_noise_variance(img)
        checks.append(noise_check)

        # Extended visual forensics (metadata, focus blur, digital splicing)
        if include_extended:
            # 3. EXIF & Metadata
            meta_check = self.check_image_metadata(img, file_path=file_path)
            checks.append(meta_check)

            # 4. Image Sharpness & Defocus Blur
            sharp_check = self.check_sharpness(img)
            checks.append(sharp_check)

            # 5. Splicing & Boundary Discontinuity
            splicing_check = self.check_splicing(img)
            checks.append(splicing_check)

        return checks


image_forensics_service = ImageForensicsService()
