"""
T2P: Automated Calculus Problem Generation and Intelligent Grading System - Mentor Edition
Supports:
1. Problem generation (Drill/Exam mode)
2. Intelligent grading (AI Mentor mode): Supports photo/handwriting recognition, line-by-line logic audit
3. Strict exam (Strict Mode): Hide hints, strengthen logical integrity check
"""
import argparse
import logging
import sys
import json
from pathlib import Path

# --- Path setup ---
root_dir = Path(__file__).resolve().parent
src_dir = root_dir / "src"
if src_dir.exists() and str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

# --- Import business modules ---
try:
    from src.config import Config
    from src.core import AppCore
    from src.batch_generator import BatchGenerator
except ImportError as e:
    print(f"Startup failed: Cannot find core modules ({e})")
    print(f"Please check directory structure, ensure {src_dir} directory has __init__.py file.")
    sys.exit(1)


def setup_logging():
    """Configure system logging"""
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    log_file = Path(Config.LOG_FILE)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, Config.LOG_LEVEL, logging.INFO),
        format=log_format,
        handlers=[
            logging.FileHandler(str(log_file), encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )


def print_banner():
    """Print welcome banner"""
    banner = """
    ================================================
    |           T2P: Term 2 Project                |
    |    AI-Driven Calculus Mentor System (V4.0)   |
    |      - Generative Learning & AI Grading -    |
    ================================================
    """
    print(banner)


def main():
    """Program main entry"""
    parser = argparse.ArgumentParser(
        description='T2P: Intelligent Calculus Teaching Assistant with Visual Understanding',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    # 1. Problem generation configuration
    gen_group = parser.add_argument_group('Problem Generation Configuration')
    gen_group.add_argument('--mode', type=str, choices=['drill', 'exam'], default='drill',
                           help='Generation mode: drill (targeted training) or exam (comprehensive exam)')
    gen_group.add_argument('--topics', nargs='+', help='Specify topic keywords')
    gen_group.add_argument('--num', type=int, default=5, help='Total number of problems to generate')
    gen_group.add_argument('--difficulty', type=int, choices=[1, 2, 3, 4, 5], default=3,
                           help='Target difficulty level (1-5)')

    # 2. Intelligent grading configuration
    mentor_group = parser.add_argument_group('Intelligent Grading (AI Mentor)')
    mentor_group.add_argument('--review', type=str, metavar='IMAGE_PATH',
                              help='Enable grading mode, enter the path to handwritten solution photo')
    mentor_group.add_argument('--pid', type=str, help='Specify the problem ID to grade (e.g., LIM_001)')
    mentor_group.add_argument('--strict', action='store_true',
                              help='Enable simulated exam mode (no hints, strict derivation process check)')

    # 3. Auxiliary functions
    aux = parser.add_argument_group('Auxiliary Functions')
    aux.add_argument('--batch-name', type=str, help='Custom batch name')
    aux.add_argument('--stats', action='store_true', help='Display historical generation statistics summary')
    aux.add_argument('--list-topics', action='store_true', help='List all available topics in the problem bank')

    if len(sys.argv) == 1:
        print_banner()
        parser.print_help()
        return

    args = parser.parse_args()
    setup_logging()
    logger = logging.getLogger("Main")

    try:
        # Initialize orchestrator via AppCore singleton
        _ = AppCore.get()  # ensures shared instances are ready
        orchestrator = BatchGenerator()

        # --- Branch 1: Intelligent grading mode (AI Mentor Mode) ---
        if args.review:
            if not args.pid:
                print("Error: Grading mode must specify the corresponding problem ID using --pid.")
                return

            image_path = Path(args.review)
            if not image_path.exists():
                print(f"Error: Cannot find photo file -> {args.review}")
                return

            print_banner()
            print(f" T2P AI Mentor is reviewing your derivation process...")
            print(f"Mode: {'【Simulated Exam】' if args.strict else '【Guided Practice】'}")


            # Call BatchGenerator's advanced audit interface
            feedback = orchestrator.review_student_submission(
                problem_id=args.pid,
                image_path=str(image_path),
                is_exam_mode=args.strict
            )

            if "error" in feedback:
                print(f"Grading failed: {feedback['error']}")
                return

            # Output audit results

            print(f"【 Grading Results Summary 】")

            # Handle different formats of feedback output
            is_correct = feedback.get('is_correct', False)
            status_icon = "Logic Passed" if is_correct else "Requires Further Correction"
            print(f"Status: {status_icon}")

            if 'score' in feedback:
                print(f"Score: {feedback['score']}/100")

            print(f"\nAI Mentor Feedback ")
            # Compatibility handling: If LLM returned raw text instead of structured JSON
            tutor_msg = feedback.get('tutor_feedback') or feedback.get('raw_ai_feedback',
                                                                       "Unable to generate detailed feedback.")
            print(tutor_msg)

            if not is_correct and feedback.get('critical_flaw'):
                print(f"\nCore Logic Flaw: {feedback['critical_flaw']}")


            return

        # --- Branch 2: List topics ---
        if args.list_topics:
            # Prioritize calling get_main_topics to get clear main categories
            topics = orchestrator.data_loader.get_main_topics()
            print("\nT2P Problem Bank Available Core Knowledge Points (Main Topics):")

            for i, topic in enumerate(topics, 1):
                count = len(orchestrator.data_loader.topics_map.get(topic, []))
                print(f"  {i:02d}. {topic:<30} (Seed problem count: {count})")

            return

        # --- Branch 3: Statistics summary ---
        if args.stats:
            stats = orchestrator.get_statistics()
            print("\nT2P System Runtime Status Summary")

            print(f"Total Generated Batches: {stats['total_batches']}")
            print(f"Total Generated Count: {stats['total_problems']}")
            print(f"Drill Sessions: {stats['mode_distribution']['drill']}")
            print(f"Exam Sessions: {stats['mode_distribution']['exam']}")
            if 'performance' in stats:
                print(f"Average Problem Quality: {stats['performance']['avg_quality_score']} / 100")

            return

        # --- Branch 4: Problem generation logic ---
        target_topics = args.topics
        if not target_topics:
            if args.mode == 'drill':
                print(" Error: Drill mode requires at least one knowledge point specified via --topics parameter.")
                return
            else:
                # Exam mode defaults to covering all core topics
                target_topics = orchestrator.data_loader.get_main_topics()

        print_banner()
        print(f"Task starting...")
        print(f"Running Mode: {args.mode.upper()}")
        print(f"Topics Involved: {', '.join(target_topics)}")
        print(f"Target Difficulty: {args.difficulty}/5")
        if args.batch_name:
            print(f"🏷Batch Label: {args.batch_name}")


        # Execute batch generation
        result = orchestrator.generate(
            topics=target_topics,
            num=args.num,
            mode=args.mode,
            difficulty=args.difficulty,
            batch_name=args.batch_name
        )

        batch_id = result.get('batch_id', 'unknown')
        output_file_path = orchestrator.output_dir / f"{batch_id}.json"


        print(f"Batch problem generation completed successfully!")
        print(f"Task Batch: {batch_id}")
        print(f"Result File: {output_file_path}")
        print(f"💡Tip: After scanning the solution, use --review {batch_id}.jpg --pid [ID] for grading.")


    except KeyboardInterrupt:
        print("\n Operation interrupted by user, exiting safely...")
    except Exception as e:
        logger.error(f"Program runtime exception: {str(e)}", exc_info=True)
        print(f"\nSystem Failure: {str(e)}")
        print(f"Detailed error log recorded to: {Config.LOG_FILE}")
        sys.exit(1)


if __name__ == '__main__':
    main()

