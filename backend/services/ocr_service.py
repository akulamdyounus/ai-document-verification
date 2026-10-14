import os
import re
from pathlib import Path
from typing import Optional, Union, List, Dict, Any, Tuple
from PIL import Image
import pytesseract
import cv2
import numpy as np

from backend.config import settings
from backend.utils.logger import logger


class BaseOCRService:
    def extract_text_from_image(self, image: Union[Image.Image, Path, str]) -> str:
        raise NotImplementedError

    def is_available(self) -> bool:
        raise NotImplementedError


class TesseractOCRService(BaseOCRService):
    """
    Advanced OCR Service utilizing OpenCV multi-variant preprocessing,
    Tesseract page segmentation mode (PSM) evaluation, and objective text quality scoring.
    """

    def __init__(self, tesseract_cmd: Optional[str] = None):
        self._cmd_path = self._resolve_tesseract_path(tesseract_cmd or settings.TESSERACT_PATH)
        if self._cmd_path:
            pytesseract.pytesseract.tesseract_cmd = str(self._cmd_path)
            logger.info(f"Tesseract OCR configured at: {self._cmd_path}")
        else:
            logger.warning("Tesseract executable not found. OCR features will be limited.")

    def _resolve_tesseract_path(self, configured_path: Optional[str]) -> Optional[Path]:
        """Resolves Tesseract binary location across Linux, macOS, and Windows."""
        import shutil

        # 1. Check explicitly configured path
        if configured_path:
            p = Path(configured_path)
            if p.exists() and p.is_file():
                return p

        # 2. Check system PATH (standard Linux / macOS / Windows PATH)
        system_tesseract = shutil.which("tesseract")
        if system_tesseract:
            return Path(system_tesseract)

        # 3. Standard Linux / Unix locations (e.g. Render, Docker, Ubuntu)
        unix_candidates = [
            Path("/usr/bin/tesseract"),
            Path("/usr/local/bin/tesseract"),
            Path("/opt/homebrew/bin/tesseract"),
        ]
        for path in unix_candidates:
            if path.exists() and path.is_file():
                return path

        # 4. Common Windows installation locations
        windows_candidates = [
            Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
            Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Tesseract-OCR" / "tesseract.exe",
        ]
        for path in windows_candidates:
            if path and path.exists() and path.is_file():
                return path

        return None

    def is_available(self) -> bool:
        if not self._cmd_path:
            return False
        try:
            version = pytesseract.get_tesseract_version()
            return bool(version)
        except Exception as e:
            logger.warning(f"Tesseract availability check failed: {e}")
            return False

    # --- OpenCV Preprocessing Techniques ---

    @staticmethod
    def deskew_image(cv_img: np.ndarray) -> Tuple[np.ndarray, float]:
        """
        Detects text line skew angle using minAreaRect on binary contours and rotates image
        if significant skew (1.0 to 45.0 degrees) is present.
        Returns: (deskewed_image, angle_applied)
        """
        try:
            if len(cv_img.shape) == 3:
                gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
            else:
                gray = cv_img.copy()

            # Invert threshold so text pixels are white
            thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
            coords = np.column_stack(np.where(thresh > 0))
            if len(coords) < 150:
                return cv_img, 0.0

            angle = cv2.minAreaRect(coords)[-1]
            if angle < -45:
                angle = -(90 + angle)
            elif angle > 45:
                angle = 90 - angle
            else:
                angle = -angle

            if 1.0 <= abs(angle) <= 45.0:
                h, w = cv_img.shape[:2]
                center = (w // 2, h // 2)
                m = cv2.getRotationMatrix2D(center, angle, 1.0)
                rotated = cv2.warpAffine(
                    cv_img, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
                )
                return rotated, round(float(angle), 2)
            return cv_img, 0.0
        except Exception as e:
            logger.debug(f"Deskew skipped: {e}")
            return cv_img, 0.0

    @staticmethod
    def upscale_image(cv_img: np.ndarray, target_min_dim: int = 1800) -> Tuple[np.ndarray, float]:
        """
        Upscales small documents / ID cards using bicubic interpolation
        to ensure fine text reaches optimal Tesseract OCR resolution (approx 300 DPI).
        """
        h, w = cv_img.shape[:2]
        max_dim = max(h, w)
        if max_dim < target_min_dim:
            scale = min(3.0, target_min_dim / max(max_dim, 1))
            new_w = int(w * scale)
            new_h = int(h * scale)
            scaled = cv2.resize(cv_img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
            return scaled, round(scale, 2)
        return cv_img, 1.0

    @staticmethod
    def enhance_contrast_and_sharpen(cv_img: np.ndarray) -> np.ndarray:
        """
        Applies unsharp Laplacian enhancement to crisp up character edges
        without destructively binarizing colored text.
        """
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
        sharpened = cv2.filter2D(cv_img, -1, kernel)
        return sharpened

    @staticmethod
    def apply_clahe(gray: np.ndarray, clip_limit: float = 2.0) -> np.ndarray:
        """
        Applies Contrast Limited Adaptive Histogram Equalization (CLAHE)
        to normalize local contrast across variable backgrounds and watermarks.
        """
        clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        # Subtle bilateral filtering to denoise while preserving crisp text boundaries
        denoised = cv2.bilateralFilter(enhanced, 5, 50, 50)
        return denoised

    @staticmethod
    def apply_adaptive_threshold(gray: np.ndarray) -> np.ndarray:
        """
        Applies adaptive Gaussian thresholding, robust against uneven lighting and gradients.
        """
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        eq = clahe.apply(gray)
        thresh = cv2.adaptiveThreshold(
            eq, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 21, 11
        )
        return thresh

    @staticmethod
    def apply_otsu_threshold(gray: np.ndarray) -> np.ndarray:
        """
        Standard Otsu thresholding after light Gaussian blur.
        """
        blur = cv2.GaussianBlur(gray, (3, 3), 0)
        thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        return thresh

    def generate_preprocessing_variants(
        self, cv_img: np.ndarray
    ) -> List[Tuple[str, np.ndarray, float]]:
        """
        Generates distinct, non-destructive preprocessing variants.
        Returns: list of (variant_name, image_array, deskew_angle)
        """
        deskewed, angle = self.deskew_image(cv_img)
        scaled, _ = self.upscale_image(deskewed)

        # 1. Enhanced Color (Preserves color nuance, prevents Otsu color destruction)
        v_color = self.enhance_contrast_and_sharpen(scaled)

        # Grayscale baseline
        if len(scaled.shape) == 3:
            gray = cv2.cvtColor(scaled, cv2.COLOR_BGR2GRAY)
        else:
            gray = scaled.copy()

        # 2. CLAHE with light bilateral denoise
        v_clahe = self.apply_clahe(gray)

        # 3. Adaptive Thresholding (local contrast)
        v_adapt = self.apply_adaptive_threshold(gray)

        # 4. Otsu Thresholding (bimodal)
        v_otsu = self.apply_otsu_threshold(gray)

        # 5. Raw scaled baseline
        v_raw = scaled

        return [
            ("enhanced_color", v_color, angle),
            ("clahe", v_clahe, angle),
            ("adaptive_thresh", v_adapt, angle),
            ("otsu_thresh", v_otsu, angle),
            ("raw_scaled", v_raw, angle),
        ]

    # --- Measurable Text Quality Scoring ---

    @staticmethod
    def score_text_quality(text: str, avg_conf: float = 0.0) -> float:
        """
        Computes an objective, measurable text quality score.
        Evaluates alphanumeric density, valid dictionary word ratio,
        structural label-value presence, date formats, and penalizes isolated lone symbols.
        """
        if not text or not text.strip():
            return 0.0

        words = text.split()
        if not words:
            return 0.0

        # Alphanumeric character count
        alnum_count = sum(c.isalnum() for c in text)

        # Valid words (at least 2 letters)
        valid_words = sum(1 for w in words if len(w) >= 2 and any(c.isalpha() for c in w))

        # Structured label-value lines (e.g. 'Name : Value' or 'DOB : 1990')
        line_pairs = len(re.findall(r"^[A-Za-z\s]{2,20}[:]\s*[A-Za-z0-9]", text, re.MULTILINE))

        # Dates present
        dates_count = len(re.findall(r"\b(?:\d{4}[/-]\d{1,2}[/-]\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b", text))

        # Key document domain terms
        keywords = [
            "licence", "license", "driving", "name", "birth", "dob", "address",
            "issue", "expiry", "validity", "valid", "union", "india", "pradesh",
            "account", "statement", "bank", "balance", "passport", "republic",
            "father", "holder", "number", "card"
        ]
        text_lower = text.lower()
        keyword_hits = sum(1 for kw in keywords if re.search(r"\b" + kw, text_lower))

        # Penalize lone symbols (e.g. isolated colons, semicolons, dashes)
        lone_symbols = sum(1 for w in words if w in [":", ";", "|", "-", "_", "/", "\\", ".", "::", ":::"])

        score = (
            (alnum_count * 0.8)
            + (valid_words * 3.5)
            + (line_pairs * 40.0)
            + (keyword_hits * 30.0)
            + (dates_count * 25.0)
            + (avg_conf * 1.5)
            - (lone_symbols * 20.0)
        )
        return round(float(score), 1)

    # --- Core OCR Processing ---

    def extract_text_with_diagnostics(
        self, image_input: Union[Image.Image, Path, str]
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Executes multi-variant, multi-PSM OCR pipeline.
        Returns: (best_extracted_text, diagnostics_dict)
        """
        if not self.is_available():
            raise RuntimeError(
                "Tesseract OCR is not installed or configured on the server. Please verify TESSERACT_PATH."
            )

        # Convert input to OpenCV BGR array
        try:
            if isinstance(image_input, (str, Path)):
                file_str = str(image_input)
                # cv2.imread doesn't always support non-ascii paths on Windows; use imdecode fallback
                cv_img = cv2.imdecode(np.fromfile(file_str, dtype=np.uint8), cv2.IMREAD_COLOR)
                if cv_img is None:
                    # Fallback to PIL
                    pil_img = Image.open(file_str).convert("RGB")
                    cv_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            elif isinstance(image_input, Image.Image):
                rgb_array = np.array(image_input.convert("RGB"))
                cv_img = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR)
            else:
                raise ValueError(f"Unsupported image input type: {type(image_input)}")
        except Exception as e:
            logger.error(f"Image loading error in OCR service: {e}")
            raise RuntimeError(f"Failed to load image for OCR: {e}")

        # Generate non-destructive preprocessing variants
        variants = self.generate_preprocessing_variants(cv_img)

        # Primary PSM modes to test:
        # PSM 6: Uniform text block (structured IDs, tables, driving licences)
        # PSM 3: Fully automatic (multi-block default)
        # PSM 11: Sparse text (scattered labels)
        psm_modes = [6, 3, 11]

        best_text = ""
        best_score = -9999.0
        best_diagnostics: Dict[str, Any] = {}
        tested_summary: List[Dict[str, Any]] = []

        base_config = "--oem 1 -c preserve_interword_spaces=1"

        for v_name, v_mat, deskew_angle in variants:
            for psm in psm_modes:
                cfg = f"{base_config} --psm {psm}"
                try:
                    data = pytesseract.image_to_data(
                        v_mat, config=cfg, lang="eng", output_type=pytesseract.Output.DICT
                    )
                    txt = pytesseract.image_to_string(v_mat, config=cfg, lang="eng")
                    
                    # Calculate average confidence
                    confs = [int(c) for c in data.get("conf", []) if str(c).strip() and int(c) >= 0]
                    avg_conf = (sum(confs) / len(confs)) if confs else 0.0

                    score = self.score_text_quality(txt, avg_conf)

                    candidate_info = {
                        "variant": v_name,
                        "psm": psm,
                        "score": score,
                        "confidence": round(avg_conf, 1),
                        "characters": len(txt),
                    }
                    tested_summary.append(candidate_info)

                    if score > best_score:
                        best_score = score
                        best_text = txt.strip()
                        best_diagnostics = {
                            "preprocessing_method": v_name,
                            "psm_used": psm,
                            "extracted_character_count": len(best_text),
                            "ocr_confidence": round(avg_conf, 1),
                            "quality_score": score,
                            "deskew_angle": deskew_angle,
                            "variants_evaluated": len(tested_summary),
                        }

                    # Fast-exit if we already have an exceptional candidate with high confidence & structure
                    if score >= 900.0 and len(txt) > 200:
                        break
                except Exception as iter_e:
                    logger.debug(f"OCR candidate {v_name} with PSM {psm} failed: {iter_e}")

            if best_score >= 900.0:
                break

        # Fallback if all candidates had zero score
        if not best_text:
            try:
                best_text = pytesseract.image_to_string(cv_img, lang="eng").strip()
                best_diagnostics = {
                    "preprocessing_method": "raw_fallback",
                    "psm_used": 3,
                    "extracted_character_count": len(best_text),
                    "ocr_confidence": 0.0,
                    "quality_score": 0.0,
                    "deskew_angle": 0.0,
                    "variants_evaluated": len(tested_summary),
                }
            except Exception as fb_e:
                logger.error(f"Fallback raw OCR also failed: {fb_e}")
                best_text = ""

        best_diagnostics["variants_tested_count"] = len(tested_summary)
        return best_text, best_diagnostics

    # --- Backwards Compatible APIs ---

    def preprocess_image(self, image: Image.Image) -> Image.Image:
        """
        Backwards-compatible preprocessing returning an enhanced PIL Image.
        Applies upscaling, contrast enhancement, and unsharp masking.
        """
        try:
            rgb_array = np.array(image.convert("RGB"))
            cv_img = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR)
            deskewed, _ = self.deskew_image(cv_img)
            scaled, _ = self.upscale_image(deskewed)
            enhanced = self.enhance_contrast_and_sharpen(scaled)
            rgb_out = cv2.cvtColor(enhanced, cv2.COLOR_BGR2RGB)
            return Image.fromarray(rgb_out)
        except Exception as e:
            logger.warning(f"Image preprocessing warning: {e}. Falling back to original.")
            return image

    def extract_text_from_image(self, image_input: Union[Image.Image, Path, str]) -> str:
        """Extracts text from a single image using multi-variant OCR pipeline."""
        text, _ = self.extract_text_with_diagnostics(image_input)
        return text

    def extract_text_from_images(self, images: List[Image.Image]) -> str:
        """Extracts and joins text across multiple image pages."""
        text, _ = self.extract_text_from_images_with_diagnostics(images)
        return text

    def extract_text_from_images_with_diagnostics(
        self, images: List[Image.Image]
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Extracts text across multiple pages with aggregated diagnostics.
        """
        page_texts = []
        page_diagnostics = []

        for idx, img in enumerate(images):
            try:
                p_text, p_diag = self.extract_text_with_diagnostics(img)
                if p_text:
                    page_texts.append(p_text)
                    page_diagnostics.append(p_diag)
            except Exception as e:
                logger.warning(f"Failed OCR on page {idx + 1}: {e}")

        full_text = "\n\n".join(page_texts).strip()

        # Aggregate diagnostics
        if page_diagnostics:
            avg_conf = sum(d.get("ocr_confidence", 0.0) for d in page_diagnostics) / len(page_diagnostics)
            primary_diag = {
                "preprocessing_method": page_diagnostics[0].get("preprocessing_method", "multi_page"),
                "psm_used": page_diagnostics[0].get("psm_used", 6),
                "extracted_character_count": len(full_text),
                "ocr_confidence": round(avg_conf, 1),
                "pages_processed": len(images),
                "pages_with_text": len(page_texts),
            }
        else:
            primary_diag = {
                "preprocessing_method": "none",
                "psm_used": 3,
                "extracted_character_count": len(full_text),
                "ocr_confidence": 0.0,
                "pages_processed": len(images),
                "pages_with_text": 0,
            }

        return full_text, primary_diag


ocr_service = TesseractOCRService()
