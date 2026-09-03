"""
GradingService — Extracted from api_server.py.

Handles: problem lookup → AI audit → score calibration → structured result.
Keeps HTTP concerns out of business logic.
"""
import base64
import json
import logging
from pathlib import Path
from typing import Dict, Optional

from src.core import AppCore
from src.data_loader import GoldenDataLoader
from src.ai_client import AIClient
from src.ocr import OCRService

logger = logging.getLogger(__name__)


class GradingService:
    """Intelligent grading business logic — framework-agnostic."""

    def __init__(self, data_loader: GoldenDataLoader = None, ai_client: AIClient = None):
        core = AppCore.get()
        self.data_loader = data_loader or core.data_loader
        self.ai_client = ai_client or core.ai_client
        self.ocr = OCRService()

    def _parse_student_input(self, raw_input: str) -> tuple:
        """
        Parse student input. Image submissions are OCR'd to text.
        Returns (ocr_text, text_answer).
        """
        image_bytes = None
        text_answer = None

        if raw_input and "base64" in raw_input and len(raw_input) > 500:
            # Image submission — try OCR
            try:
                base64_str = raw_input.split(",")[1] if "," in raw_input else raw_input
                image_bytes = base64.b64decode(base64_str.strip())
                logger.info("Image submission detected, running OCR...")
                ocr_text = self.ocr.extract(image_bytes)
                if ocr_text:
                    text_answer = ocr_text
                    logger.info("OCR completed successfully")
                else:
                    logger.info("OCR returned no text — using visual submission note")
            except Exception as e:
                logger.warning(f"Image decode/OCR failed: {e}")
        elif raw_input and len(raw_input) < 500:
            # Text answer (MCQ option or short text)
            text_answer = raw_input.strip()
            logger.info("Text answer received")
        else:
            text_answer = raw_input

        return image_bytes, text_answer

    def _calibrate_score(self, is_correct: bool, raw_score: int, is_text_mcq: bool) -> int:
        """
        Score calibration logic (formerly inline in api_server.py).

        Rules:
        - MCQ text: correct → 100, incorrect → cap at 30
        - Handwritten image: correct < 60 → boost to 80, else keep raw
        """
        try:
            raw_score = int(raw_score)
        except (TypeError, ValueError):
            raw_score = 0
        raw_score = max(0, min(100, raw_score))

        if is_text_mcq:
            if is_correct:
                return 100
            else:
                return min(raw_score, 30) if raw_score > 30 else raw_score
        else:
            if is_correct and raw_score < 60:
                return 80
            return raw_score

    def audit(self, problem_id: str, student_input: str,
              is_exam_mode: bool = False) -> Dict:
        """
        Main audit entry point.

        Args:
            problem_id: ID of the target problem
            student_input: base64 image string OR plain text answer (A/B/C/D or text)
            is_exam_mode: Strict exam mode

        Returns:
            {
                "success": bool,
                "is_correct": bool,
                "logic_alignment_score": int,
                "error_analysis": str,
                "tutor_feedback": str,
                "next_hint": str,
                "ocr_text": str
            }
        """
        # 1. Parse input type
        image_bytes, text_answer = self._parse_student_input(student_input)

        # 2. Find problem data
        problem = self.data_loader.find_problem_by_id(
            problem_id=problem_id,
            output_dir=Path(AppCore.get().config.OUTPUT_DIR)
        )
        if not problem:
            return {"success": False, "error": f"Problem ID '{problem_id}' not found"}

        # 3. Call AI audit
        raw_review = self.ai_client.mentor_review(
            student_work_image=image_bytes,
            student_text_answer=text_answer,
            problem_data=problem,
            is_exam_mode=is_exam_mode
        )

        # 4. Parse AI response
        if not raw_review:
            return {"success": False, "error": "AI grading returned an empty response"}

        try:
            cleaned = raw_review.strip().replace("```json", "").replace("```", "").strip()
            review_json = json.loads(cleaned)
        except Exception as e:
            logger.error(f"JSON parsing failed: {e}")
            review_json = {}

        # 5. Score calibration
        is_correct = review_json.get("is_correct", False)
        raw_score = review_json.get("logic_alignment_score", 0)
        is_text_mcq = bool(problem.get("options")) and image_bytes is None and bool(text_answer)
        final_score = self._calibrate_score(is_correct, raw_score, is_text_mcq)

        return {
            "success": True,
            "is_correct": is_correct,
            "logic_alignment_score": final_score,
            "error_analysis": review_json.get("error_analysis", "Analysis complete"),
            "tutor_feedback": review_json.get("tutor_feedback", ""),
            "next_hint": review_json.get("next_hint", ""),
            "ocr_text": text_answer if text_answer else "Extracted from image"
        }
