"""
AI Client — DeepSeek Edition (OpenAI-compatible API)
Supports: sync/async text generation, multimodal image review, 429 auto-retry.
"""
import logging
import time
import base64
import json
from typing import Optional, Union, List, Dict
from openai import OpenAI, AsyncOpenAI

from src.config import Config

logger = logging.getLogger(__name__)


class AIClient:
    """
    Unified AI client — powered by DeepSeek via OpenAI-compatible API.
    Supports text generation and multimodal image review.
    """

    def __init__(self):
        """Initialize DeepSeek client via OpenAI SDK"""
        self.api_key = Config.DEEPSEEK_API_KEY
        self.base_url = Config.DEEPSEEK_BASE_URL
        self.model_name = Config.DEEPSEEK_MODEL

        if not self.api_key:
            logger.error("DEEPSEEK_API_KEY is empty! Please set it in .env")
            raise RuntimeError("DEEPSEEK_API_KEY not configured")

        try:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
            self.async_client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
            logger.info(f"DeepSeek client initialized | Model: {self.model_name} | Base URL: {self.base_url}")
        except Exception as e:
            logger.error(f"DeepSeek client init failed: {e}")
            raise

    def _build_messages(self, prompt: str, image_bytes: Optional[bytes] = None,
                        mime_type: str = "image/jpeg") -> List[Dict]:
        """
        Build messages list in OpenAI-compatible format.

        NOTE: deepseek-chat currently does NOT support image_url content type.
        When an image is provided, we append a note to the prompt instead of
        sending the raw image bytes. (For future multimodal support, re-enable
        the image_url code path when DeepSeek adds vision API.)
        """
        if image_bytes and isinstance(image_bytes, bytes) and len(image_bytes) > 0:
            # DeepSeek workaround: describe the image instead of sending it
            prompt = (
                "[NOTE: The student submitted a handwritten/drawn answer via the signature pad. "
                "The image data is not directly viewable by this model. "
                "Please use the problem context and any text extracted by the frontend to evaluate "
                "the submission. If no text was extracted, note that the submission is visual-only "
                "and provide general guidance.]\n\n"
                + prompt
            )

        return [{"role": "user", "content": prompt}]

    def generate(self, prompt: str, image_bytes: Optional[bytes] = None,
                 mime_type: str = "image/jpeg",
                 response_mime_type: str = "application/json",
                 temperature: float = 0.5) -> Optional[str]:
        """
        Core generation method — calls DeepSeek chat completions API.

        Args:
            prompt: The text prompt
            image_bytes: Optional binary image data for multimodal review
            mime_type: MIME type of the image (default: image/jpeg)
            response_mime_type: Ignored (kept for backward compat; DeepSeek uses prompt-based JSON control)
            temperature: Generation temperature (0.0 - 2.0)
        """
        messages = self._build_messages(prompt, image_bytes, mime_type)

        for attempt in range(3):
            try:
                task_label = "Visual Audit" if image_bytes else "Text generation"
                logger.info(f"{task_label} | Request attempt {attempt + 1}/3...")

                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=16384,
                    top_p=0.95
                )

                if response and response.choices:
                    content = response.choices[0].message.content
                    if content:
                        return content
                    else:
                        logger.warning("Empty response content from DeepSeek")

                # Check for content filter / refusal
                if response.choices and response.choices[0].finish_reason == "content_filter":
                    logger.error("Response blocked by content filter")
                    return None

            except Exception as e:
                err_msg = str(e)
                # DeepSeek rate limiting / busy
                if "429" in err_msg or "rate_limit" in err_msg.lower() or "busy" in err_msg.lower():
                    if attempt < 2:
                        wait_time = 90
                        logger.warning(f"Rate limited (429/busy). Waiting {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                # Context length exceeded
                if "context_length" in err_msg.lower() or "maximum context" in err_msg.lower():
                    logger.error(f"Context length exceeded: {err_msg}")
                    return None

                if attempt < 2:
                    logger.warning(f"Temporary error: {err_msg}. Retrying in 5s...")
                    time.sleep(5)
                    continue
                else:
                    logger.error(f"All retries exhausted: {err_msg}")
                    raise e

        return None

    async def generate_async(self, prompt: str, image_bytes: Optional[bytes] = None,
                             mime_type: str = "image/jpeg",
                             temperature: float = 0.5) -> Optional[str]:
        """
        Async version of generate() — non-blocking API call for FastAPI endpoints.
        """
        messages = self._build_messages(prompt, image_bytes, mime_type)

        for attempt in range(3):
            try:
                task_label = "Visual Audit" if image_bytes else "Text generation"
                logger.info(f"Async {task_label} | Attempt {attempt + 1}/3...")

                response = await self.async_client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=16384,
                    top_p=0.95
                )

                if response and response.choices:
                    content = response.choices[0].message.content
                    if content:
                        return content

            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "rate_limit" in err_msg.lower():
                    if attempt < 2:
                        await __import__('asyncio').sleep(90)
                        continue
                if attempt < 2:
                    await __import__('asyncio').sleep(5)
                    continue
                else:
                    logger.error(f"Async all retries exhausted: {err_msg}")
                    raise e
        return None

    def mentor_review(self, student_work_image: Optional[bytes] = None,
                      problem_data: Dict = {},
                      is_exam_mode: bool = False,
                      student_text_answer: Optional[str] = None) -> str:
        """
        Intelligent tutor audit — supports image, text, or combined input.

        Args:
            student_work_image: Binary image data (handwritten work photo)
            problem_data: Problem metadata (statement, solution, scaffolding)
            is_exam_mode: Strict exam mode (no hints)
            student_text_answer: Multiple-choice or text answer submitted by student
        """
        scaffolding_info = (
            "Not available (exam mode prohibited prompt)"
            if is_exam_mode
            else problem_data.get('scaffolding')
        )

        # Build input description
        input_descriptions = []
        if student_work_image:
            input_descriptions.append("Handwritten answer photo")
        if student_text_answer:
            input_descriptions.append(f"Text answer (submitted: {student_text_answer})")

        input_type_desc = " + ".join(input_descriptions) if input_descriptions else "No content submitted"

        mode_instruction = (
            "[Mode: Strict Exam]\n- It is strictly prohibited to provide specific solutions.\n- Emphasize the logical discontinuity."
            if is_exam_mode
            else "[Mode: Inspirational Practice]\n- Use Socratic method to guide students to discover errors."
        )

        # Build option list for MCQ questions
        options = problem_data.get('options', {})
        correct_answer = problem_data.get('answer', '')
        options_text = ""
        if options:
            options_text = "\n".join([f"  {k}: {v}" for k, v in options.items()])
            options_text = f"\n- Options:\n{options_text}\n- Correct Answer: {correct_answer}"

        prompt = f"""
You are a professional calculus instructor. Please audit the submitted content of the students.
Submission Type: {input_type_desc}

{mode_instruction}

【Reference Benchmark】
- Problem Statement: {problem_data.get('problem_statement')}
- Standard Solution: {problem_data.get('solution')}{options_text}

【Specific Content Submitted by Student】
{student_text_answer if student_text_answer else "(See image content)"}

【Audit and Scoring Criteria — CRITICAL】
1. **Multiple Choice Question (MCQ) Logic** — IF the problem has options:
   - The student's submission is an OPTION LETTER (A/B/C/D). Compare it to the Correct Answer above.
   - If the student's letter MATCHES the Correct Answer → is_correct: true, logic_alignment_score: 100
   - If the student's letter does NOT match → is_correct: false, logic_alignment_score: 0
   - IMPORTANT: The student submitting just a letter IS VALID for MCQ. Grade it as MCQ.
2. **Calculation/Derivation Logic** — IF the problem has no options:
   - **Problem Consistency Check (CRITICAL)**: First verify the student is solving the SAME problem.
     If completely different → is_correct: false, logic_alignment_score: 0
   - For matching problems: compare the student's final answer to the standard solution.
   - Perform error diagnosis: locate calculation/concept/formula errors.
   - Check for missing key proof steps.
3. **Error Diagnosis**: Use Socratic guidance — ask students if they may have overlooked a variable
   when applying relevant formulas (e.g., chain rule, cosine theorem)

【OUTPUT FORMAT — RETURN ONLY RAW JSON, NO MARKDOWN WRAPPERS】
{{
    "is_correct": bool,
    "logic_alignment_score": int,
    "error_analysis": "If MCQ and correct: 'Option {correct_answer} is correct'. If wrong: 'Your option X is incorrect, correct is {correct_answer}'",
    "tutor_feedback": "For MCQ correct: affirm and briefly explain the principle. For wrong: guide step by step",
    "next_hint": "Guide for next thinking step"
}}
"""

        return self.generate(
            prompt=prompt,
            image_bytes=student_work_image,
            temperature=0.3
        )
