import json
import time
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import matplotlib.pyplot as plt
import numpy as np
import logging

from src.stores import ProgressStore, JSONFileStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class UserSession:
    """
    UserSession: manages user learning lifecycle with pluggable storage backend.
    Core features: learning path navigation, level progression, time tracking,
    persistent storage, and learning analytics chart generation.
    """

    def __init__(self, user_id: str, store: ProgressStore = None):
        self.user_id = user_id
        base_path = Path(__file__).resolve().parent.parent
        self.store = store or JSONFileStore(data_dir=str(base_path / "data" / "users"))

        # --- Core modification: Dynamically load V3 dataset ---
        # Prioritize environment variable, otherwise read v3 version from data directory
        env_path = os.getenv("GOLDEN_DATASET_PATH")
        dataset_path = Path(env_path) if env_path else base_path / "data" / "golden_dataset_v3.json"

        logger.info(f"📅 Loading Roadmap based on dataset: {dataset_path.name}")
        self.roadmap = self._get_topics_from_dataset(dataset_path)

        self.progress = self._load_progress()
        self.session_start_time = None

    def _get_topics_from_dataset(self, path: Path) -> List[str]:
        """Dynamically extract all topics from V3 dataset, preserving original order of appearance"""
        try:
            if not path.exists():
                raise FileNotFoundError(f"Dataset file not found: {path}")

            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                topics = []
                # V3 dataset problems are stored under the 'problems' key
                for p in data.get("problems", []):
                    t = p.get("topic")
                    if t and t not in topics:
                        topics.append(t)

                if not topics:
                    logger.warning("No Topics extracted from dataset, please check JSON format.")
                return topics
        except Exception as e:
            logger.error(f"Unable to read V3 dataset to generate Roadmap: {e}")
            # Fallback Roadmap (V3 core topics)
            return ["Limits and Continuity", "Derivatives", "Integrals", "Vector Calculus"]

    def _load_progress(self) -> Dict:
        """Load or initialize user progress data via the storage backend."""
        data = self.store.load(self.user_id)
        if data:
            # Ensure all roadmap topics are initialized
            if "topics_status" not in data:
                data["topics_status"] = {}
            for topic in self.roadmap:
                if topic not in data["topics_status"]:
                    data["topics_status"][topic] = {
                        "mastery_score": 0.0,
                        "current_level": 1,
                        "completed_count": 0
                    }
            return data

        # Initialize new user structure
        return {
            "metadata": {
                "user_id": self.user_id,
                "join_date": datetime.now().strftime("%Y-%m-%d"),
                "total_minutes": 0.0,
                "dataset_version": "V3"
            },
            "topics_status": {
                topic: {
                    "mastery_score": 0.0,  # Mastery: 0.0 to 1.0
                    "current_level": 1,  # Level: 1(Basic), 2(Advanced), 3(Comprehensive/Exam)
                    "completed_count": 0
                } for topic in self.roadmap
            },
            "learning_history": []
        }

    def start_learning(self):
        """Start learning session"""
        self.session_start_time = time.time()
        logger.info(f"User {self.user_id}'s V3 learning session has started.")

    def stop_learning(self):
        """End session and persist time record"""
        if self.session_start_time:
            duration = (time.time() - self.session_start_time) / 60
            self.progress["metadata"]["total_minutes"] += round(duration, 2)
            self.session_start_time = None
            self.save()

    def save(self):
        """Save progress via the storage backend."""
        self.store.save(self.user_id, self.progress)

    def get_current_task_params(self) -> Dict:
        """Adaptive path algorithm: Find the first topic not meeting target based on V3 Roadmap"""
        for topic in self.roadmap:
            status = self.progress["topics_status"].get(topic)
            if not status: continue

            if status["mastery_score"] < 0.85:
                level = status["current_level"]
                # Difficulty strategy: L1 -> Diff 2, L2 -> Diff 3, L3 -> Diff 4/5
                difficulty = 2 if level == 1 else (3 if level == 2 else 4)
                mode = "drill" if level < 3 else "exam"

                return {
                    "topic": topic,
                    "difficulty": difficulty,
                    "mode": mode,
                    "level": level
                }
        # Challenge mode after all levels completed
        return {"topic": self.roadmap[-1], "difficulty": 5, "mode": "exam", "level": 3}

    def record_result(self, topic: str, score: float, is_passed: bool):
        """Update score, smoothly calculate mastery and handle level promotion"""
        # Compatibility handling: Try to match V3 normalized Topic name
        target_topic = None
        if topic in self.progress["topics_status"]:
            target_topic = topic
        else:
            # Fuzzy matching (prevent minor differences in AI-returned topic names)
            for r_topic in self.roadmap:
                if topic.lower().strip() in r_topic.lower() or r_topic.lower() in topic.lower():
                    target_topic = r_topic
                    break

        if not target_topic:
            logger.warning(f"Unable to identify topic '{topic}', score not recorded.")
            return

        status = self.progress["topics_status"][target_topic]

        # EMA mastery algorithm (maintain smooth growth)
        old_mastery = status["mastery_score"]
        status["mastery_score"] = round(old_mastery * 0.4 + (score / 100) * 0.6, 2)
        status["completed_count"] += 1

        # Promotion logic: Score meets threshold and not yet at max level
        if is_passed and score >= 80 and status["current_level"] < 3:
            status["current_level"] += 1
            logger.info(f"🎊 Promotion! [{target_topic}] advanced to Level {status['current_level']}")

        self.progress["learning_history"].append({
            "time": datetime.now().isoformat(),
            "topic": target_topic,
            "score": score,
            "level_at_time": status["current_level"]
        })
        self.save()

    def generate_visual_dashboard(self, save_path: str = "output/dashboard.png"):
        """Generate V3 progress-based visualization dashboard"""
        out_p = Path(__file__).resolve().parent.parent / save_path
        out_p.parent.mkdir(parents=True, exist_ok=True)

        topics = self.roadmap
        if not topics: return

        # Format labels
        display_labels = [t.replace(" and ", " &\n") if len(t) > 12 else t for t in topics]
        mastery_scores = [self.progress["topics_status"][t]["mastery_score"] * 100 for t in topics]
        levels = [self.progress["topics_status"][t]["current_level"] for t in topics]

        fig = plt.figure(figsize=(16, 8))
        plt.suptitle(f"T2P V3 Learning Analytics - {self.user_id}", fontsize=20, fontweight='bold', y=0.98)

        # 1. Radar chart (Mastery distribution)
        ax1 = fig.add_subplot(121, polar=True)
        angles = np.linspace(0, 2 * np.pi, len(topics), endpoint=False).tolist()
        # Close the loop
        scores_plot = mastery_scores + [mastery_scores[0]]
        angles_plot = angles + [angles[0]]

        ax1.fill(angles_plot, scores_plot, color='#3498DB', alpha=0.3)
        ax1.plot(angles_plot, scores_plot, color='#2980B9', linewidth=2, marker='o')
        ax1.set_xticks(angles)
        ax1.set_xticklabels(display_labels, fontsize=9)
        ax1.set_title("Mastery Overview (%)", size=14, pad=30)

        # 2. Progress bars (Level distribution)
        ax2 = fig.add_subplot(122)
        colors = ['#2ECC71' if l == 3 else ('#F1C40F' if l == 2 else '#BDC3C7') for l in levels]
        bars = ax2.bar(topics, levels, color=colors, alpha=0.8, edgecolor='#2C3E50')

        ax2.set_xticks(range(len(topics)))
        ax2.set_xticklabels(display_labels, rotation=25, ha="right", fontsize=9)
        ax2.set_yticks([1, 2, 3])
        ax2.set_yticklabels(['L1: Basics', 'L2: Scaffolding', 'L3: Exam Ready'])
        ax2.set_title("Progression by Topic", size=14, pad=20)

        # Display completed count above bars
        for bar, t in zip(bars, topics):
            count = self.progress["topics_status"][t]["completed_count"]
            ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.05,
                     f'n={count}', ha='center', va='bottom', fontsize=8, fontweight='bold')

        plt.tight_layout(rect=[0, 0.03, 1, 0.95])
        plt.savefig(str(out_p), dpi=300)
        plt.close()
        logger.info(f"Dashboard chart saved: {out_p}")

    def generate_report(self):
        """Generate terminal character-style learning report"""

        print(f"║ {('V3 LEARNING REPORT: ' + self.user_id).center(60)} ║")

        print(f"║ Total Study Time: {self.progress['metadata']['total_minutes']:<32} mins ║")


        for topic in self.roadmap:
            data = self.progress["topics_status"][topic]
            icon = "✅" if data["mastery_score"] >= 0.85 else "🏗️"
            # Progress bar logic
            bar_len = int(data['mastery_score'] * 20)
            p_bar = "█" * bar_len + "░" * (20 - bar_len)

            # Alignment display
            topic_disp = (topic[:25] + "..") if len(topic) > 27 else topic
            print(
                f"║ {icon} {topic_disp:<27} | L{data['current_level']} | {p_bar} {int(data['mastery_score'] * 100):>3}% ║")



        # Auto-refresh chart
        self.generate_visual_dashboard(save_path=f"output/dashboard_{self.user_id}.png")