"""
Configuration file - Manages project paths, LLM provider settings, and generation control
"""
import os
import logging
from pathlib import Path
from dotenv import load_dotenv


# Define a new logger here so it doesn't depend on api_server
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()


class Config:
    """Global configuration class"""

    # --- Base path configuration ---
    # Path(__file__).resolve() -> D:\PycharmBase\T2P\src\config.py
    # .parent.parent -> D:\PycharmBase\T2P
    BASE_DIR = Path(__file__).resolve().parent.parent
    print(f"Project root: {BASE_DIR}")

    # --- Resource paths ---
    # Default points to D:\PycharmBase\T2P\data\golden_dataset_v2.json
    GOLDEN_DATASET_PATH = os.getenv("GOLDEN_DATASET_PATH", str(BASE_DIR / "data" / "golden_dataset_v3.json"))

    # Default points to D:\PycharmBase\T2P\output
    OUTPUT_DIR = os.getenv("OUTPUT_DIR", str(BASE_DIR / "output"))

    # Default points to D:\PycharmBase\T2P\logs\t2p_system.log
    LOG_FILE = os.getenv("LOG_FILE", str(BASE_DIR / "logs" / "t2p_system.log"))

    # --- LLM Provider: DeepSeek (OpenAI-compatible API) ---
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
    if not DEEPSEEK_API_KEY:
        logger.error("❌ DEEPSEEK_API_KEY not found in environment variables")

    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

    # --- Model generation control parameters ---
    DEFAULT_TEMPERATURE = float(os.getenv("DEFAULT_TEMPERATURE", 0.5))
    DEFAULT_MAX_TOKENS = int(os.getenv("DEFAULT_MAX_TOKENS", 16384))
    DEFAULT_TOP_P = float(os.getenv("DEFAULT_TOP_P", 0.95))

    # --- Runtime scheduling configuration ---
    BATCH_SIZE = int(os.getenv("BATCH_SIZE", 1))
    REQUEST_DELAY = int(os.getenv("REQUEST_DELAY", 30))

    # [Recommendation]: Considering 429 risk, retry count can be maintained at 3 or increased to 5
    MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))

    # --- Log level ---
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    @classmethod
    def ensure_dirs(cls):
        """Ensure necessary directories exist"""
        Path(cls.OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
        Path(cls.LOG_FILE).parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def reload(cls):
        """Re-read environment variables (supports runtime config changes)."""
        load_dotenv(override=True)
        cls.DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
        cls.DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        cls.DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        cls.GOLDEN_DATASET_PATH = os.getenv("GOLDEN_DATASET_PATH", str(cls.BASE_DIR / "data" / "golden_dataset_v3.json"))
        cls.OUTPUT_DIR = os.getenv("OUTPUT_DIR", str(cls.BASE_DIR / "output"))
        cls.LOG_FILE = os.getenv("LOG_FILE", str(cls.BASE_DIR / "logs" / "t2p_system.log"))
        cls.ENABLE_AI_REVIEW = os.getenv("ENABLE_AI_REVIEW", "true").lower() in ("true", "1", "yes")
        logger.info("Config reloaded from environment")


# Auto-initialize directories
Config.ensure_dirs()