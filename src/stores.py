"""
ProgressStore — Abstract storage backend for user learning progress.

Supports: JSON file (default), ready for SQLite/Redis extension.
"""
from abc import ABC, abstractmethod
from typing import Dict
from pathlib import Path
import json
import logging
import hashlib

logger = logging.getLogger(__name__)


class ProgressStore(ABC):
    """Abstract interface for user progress persistence."""

    @abstractmethod
    def load(self, user_id: str) -> Dict:
        """Load progress data for a user. Returns empty dict if not found."""
        ...

    @abstractmethod
    def save(self, user_id: str, data: Dict):
        """Save progress data for a user."""
        ...


class JSONFileStore(ProgressStore):
    """JSON-file-based progress storage (current default)."""

    def __init__(self, data_dir: str = "data/users"):
        self.data_dir = Path(data_dir).resolve()

    def _path(self, user_id: str) -> Path:
        normalized_id = str(user_id).strip()
        if not normalized_id:
            raise ValueError("user_id must not be empty")
        if len(normalized_id) > 128:
            raise ValueError("user_id must be 128 characters or fewer")

        # Never place user-controlled text in a filesystem path. Besides blocking
        # path traversal, the digest avoids leaking usernames in directory listings.
        digest = hashlib.sha256(normalized_id.encode("utf-8")).hexdigest()[:32]
        return self.data_dir / f"user_{digest}_progress.json"

    def load(self, user_id: str) -> Dict:
        path = self._path(user_id)
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read progress for {user_id}: {e}")
        return {}

    def save(self, user_id: str, data: Dict):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        path = self._path(user_id)
        temporary_path = path.with_suffix(".tmp")
        with open(temporary_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        temporary_path.replace(path)
