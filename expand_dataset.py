import sys
from pathlib import Path

# --- Key path adaptation: Ensure the script can find modules in the src directory ---
root_dir = Path(__file__).resolve().parent
src_dir = root_dir / "src"
if src_dir.exists() and str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
# ----------------------------------------------

import json
import logging
from pathlib import Path
from src.batch_generator import BatchGenerator
from src.config import Config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DatasetExpander")


def expand_golden_dataset(target_count=10):
    # 1. Initialize existing orchestrator
    batch_gen = BatchGenerator()
    data_loader = batch_gen.data_loader
    output_path = Path(Config.GOLDEN_DATASET_PATH)

    # Get all current topics
    topics = data_loader.get_topics()
    logger.info(f"Starting expansion task. Target: {target_count} problems per topic. Current topics: {len(topics)}")

    all_new_problems = []

    for topic in topics:
        current_probs = data_loader.topics_map.get(topic, [])
        needed = target_count - len(current_probs)

        if needed <= 0:
            logger.info(f"Topic '{topic}' already meets the target (Current: {len(current_probs)})")
            continue

        logger.info(f"Generating {needed} high-quality problems for '{topic}'...")

        # 2. Call existing generate_batch with mode='drill'
        # Utilizing existing self-healing and evaluation logic
        results = batch_gen.generator.generate_batch(
            topics=[topic],
            num=needed,
            mode="drill",
            difficulty=3  # Medium difficulty recommended for seed data
        )

        # 3. Filter high-standard problems for the golden dataset
        for prob in results:
            # Only include problems with evaluation score > 85 and passed logic checks
            if prob.get('evaluation', {}).get('score', 0) >= 85:
                # Remove temporary generation fields to keep the golden dataset clean
                clean_prob = {
                    "problem_id": f"EXT_{topic[:3].upper()}_{len(all_new_problems):03d}",
                    "topic": prob.get("topic", topic),
                    "sub_topic": topic,
                    "difficulty": prob.get("difficulty"),
                    "problem_statement": prob.get("problem_statement"),
                    "scaffolding": prob.get("scaffolding"),
                    "solution": prob.get("solution"),
                    "real_world_context": prob.get("real_world_context"),
                    "concepts": prob.get("concepts")
                }
                all_new_problems.append(clean_prob)

    # 4. Write back to file
    if all_new_problems:
        # Read original file content
        with open(output_path, 'r', encoding='utf-8') as f:
            full_data = json.load(f)

        # Merge data
        if isinstance(full_data, dict) and 'problems' in full_data:
            full_data['problems'].extend(all_new_problems)
            full_data['dataset_info']['total_problems'] = len(full_data['problems'])
        else:
            # Compatibility for pure list format
            full_data.extend(all_new_problems)

        # Backup and save
        backup_path = output_path.with_suffix('.json.bak')
        output_path.rename(backup_path)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(full_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Expansion complete! Successfully added {len(all_new_problems)} problems to {output_path}")
    else:
        logger.info("No high-quality problems generated. File remains unchanged.")


if __name__ == "__main__":
    expand_golden_dataset(target_count=10)