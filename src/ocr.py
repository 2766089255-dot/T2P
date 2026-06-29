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

logger = logging.getLogger(__name__)


class OCRService:
    """Optical character recognition for student handwritten submissions."""

    # ocr.space free tier: 25k requests/month, no API key needed
    OCR_SPACE_URL = "https://api.ocr.space/parse/image"

    def __init__(self):
        self._reader = None        # easyocr reader (lazy)
        self._easyocr_available = None

    # ── ocr.space backend (primary — zero setup) ──────────────────────

    def _ocr_space(self, image_bytes: bytes) -> Optional[str]:
        """Send image to ocr.space free API, return extracted text."""
        try:
            import httpx

            b64 = base64.b64encode(image_bytes).decode("utf-8")
            resp = httpx.post(
                self.OCR_SPACE_URL,
                data={
                    "apikey": "helloworld",  # ocr.space free tier key
                    "base64Image": f"data:image/png;base64,{b64}",
                    "language": "eng",
                    "isOverlayRequired": "false",
                    "scale": "true",
                    "OCREngine": "2",
                },
                timeout=httpx.Timeout(15.0),
            )
            if resp.status_code != 200:
                logger.warning(f"ocr.space returned {resp.status_code}")
                return None

            data = resp.json()
            results = data.get("ParsedResults", [])
            if not results:
                return None

            text = results[0].get("ParsedText", "").strip()
            if text:
                logger.info(f"OCR (ocr.space): {text[:80]}...")
                return text
            return None

        except Exception as e:
            logger.warning(f"ocr.space request failed: {e}")
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
