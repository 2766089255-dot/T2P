"""
OCR Service — Extracts text from handwritten/math images.

Backend priority:
  1. ocr.space  — free REST API, no key, no model download (~2s)
  2. easyocr    — local, offline, downloads model on first use (~100MB)

Layered design:
  Image bytes → OCR engine → extracted text → DeepSeek grades the math
"""
import logging
import io
import base64
from typing import Optional
from PIL import Image

from src.config import Config

logger = logging.getLogger(__name__)


class OCRService:
    """Optical character recognition for student handwritten submissions."""

    # Keep encoded uploads below the free plan's 1 MB source-file limit.
    MAX_FREE_IMAGE_BYTES = 950_000

    def __init__(self, api_key: Optional[str] = None, trust_env: Optional[bool] = None):
        self._reader = None        # easyocr reader (lazy)
        self._easyocr_available = None
        self.api_key = api_key or Config.OCR_SPACE_API_KEY
        self.api_url = Config.OCR_SPACE_URL
        self.engine = Config.OCR_SPACE_ENGINE
        self.language = Config.OCR_SPACE_LANGUAGE
        self.timeout = Config.OCR_SPACE_TIMEOUT
        self.trust_env = Config.OCR_SPACE_TRUST_ENV if trust_env is None else trust_env

    def _prepare_cloud_image(self, image_bytes: bytes) -> tuple[bytes, str]:
        """Validate an image and reduce large photos for the OCR.Space free tier."""
        if not image_bytes:
            raise ValueError("Image payload is empty")

        with Image.open(io.BytesIO(image_bytes)) as image:
            image.load()
            source_format = (image.format or "PNG").upper()
            mime_types = {
                "PNG": "image/png",
                "JPEG": "image/jpeg",
                "JPG": "image/jpeg",
                "GIF": "image/gif",
                "BMP": "image/bmp",
                "TIFF": "image/tiff",
            }

            if len(image_bytes) <= self.MAX_FREE_IMAGE_BYTES and source_format in mime_types:
                return image_bytes, mime_types[source_format]

            # Uploaded phone photos can exceed the free API limit. Re-encode at
            # progressively smaller sizes while keeping enough detail for OCR.
            working = image.convert("RGB")
            for max_dimension, quality in ((2200, 88), (1800, 80), (1400, 72), (1100, 65)):
                resized = working.copy()
                resized.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
                output = io.BytesIO()
                resized.save(output, format="JPEG", quality=quality, optimize=True)
                prepared = output.getvalue()
                if len(prepared) <= self.MAX_FREE_IMAGE_BYTES:
                    return prepared, "image/jpeg"

        raise ValueError("Image cannot be reduced below the OCR.Space free-plan limit")

    # ── ocr.space backend (primary — zero setup) ──────────────────────

    def _ocr_space(self, image_bytes: bytes) -> Optional[str]:
        """Send image to ocr.space free API, return extracted text."""
        try:
            import httpx

            prepared_bytes, mime_type = self._prepare_cloud_image(image_bytes)
            b64 = base64.b64encode(prepared_bytes).decode("ascii")
            with httpx.Client(
                timeout=httpx.Timeout(self.timeout),
                trust_env=self.trust_env,
            ) as client:
                resp = client.post(
                    self.api_url,
                    headers={"apikey": self.api_key},
                    data={
                        "base64Image": f"data:{mime_type};base64,{b64}",
                        "language": self.language,
                        "isOverlayRequired": "false",
                        "scale": "true",
                        "OCREngine": self.engine,
                    },
                )
            if resp.status_code != 200:
                logger.warning("OCR.Space returned HTTP %s", resp.status_code)
                return None

            data = resp.json()
            if data.get("IsErroredOnProcessing"):
                logger.warning("OCR.Space processing error: %s", data.get("ErrorMessage") or "unknown error")
                return None

            results = data.get("ParsedResults", [])
            if not results:
                return None

            first_result = results[0]
            if first_result.get("FileParseExitCode") not in (1, "1", None):
                logger.warning("OCR.Space could not parse the image: %s", first_result.get("ErrorMessage") or "unknown error")
                return None

            text = (first_result.get("ParsedText") or "").strip()
            if text:
                logger.info("OCR.Space extracted %d characters", len(text))
                return text
            return None

        except Exception as exc:
            logger.warning("OCR.Space request failed: %s", exc)
            return None

    # ── easyocr backend (fallback — local, offline) ───────────────────

    def _init_easyocr(self) -> bool:
        """Lazy-init easyocr. Returns True if ready."""
        if self._easyocr_available is not None:
            return self._easyocr_available
        try:
            import easyocr
            self._reader = easyocr.Reader(['en'], gpu=False, verbose=False)
            self._easyocr_available = True
            logger.info("OCR backend ready (easyocr — local)")
        except Exception as e:
            logger.info(f"easyocr unavailable ({e})")
            self._easyocr_available = False
        return self._easyocr_available

    def _easyocr_extract(self, image_bytes: bytes) -> Optional[str]:
        """Extract text using easyocr (local)."""
        if not self._init_easyocr():
            return None
        try:
            image = Image.open(io.BytesIO(image_bytes))
            if image.mode in ('RGBA', 'P'):
                image = image.convert('RGB')
            results = self._reader.readtext(image, detail=0)
            text = ' '.join(results).strip()
            if text:
                logger.info(f"OCR (easyocr): {text[:80]}...")
                return text
        except Exception as e:
            logger.warning(f"easyocr extraction failed: {e}")
        return None

    # ── public API ────────────────────────────────────────────────────

    def extract(self, image_bytes: bytes) -> Optional[str]:
        """
        Extract text from an image. Tries ocr.space first, then easyocr.

        Returns extracted text, or None if all backends fail.
        """
        # 1. Try ocr.space (fast, no setup)
        text = self._ocr_space(image_bytes)
        if text:
            return text

        # 2. Fall back to easyocr (local, offline)
        text = self._easyocr_extract(image_bytes)
        if text:
            return text

        logger.info("All OCR backends returned no text")
        return None
