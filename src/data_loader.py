"""
Golden Dataset Loader - Tutor Audit Enhanced Version (Supports global indexing and dynamic retrieval)
"""
import json
import random
from typing import Dict, List, Optional, Union
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class GoldenDataLoader:
    """
    Golden Dataset Loader
    1. Supports multi-level topic indexing and fuzzy matching
    2. Supports reverse retrieval of problems from historical generation results (for visual grading)
    """

    def __init__(self, data_path: str):
        """
        Initialize loader
        Args:
            data_path: Path to golden dataset JSON file
        """
        self.data_path = Path(data_path)
        self.dataset = None
        self.problems = []
        self.topics_map = {}  # Structure: { "Topic Name": [problem_dict, ...] }
        self.load()

    def load(self):
        """Load initial golden dataset"""
        try:
            if not self.data_path.exists():
                logger.error(f"Dataset file not found: {self.data_path}")
                return

            with open(self.data_path, 'r', encoding='utf-8') as f:
                self.dataset = json.load(f)

            # Extract problem list
            if isinstance(self.dataset, dict) and 'problems' in self.dataset:
                self.problems = self.dataset['problems']
            elif isinstance(self.dataset, list):
                self.problems = self.dataset
            else:
                self.problems = []

            # Rebuild topic index
            self._build_topic_map()

            logger.info(f"Initial dataset loaded successfully: {len(self.problems)} problems total, "
                        f"{len(self.topics_map)} available topic indices mapped")

        except Exception as e:
            logger.error(f"Failed to load dataset: {str(e)}")
            raise

    def _build_topic_map(self):
        """Build index by both main category and subcategory, and clean whitespace"""
        self.topics_map = {}
        for p in self.problems:
            main_topic = str(p.get('topic', 'unknown')).strip()
            sub_topic = str(p.get('sub_topic', '')).strip()

            # 1. Map to main category
            if main_topic not in self.topics_map:
                self.topics_map[main_topic] = []
            self.topics_map[main_topic].append(p)

            # 2. If subcategory exists and is different, also map to subcategory
            if sub_topic and sub_topic != main_topic:
                if sub_topic not in self.topics_map:
                    self.topics_map[sub_topic] = []
                self.topics_map[sub_topic].append(p)

    def find_problem_by_id(self, problem_id: str, output_dir: Optional[Path] = None) -> Optional[Dict]:
        """
        Core new feature: Global problem retrieval, supporting both problem_id and id fields.
        The grading endpoint uses this method to retrieve the problem's solution and scaffolding.

        Args:
            problem_id: Unique problem ID
            output_dir: Output directory for generated results (used to find non-seed problems)
        """
        # 1. First search in the in-memory golden problem bank
        for p in self.problems:
            if p.get('problem_id') == problem_id or p.get('id') == problem_id:
                return p

        # 2. If not found, try searching in the output directory for generated batch files or individual problem files
        if output_dir and output_dir.exists():
            logger.info(f"🔍 Dynamically searching for problem {problem_id} in output directory {output_dir}...")
            # Iterate through all .json files in the directory
            for json_file in output_dir.glob("*.json"):
                # Skip history summary file
                if json_file.name == "generation_history.json":
                    continue
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    # Case A: File itself is a problem dictionary, check problem_id or id
                    if isinstance(data, dict):
                        if data.get('problem_id') == problem_id or data.get('id') == problem_id:
                            logger.info(f"Problem archive recovered from individual problem file {json_file.name}")
                            return data

                    # Case B: File contains a problems list (batch file)
                    target_list = data.get('problems', []) if isinstance(data, dict) else data
                    if isinstance(target_list, list):
                        for p in target_list:
                            if isinstance(p, dict):
                                if p.get('problem_id') == problem_id or p.get('id') == problem_id:
                                    logger.info(f"✨ Problem archive recovered from historical batch {json_file.name}")
                                    return p
                except Exception as e:
                    logger.debug(f"Failed to read file {json_file.name}: {e}")
                    continue

        logger.warning(f"Unable to find problem data with ID {problem_id}, grading aborted.")
        return None

    def get_topics(self) -> List[str]:
        """Get all available topic names"""
        return list(self.topics_map.keys())

    def get_main_topics(self) -> List[str]:
        """Get unique main category topics"""
        main_topics = set()
        for p in self.problems:
            topic = p.get('topic')
            if topic:
                main_topics.add(topic.strip())
        return sorted(list(main_topics))

    def get_examples(self, topic: str, num_examples: int = 2) -> List[Dict]:
        """Get example problems (with fuzzy matching logic)"""
        search_key = topic.strip()
        examples = self.topics_map.get(search_key)

        if not examples:
            for existing_key in self.topics_map.keys():
                if search_key.lower() in existing_key.lower() or \
                   existing_key.lower() in search_key.lower():
                    examples = self.topics_map[existing_key]
                    break

        if not examples:
            return []

        sample_size = min(num_examples, len(examples))
        return random.sample(examples, sample_size)

    def format_example(self, problem: Dict) -> str:
        """Format as JSON string"""
        return json.dumps(problem, indent=2, ensure_ascii=False)