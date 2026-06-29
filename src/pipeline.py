"""
GenerationPipeline — Clean separation of generation stages.

Refactored from ProblemGenerator._generate_with_retry_logic().
Each stage is independently testable.
"""
import time
import random
import logging
from typing import List, Dict, Optional

from src.config import Config
from src.prompt_builder import PromptBuilder
from src.postprocessor import PostProcessor
from src.evaluator import QualityEvaluator

logger = logging.getLogger(__name__)


class GenerationPipeline:
    """
    Encapsulates the problem generation pipeline as explicit stages:
      1. Topic sampling
      2. Prompt building
      3. API generation (via external client)
      4. Post-processing
      5. Quality evaluation
      6. Self-healing retry loop
    """

    def __init__(self, data_loader, ai_client,
                 evaluator: QualityEvaluator = None,
                 postprocessor: PostProcessor = None):
        self.data_loader = data_loader
        self.ai_client = ai_client
        self.prompt_builder = PromptBuilder(data_loader)
        self.postprocessor = postprocessor or PostProcessor()
        self.evaluator = evaluator or QualityEvaluator(data_loader, ai_client=ai_client)

    def sample_topics(self, topics: List[str], mode: str) -> List[str]:
        """Dynamic topic sampling strategy."""
        if not topics:
            return []
        if mode == "drill":
            return topics[:1]  # Single knowledge point

        # Exam mode: core anchor + 1-2 related topics
        main_topic = topics[0]
        others = [t for t in topics[1:] if t != main_topic]
        related_count = random.randint(1, min(2, len(others))) if others else 0
        related = random.sample(others, related_count) if others else []
        return [main_topic] + related

    def run(self, topics: List[str], mode: str = "drill",
            difficulty: int = 3, temperature: float = 0.5,
            question_type: str = "mcq") -> Optional[Dict]:
        """
        Execute the full pipeline with self-healing retry loop.
        Returns a validated problem dict, or None if exhausted.
        """
        max_retries = Config.MAX_RETRIES
        current_feedback = ""
        active_topics = self.sample_topics(topics, mode)

        for attempt in range(max_retries):
            try:
                logger.info(f"Attempt {attempt + 1}/{max_retries} | Mode: {mode} | Core: {active_topics[0]}")

                # Stage 1: Build prompt
                fusion_instruction = ""
                if mode == "exam" and len(active_topics) > 1:
                    fusion_instruction = (
                        f"| COMPOSITE TASK: Integrate {active_topics[1:]} "
                        f"into the context of {active_topics[0]}."
                    )

                prompt = self.prompt_builder.build_prompt(
                    topics=active_topics,
                    mode=mode,
                    difficulty=difficulty,
                    feedback=current_feedback + fusion_instruction,
                    question_type=question_type
                )

                # Stage 2: API call
                temp = temperature or (0.8 if mode == "exam" else 0.5)
                response = self.ai_client.generate(prompt, temperature=temp)
                if not response:
                    continue

                # Stage 3: Parse & clean
                problem = self.postprocessor.process(response, active_topics[0])
                if not problem:
                    logger.warning("JSON parsing failed, retrying...")
                    continue

                # Stage 4: Fill metadata
                from datetime import datetime
                problem.update({
                    'generated_at': datetime.now().isoformat(),
                    'mode': mode,
                    'question_type': question_type,
                    'target_difficulty': difficulty,
                    'core_topic': active_topics[0],
                    'integrated_topics': active_topics
                })

                # Stage 5: Quality evaluation
                result = self.evaluator.evaluate(problem, active_topics)
                problem['evaluation'] = result.__dict__

                if result.passed:
                    logger.info(f"✅ Generation passed (Score: {result.score})")
                    return problem
                else:
                    current_feedback = f"Previous Attempt Flaw: {result.ai_feedback}"
                    logger.warning(f"⚠️ Quality failed: {result.ai_feedback}")
                    time.sleep(2 * (attempt + 1))

            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "rate_limit" in err_msg.lower():
                    wait_sec = 30 * (attempt + 1)
                    logger.error(f"Rate limited (429). Waiting {wait_sec}s...")
                    time.sleep(wait_sec)
                else:
                    logger.error(f"Generation error: {err_msg}")
                    time.sleep(5)

        return None
