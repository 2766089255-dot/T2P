"""
Core Generation Logic - T2P System (Pipeline Refactored Version)
Uses GenerationPipeline for clean separation of prompt/API/postprocess/evaluate stages.
"""
import time
import logging
from typing import List, Dict, Optional, Any

from src.config import Config
from src.ai_client import AIClient
from src.pipeline import GenerationPipeline

logger = logging.getLogger(__name__)


class ProblemGenerator:
    """Problem generator — delegates to GenerationPipeline; handles batch orchestration."""

    def __init__(self, data_loader, ai_client=None, evaluator=None, postprocessor=None):
        """Initialize generator with explicit dependencies (prefer AppCore injection)."""
        self.data_loader = data_loader
        self.ai_client = ai_client or AIClient()

        # Shared components from AppCore (or fallback)
        self.pipeline = GenerationPipeline(
            data_loader=data_loader,
            ai_client=self.ai_client,
            evaluator=evaluator,
            postprocessor=postprocessor
        )

    def generate_one(self, topics: List[str], mode: str = "drill",
                     difficulty: int = 3, temperature: float = None,
                     question_type: str = "mcq") -> Optional[Dict]:
        """Generate a single problem via the pipeline."""
        return self.pipeline.run(
            topics=topics,
            mode=mode,
            difficulty=difficulty,
            temperature=temperature or (0.8 if mode == "exam" else 0.5),
            question_type=question_type
        )

    def generate_batch(self, topics: List[str], num: int = 5,
                       mode: str = "drill", difficulty: int = 3,
                       question_type: str = "mcq") -> List[Dict]:
        """Execute batch task logic"""
        batch_result = []
        logger.info(f"===== Batch task started | Mode: {mode.upper()} | Target count: {num} =====")

        for i in range(num):
            logger.info(f"--- Progress: {i+1}/{num} ---")

            # Dynamically fine-tune temperature for each generation to increase problem diversity
            dynamic_temp = Config.DEFAULT_TEMPERATURE + (i * 0.05) % 0.2

            # Note: In Exam mode, topics[0] serves as anchor, subsequent generate_one will auto-handle fusion
            problem = self.generate_one(
                topics=topics,
                mode=mode,
                difficulty=difficulty,
                temperature=dynamic_temp,
                question_type=question_type
            )

            if problem:
                batch_result.append(problem)

            # Rate control: brief cooldown between problems
            if i < num - 1:
                delay = 2 if mode == "exam" else 1
                logger.info(f"Cooling down ({delay}s)...")
                time.sleep(delay)

        # Semantic deduplication after batch completion
        if len(batch_result) > 1:
            logger.info("Running batch semantic deduplication...")
            unique_problems = self.postprocessor.deduplicate(batch_result)
            return unique_problems

        return batch_result