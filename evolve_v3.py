import json
import logging
import time
import sys
from pathlib import Path

# --- Key path adaptation: Ensure script can find modules in the src directory ---
root_dir = Path(__file__).resolve().parent
src_dir = root_dir / "src"
if src_dir.exists() and str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
# ----------------------------------------------

from src.config import Config
from src.batch_generator import BatchGenerator


def setup_v3_logging():
    """Configure logging: optimize display and support UTF-8"""
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    if logger.hasHandlers():
        logger.handlers.clear()

    # Standard output stream
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(logging.Formatter(log_format))
    logger.addHandler(stdout_handler)

    # Specialized resume log file for checkpointing
    log_file = Path(Config.LOG_FILE).parent / "v3_evolution_resume.log"
    file_handler = logging.FileHandler(str(log_file), encoding='utf-8')
    file_handler.setFormatter(logging.Formatter(log_format))
    logger.addHandler(file_handler)

    return logging.getLogger("V3_Evolver")


def evolve_to_v3():
    logger = setup_v3_logging()

    # 1. Initialize core components
    batch_gen = BatchGenerator()
    loader = batch_gen.data_loader
    generator = batch_gen.generator

    v3_path = Path(Config.BASE_DIR) / "data" / "golden_dataset_v3.json"

    # 2. Check existing progress (Load Checkpoint)
    current_problems = []
    if v3_path.exists():
        logger.info(f"Existing V3 dataset found, loading progress...")
        with open(v3_path, 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
            current_problems = existing_data.get("problems", [])
        logger.info(f"Currently contains {len(current_problems)} problems.")
    else:
        logger.info(f"V3 dataset not found, starting evolution based on V2.")
        current_problems = loader.problems

    # [Core Modification 1]: Unify/Confirm 'type' field for existing problems
    for p in current_problems:
        if "type" not in p:
            # Migrate question_type to type if only the former exists
            p["type"] = p.get("question_type", "calculation")

    main_topics = loader.get_main_topics()
    expansion_plans = [
        {"type": "mcq", "count": 5},
        {"type": "fill_in", "count": 5}
    ]

    # 3. Iterative generation and gap filling
    for topic in main_topics:
        logger.info(f" Processing Topic: 【{topic}】")

        for plan in expansion_plans:
            q_type = plan["type"]
            target_num = plan["count"]

            # [Core Modification 2]: Use 'type' field for statistics
            existing_count = len([p for p in current_problems
                                  if p.get('topic') == topic and p.get('type') == q_type])

            needed = target_num - existing_count
            if needed <= 0:
                logger.info(f"[{q_type}] Target reached ({existing_count}/{target_num}), skipping.")
                continue

            logger.info(f" [{q_type}] Need to supplement {needed} problems (Current: {existing_count}/{target_num})...")

            success_count = 0
            attempts = 0
            max_attempts = needed * 3

            while success_count < needed and attempts < max_attempts:
                attempts += 1
                try:
                    # Call generator
                    problem = generator.generate_one(
                        topics=[topic],
                        mode="drill",
                        difficulty=3,
                        question_type=q_type
                    )

                    if problem and problem.get('evaluation', {}).get('score', 0) >= 85:
                        # Ensure unified and unique ID format
                        topic_code = topic[:3].upper().replace(" ", "")
                        timestamp = int(time.time()) % 10000
                        problem["problem_id"] = f"V3_{topic_code}_{q_type.upper()}_{timestamp}_{success_count}"

                        # [Core Modification 3]: Store new problem type in 'type' field
                        problem["type"] = q_type

                        # Special validation for MCQ
                        if q_type == "mcq" and "options" not in problem:
                            logger.warning(" Generation missing options, discarding problem.")
                            continue

                        current_problems.append(problem)
                        success_count += 1
                        logger.info(f"  Success ({success_count}/{needed}) | Score: {problem['evaluation']['score']}")

                        # Real-time save
                        save_dataset(v3_path, current_problems)

                    # Frequency protection
                    time.sleep(15)

                except Exception as e:
                    logger.error(f" =Serious Exception: {str(e)}")
                    logger.info("   = System paused for 10 seconds before next round...")
                    time.sleep(10)


    logger.info(f"Evolution complete! Final V3 dataset size: {len(current_problems)} problems.")


def save_dataset(path, problems):
    """Helper function to save the dataset"""
    output_data = {
        "dataset_info": {
            "name": "T2P Calculus Golden Dataset V3 (Smart Recovery)",
            "version": "3.1",
            "total_problems": len(problems),
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "description": "Comprehensive calculus dataset with MCQ and Fill-in types. Includes 429 self-healing capability."
        },
        "problems": problems
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    try:
        evolve_to_v3()
    except KeyboardInterrupt:
        print("\nProcess terminated by user. Current progress saved to golden_dataset_v3.json")