"""
Prompt Builder - Core Anchor & Multi-Dimensional Fusion (V4.0)
Optimizations:
1. Deprecated Exam paper package mode, changed to generating "deep fusion comprehensive problems".
2. Introduced "core anchor + related knowledge points" prompt logic.
3. Strengthened robustness of LaTeX double escaping and JSON structure.
"""
import json
import random
from typing import List, Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)

class PromptBuilder:
    """Prompt builder - Supports single knowledge point training and multi-knowledge-point deep fusion problem generation"""

    def __init__(self, data_loader):
        """
        Initialize builder
        Args:
            data_loader: GoldenDataLoader instance
        """
        self.data_loader = data_loader

    def build_prompt(self, topics: List[str], mode: str = "drill",
                     difficulty: int = 3, question_type: str = "calculation",
                     feedback: str = "") -> str:
        """
        Unified entry: Build deep fusion problem or targeted training prompts
        """
        if isinstance(topics, str):
            topics = [topics]

        # Validate whether question_type is valid
        valid_types = ["calculation", "mcq", "fill_in"]
        if question_type not in valid_types:
            logger.warning(f"Invalid question_type '{question_type}', defaulting to 'calculation'")
            question_type = "calculation"

        # 0. JSON-only constraint (DeepSeek has no native JSON mode)
        json_only = "\n[!!! CRITICAL: YOU MUST RETURN ONLY RAW VALID JSON. NO markdown wrappers. NO explanation text. NO code fences. PURE JSON ONLY. !!!]\n"

        # 1. Build base prompt according to mode
        if mode == "exam":
            # In Exam mode, the first topic is the core anchor, the rest are related knowledge points
            anchor_topic = topics[0] if topics else "Calculus"
            related_topics = topics[1:] if len(topics) > 1 else []
            prompt = json_only + self._build_fusion_exam_prompt(anchor_topic, related_topics, difficulty)
        else:
            target_topic = topics[0] if topics else "Calculus Fundamentals"
            prompt = json_only + self._build_drill_prompt(target_topic, difficulty, question_type)

        # 2. Inject self-healing feedback
        if feedback:
            healing_block = (
                f"\n\n[!!! CRITICAL: SELF-HEALING FEEDBACK FROM PREVIOUS ATTEMPT !!!]\n"
                f"Your previous output failed evaluation: '{feedback}'\n"
                f"INSTRUCTION: Re-generate while fixing the logic/format issues. Pay special attention to LaTeX escaping and spacing."
            )
            prompt += healing_block

        return prompt

    def _get_base_role(self, is_fusion_mode: bool = False) -> str:
        role_type = "Senior Mathematics Curriculum Designer (Fusion Specialist)" if is_fusion_mode else "Calculus Pedagogy Researcher"
        return (
            f"ROLE: You are a {role_type}. "
            "Your goal is to generate mathematically rigorous, logically consistent, and pedagogically sound materials. "
            "LANG: Output in English (matching the seed examples). "
            "ALL math formulas and variable names MUST be in standard ASCII/LaTeX inside $...$ or $$...$$. "
            "NEVER convert math variables to Chinese or Unicode characters."
        )

    def _get_logic_guardrails(self) -> str:
        return (
            "\n[STRICT MATHEMATICAL LOGIC RULES]:\n"
            "1. NUMERICAL VERIFICATION: Ensure problems are solvable with clean results (prefer integers or simple fractions).\n"
            "2. GEOMETRIC CONSISTENCY: Verify function intersections and ensure area/volume values are positive.\n"
            "3. NO HALLUCINATION: All LaTeX must be syntactically correct and parsable.\n"
            "4. VARIABLE INTEGRITY: Math variables (t, x, y, s, a, b, n, etc.) inside $...$ must NEVER be translated, "
            "replaced, or converted to Chinese/Unicode characters. 't' stays 't', NOT '吨' or 'ｔ' (fullwidth)."
        )

    def _get_latex_constraints(self) -> str:
        """Unified and strict LaTeX formatting constraints"""
        return (
            "\n[STRICT LATEX & FORMATTING CONSTRAINTS]:"
            "\n1. ESCAPING: Inside JSON strings, use DOUBLE BACKSLASHES for all commands (e.g., '\\\\int', '\\\\frac')."
            "\n2. ENVIRONMENTS: For 'cases' or 'aligned', use FOUR BACKSLASHES for line breaks (e.g., '... \\\\\\\\ ...')."
            "\n3. DELIMITERS: Use ONLY single `$` for inline math and `$$` for block math. NEVER use `\\(`, `\\)`, `\\[`, or `\\]`."
            "\n4. MANDATORY SPACING: Leave a visible space between text and math delimiters (e.g., 'Let $ f(x) $ be')."
            "\n5. NO LAYOUT MACROS: NEVER use `\\\\quad`, `\\\\qquad`, or `\\\\text` for visual layout."
        )

    def _build_drill_prompt(self, topic: str, difficulty: int, question_type: str) -> str:
        """Targeted training mode: Focus on depth of a single knowledge point"""
        prompt_parts = [
            self._get_base_role(is_fusion_mode=False),
            f"\nTASK: Generate ONE {question_type.upper()} problem for the topic: '{topic}'.",
            f"DIFFICULTY LEVEL: {difficulty}/5.",
            self._get_logic_guardrails(),
            self._get_single_output_schema(topic, question_type)
        ]
        return "\n".join(prompt_parts)

    def _build_fusion_exam_prompt(self, anchor: str, related: List[str], difficulty: int) -> str:
        """Deep fusion mode: Core anchor + multi-dimensional association"""
        related_str = ", ".join(related) if related else "applicable cross-domain concepts"

        prompt_parts = [
            self._get_base_role(is_fusion_mode=True),
            f"\nTASK: Create ONE high-order INTEGRATED problem.",
            f"CORE ANCHOR TOPIC: '{anchor}'",
            f"MANDATORY RELATED CONCEPTS: [{related_str}]",
            f"TARGET DIFFICULTY: {difficulty}/5.",
            self._get_logic_guardrails(),
            "\n[FUSION INSTRUCTIONS]:",
            "1. THEME: The problem must start with the Core Anchor but require the Related Concepts to fully solve.",
            "2. STRUCTURE: Use a multi-part structure (e.g., Part a, Part b) where Part b relies on the result or concept of Part a.",
            "3. COMPLEXITY: Focus on the transition between concepts (e.g., finding a derivative to use in a related rates application).",
            self._get_single_output_schema(f"{anchor} (Fused)", "calculation")
        ]
        return "\n".join(prompt_parts)

    def _get_single_output_schema(self, topic_str: str, question_type: str) -> str:
        """Define the standard JSON structure for a single problem (compatible with both Drill and Fusion modes)"""
        schema = {
            "id": "T2P_GEN_1",
            "topic": topic_str,
            "problem_statement": "LaTeX text describing the problem",
            "question_type": question_type,
            "difficulty": 0,  # 0-5
            "solution": "Detailed multi-step LaTeX solution",
            "scaffolding": [
                {"step": 1, "hint": "Conceptual hint for the first hurdle"},
                {"step": 2, "hint": "Procedural hint for the calculation"}
            ],
            "integration_analysis": "Explanation of how different topics are fused here (Only for fusion mode)"
        }

        if question_type == "mcq":
            schema["options"] = {"A": "", "B": "", "C": "", "D": ""}
            schema["answer"] = "A"
        elif question_type == "fill_in":
            schema["problem_statement"] = "Problem text with [BLANK_1] and [BLANK_2]"
            schema["correct_values"] = ["val1", "val2"]

        return (
            "\n[STRICT OUTPUT RULE]: RETURN ONLY RAW JSON. NO MARKDOWN. NO PREFACE. NO CODE FENCES. PURE JSON OBJECT STARTING WITH '{' AND ENDING WITH '}'."
            f"\nJSON STRUCTURE:\n{json.dumps(schema, indent=2)}"
            f"\n{self._get_latex_constraints()}"
        )