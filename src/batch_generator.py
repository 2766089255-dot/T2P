"""
Batch Generator - Intelligent Orchestrator (V4.0.1 Integrated Version)
Optimizations:
1. Adapted to deep fusion problem generation mode: Changed Exam mode from full exam papers to multiple comprehensive problems.
2. Introduced intra-batch anchor rotation mechanism: Ensures generation coverage for multi-knowledge-point requests.
3. Enhanced physical cooldown: Explicitly avoids 429 quota limits.
4. Supports question_type parameter passing, enabling question type selection to take effect.
"""
import json
import os
import logging
import time
from typing import List, Dict, Optional, Any
from datetime import datetime
from pathlib import Path

# Import business modules
from src.config import Config
from src.core import AppCore

logger = logging.getLogger(__name__)

class BatchGenerator:
    """Batch generation and audit scheduler — uses shared AppCore instances."""

    def __init__(self, output_dir: str = None):
        """Initialize the scheduler with shared core dependencies."""
        core = AppCore.get()
        self.output_dir = Path(output_dir or Config.OUTPUT_DIR)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Shared instances from AppCore
        self.data_loader = core.data_loader
        self.ai_client = core.ai_client
        self.generator = core.generator

        # BatchGenerator-owned: generation history
        self.history_file = self.output_dir / "generation_history.json"
        self.history = self._load_history()

    def _load_history(self) -> Dict:
        """Load generation history summary"""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict) and 'batches' in data:
                        return data
            except Exception as e:
                logger.warning(f"Failed to read history file: {e}")
        return {'batches': []}

    def _save_history(self):
        """Save generation history summary"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save history file: {e}")

    def generate(self, topics: List[str] = None, num: int = 5,
                 mode: str = "drill", difficulty: int = 3,
                 question_type: str = "calculation",   # New question type parameter
                 batch_name: str = None) -> Dict:
        """
        Execute intelligent problem generation pipeline
        """
        if not topics:
            topics = self.data_loader.get_main_topics()

        logger.info(f"Task started | Mode: {mode.upper()} | Target count: {num} | Question type: {question_type} | Core pool: {topics}")

        final_problems = []

        # --- Core scheduling logic ---
        for i in range(num):
            logger.info(f"--- Processing problem {i+1}/{num} ---")

            # Dynamically adjust knowledge point arrangement for current task
            # In Exam mode, rotate the first element as the "core anchor" for each iteration
            if mode == "exam" and len(topics) > 1:
                current_topics = [topics[i % len(topics)]] + [t for t in topics if t != topics[i % len(topics)]]
            else:
                current_topics = topics

            # Dynamic temperature fine-tuning
            temp = Config.DEFAULT_TEMPERATURE + (i * 0.05) % 0.3

            # Call generator
            prob = self.generator.generate_one(
                topics=current_topics,
                mode=mode,
                difficulty=difficulty,
                temperature=temp,
                question_type=question_type   # Pass question type
            )

            if prob:
                final_problems.append(prob)

            # --- Brief cooldown between requests ---
            if i < num - 1:
                delay = 2 if mode == "exam" else 1
                logger.info(f"Physical cooldown, waiting {delay} seconds before continuing...")
                time.sleep(delay)

        # --- Post-processing: Semantic deduplication ---
        if final_problems and len(final_problems) > 1:
            original_count = len(final_problems)
            final_problems = self.generator.postprocessor.deduplicate(final_problems)
            if len(final_problems) < original_count:
                logger.info(f"Semantic deduplication engine filtered {original_count - len(final_problems)} highly similar problems")

        # Build batch details
        batch_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        batch_result = {
            'batch_id': batch_id,
            'batch_name': batch_name or f"{mode}_{batch_id[-6:]}",
            'mode': mode,
            'question_type': question_type,   # Record question type
            'generated_at': datetime.now().isoformat(),
            'target_topics': topics,
            'difficulty_setting': difficulty,
            'total_generated': len(final_problems),
            'problems': final_problems
        }

        # Persist results to storage
        output_file = self.output_dir / f"{batch_id}.json"
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(batch_result, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save batch file: {e}")

        # Update summary history
        self.history['batches'].append({
            'batch_id': batch_id,
            'mode': mode,
            'topics': topics,
            'total_generated': len(final_problems),
            'generated_at': batch_result['generated_at']
        })
        self._save_history()

        return batch_result

    def review_student_submission(self, problem_id: str, image_path: str, is_exam_mode: bool = False) -> Dict:
        """Intelligent tutor review interface (maintained as-is)"""
        problem_data = None
        for p in self.data_loader.problems:
            if p.get('problem_id') == problem_id:
                problem_data = p
                break

        if not problem_data:
            logger.error(f"Audit aborted: Could not find reference answer for ID {problem_id} in dataset")
            return {"error": "Target problem data missing from loader."}

        try:
            with open(image_path, "rb") as f:
                image_bytes = f.read()
        except Exception as e:
            logger.error(f"Image read failed: {e}")
            return {"error": f"Image read error: {str(e)}"}

        logger.info(f"Starting AI tutor audit | Problem: {problem_id}")
        raw_review = self.ai_client.mentor_review(
            student_work_image=image_bytes,
            problem_data=problem_data,
            is_exam_mode=is_exam_mode
        )

        try:
            cleaned_review = raw_review.strip().replace("```json", "").replace("```", "")
            return json.loads(cleaned_review)
        except json.JSONDecodeError:
            return {"raw_ai_feedback": raw_review}

    def get_statistics(self) -> Dict:
        """Get system runtime statistics summary (enhanced version)"""
        all_batches = self.history.get('batches', [])
        stats = {
            'total_batches': len(all_batches),
            'total_problems': sum(b.get('total_generated', 0) for b in all_batches),
            'mode_distribution': {
                'drill': len([b for b in all_batches if b.get('mode') == 'drill']),
                'exam': len([b for b in all_batches if b.get('mode') == 'exam'])
            },
            'performance': { 'avg_quality_score': 0.0 }
        }

        scores = []
        for batch in all_batches:
            batch_file = self.output_dir / f"{batch['batch_id']}.json"
            if batch_file.exists():
                try:
                    with open(batch_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        for p in data.get('problems', []):
                            s = p.get('evaluation', {}).get('score')
                            if s is not None: scores.append(float(s))
                except (json.JSONDecodeError, KeyError, TypeError):
                    continue

        if scores:
            stats['performance']['avg_quality_score'] = round(sum(scores) / len(scores), 2)
        return stats