"""
AppCore — Centralized dependency container (singleton).

Why: Previously AIClient, DataLoader, Generator, Evaluator were created
ad-hoc in BatchGenerator with fallback constructors. This makes dependencies
explicit, ensures single AIClient instance, and simplifies testing.
"""
import logging
from typing import Optional

from src.config import Config
from src.data_loader import GoldenDataLoader
from src.ai_client import AIClient
from src.generator import ProblemGenerator
from src.evaluator import QualityEvaluator
from src.postprocessor import PostProcessor

logger = logging.getLogger(__name__)


class AppCore:
    """Application-level dependency container (singleton)."""

    _instance: Optional["AppCore"] = None

    def __init__(self):
        logger.info("Initializing AppCore...")

        # ---- Foundation ----
        self.config = Config  # Config is still class-level; see config.py

        # ---- Data ----
        self.data_loader = GoldenDataLoader(self.config.GOLDEN_DATASET_PATH)

        # ---- AI Client (single shared instance) ----
        self.ai_client = AIClient()

        # ---- Shared postprocessor ----
        self.postprocessor = PostProcessor()

        # ---- Domain services ----
        self.evaluator = QualityEvaluator(
            golden_data_loader=self.data_loader,
            ai_client=self.ai_client
        )
        self.generator = ProblemGenerator(
            data_loader=self.data_loader,
            ai_client=self.ai_client,
            evaluator=self.evaluator,
            postprocessor=self.postprocessor
        )

        logger.info("AppCore ready | topics=%d | model=%s",
                     len(self.data_loader.problems), self.config.DEEPSEEK_MODEL)

    @classmethod
    def get(cls) -> "AppCore":
        """Return the singleton instance, creating it lazily on first call."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls):
        """Reset singleton (useful for testing)."""
        cls._instance = None
