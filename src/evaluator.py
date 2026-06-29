"""
Quality Evaluator - Intelligent & Robust Version (V4.1)
Audit engine optimized for deep fusion mode:
1. Strengthened weight of cross-knowledge-point connection logic (Concept Integration).
2. Introduced logical gap scanning to ensure rigor of multi-step comprehensive problems.
3. Enhanced JSON safe extraction and defensive cleaning, adapted for LLM outputs.
4. [Core Fix]: Completely decoupled Drill mode admission criteria, exempting single-topic problems from fusion score requirements.
"""
import json
import logging
import os
import re
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from src.ai_client import AIClient

logger = logging.getLogger(__name__)


@dataclass
class EvaluationResult:
    """Evaluation result data class"""
    score: float
    dimensions: Dict[str, float]
    issues: List[str]
    passed: bool
    ai_feedback: str = ""


class QualityEvaluator:
    """Intelligent quality evaluator - Responsible for closed-loop quality control of the T2P system"""

    def __init__(self, golden_data_loader=None, ai_client=None):
        self.golden_loader = golden_data_loader
        self.ai_client = ai_client or AIClient()

        # Demo mode: skip AI review to save API calls & latency
        self.enable_ai_review = os.getenv("ENABLE_AI_REVIEW", "true").lower() in ("true", "1", "yes")
        if not self.enable_ai_review:
            logger.info("AI review disabled — using rule-based evaluation only")

        # Weight distribution: In comprehensive mode, mathematical logic and knowledge point fusion are core
        self.weights = {
            'structure': 0.10,  # Basic JSON structure
            'math_logic': 0.35,  # Mathematical logic accuracy (Core)
            'scaffolding': 0.15,  # Scaffolded teaching quality
            'pedagogical_alignment': 0.15,  # Pedagogical principle alignment
            'concept_integration': 0.15,  # Cross-knowledge-point fusion depth
            'originality': 0.10  # Originality
        }

    def _extract_json(self, text: str) -> Dict:
        """Safely extract JSON from model response text"""
        try:
            text = text.strip()
            if text.startswith("```"):
                text = re.sub(r'^```json\s*|```$', '', text, flags=re.MULTILINE)

            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                data = json.loads(match.group())
                return self._clean_ai_json(data)
            return {}
        except Exception as e:
            logger.warning(f"JSON extraction failed: {e}")
            return {}

    def _clean_ai_json(self, data: Dict) -> Dict:
        """Defensive cleaning: Convert AI-returned null values to safe defaults"""
        if not isinstance(data, dict):
            return {}

        cleaned = {}
        for k, v in data.items():
            if v is None:
                if 'score' in k:
                    cleaned[k] = 0
                elif 'is_' in k or 'correct' in k:
                    cleaned[k] = False
                else:
                    cleaned[k] = "N/A"
            else:
                cleaned[k] = v
        return cleaned

    def _evaluate_with_llm(self, problem: Dict, expected_topics: List[str]) -> Dict[str, Any]:
        """Use AI for expert-level review"""
        anchor = expected_topics[0] if expected_topics else "Unknown"
        related = expected_topics[1:] if len(expected_topics) > 1 else []

        # Prompt optimization: Explicitly inform Auditor that Integration score of 0 is reasonable in Drill mode
        review_prompt = f"""
        [ROLE] Senior Mathematics Education Auditor
        [TASK] Critically evaluate this calculus problem.

        [CONTEXT]
        Core Anchor Topic: {anchor}
        Related Concepts: {related}

        [PROBLEM DATA]
        {json.dumps(problem, indent=2)}

        [AUDIT RUBRIC]
        1. MATH ACCURACY: Is the solution logically sound?
        2. CONCEPT FUSION: Meaningful link between {anchor} and {related}? (Note: If this is a single-topic DRILL, 0 is acceptable).
        3. SCAFFOLDING: Do hints guide without giving away the answer?
        4. LOGICAL CONTINUITY: Do steps follow logically?

        [OUTPUT FORMAT] Return ONLY a RAW JSON object:
        {{
            "math_logic_score": 0-100,
            "pedagogical_score": 0-100,
            "integration_score": 0-100,
            "is_mathematically_correct": true/false,
            "logical_gap_detected": true/false,
            "critical_flaw": "Specific description",
            "improvement_suggestion": "Concrete action"
        }}
        """
        try:
            response = self.ai_client.generate(review_prompt, temperature=0.1)
            return self._extract_json(response)
        except Exception as e:
            logger.error(f"AI review connection exception: {e}")
            return {
                "is_mathematically_correct": False,
                "math_logic_score": 0,
                "pedagogical_score": 0,
                "integration_score": 0,
                "critical_flaw": f"Evaluation Pipeline Error: {str(e)}"
            }

    def evaluate(self, problem: Dict, target_topics: List[str] = None) -> EvaluationResult:
        """Execute comprehensive audit pipeline"""
        dimensions = {}
        all_issues = []

        # Identify current mode
        current_mode = problem.get('mode', 'drill').lower()

        # 1. Structure and completeness validation
        required = ['problem_statement', 'scaffolding', 'solution', 'integration_analysis']
        missing_fields = [f for f in required if f not in problem or not problem[f]]
        struct_score = 100 - (len(missing_fields) * 25)
        dimensions['structure'] = max(0, struct_score)
        if missing_fields:
            all_issues.append(f"Missing mandatory fields: {missing_fields}")

        # 2. AI deep semantic audit (skippable via ENABLE_AI_REVIEW=false)
        if self.enable_ai_review:
            ai_review = self._evaluate_with_llm(problem, target_topics or [])
        else:
            ai_review = {
                "math_logic_score": 85,
                "pedagogical_score": 80,
                "integration_score": 75,
                "is_mathematically_correct": True,
                "logical_gap_detected": False,
                "critical_flaw": "AI review disabled (demo mode)",
                "improvement_suggestion": "Enable AI review for full audit"
            }

        dimensions['math_logic'] = float(ai_review.get('math_logic_score') or 0)
        dimensions['pedagogical_alignment'] = float(ai_review.get('pedagogical_score') or 0)
        dimensions['scaffolding'] = float(ai_review.get('pedagogical_score') or 0)
        dimensions['concept_integration'] = float(ai_review.get('integration_score') or 0)

        # 3. Originality check
        dimensions['originality'] = 100.0
        if self.golden_loader and problem.get('problem_statement'):
            statement_snippet = problem['problem_statement'][:40]
            for golden_p in self.golden_loader.problems[:10]:
                if statement_snippet in golden_p.get('problem_statement', ''):
                    dimensions['originality'] = 30.0
                    all_issues.append("High similarity detected with Golden Dataset.")
                    break

        # 4. Final weighted summary
        total_score = sum(dimensions[dim] * self.weights.get(dim, 0) for dim in dimensions)

        # 5. Admission criteria (Core logic correction)
        pass_threshold = 60.0 if current_mode == 'drill' else 75.0
        is_correct = ai_review.get('is_mathematically_correct', False)
        is_logical = not ai_review.get('logical_gap_detected', True)

        # Mode-specific admission conditions
        if current_mode == 'drill':
            # --- DRILL mode admission conditions: Fusion requirement exempted ---
            # Passed as long as total score meets threshold, math is correct, logic is coherent, and structure is complete
            passed = (
                    total_score >= pass_threshold and
                    is_correct and
                    is_logical and
                    dimensions['structure'] >= 75
            )
        else:
            # --- EXAM/FUSION mode admission conditions: Maintain high standards ---
            # Must meet fusion score hard requirement (>= 50)
            passed = (
                    total_score >= pass_threshold and
                    is_correct and
                    is_logical and
                    dimensions['structure'] >= 75 and
                    dimensions['concept_integration'] >= 50.0
            )

        # 6. Build feedback
        flaw = ai_review.get('critical_flaw') or "None"
        suggestion = ai_review.get('improvement_suggestion') or "N/A"

        feedback = (
            f"Status: {'Passed' if passed else 'Failed'} | "
            f"Score: {total_score:.1f}/{pass_threshold} | "
            f"Mode: {current_mode.upper()} | "
            f"Flaw: {flaw} | "
            f"Suggestion: {suggestion}"
        )

        if not is_correct:
            all_issues.append("CRITICAL: Mathematical logic error.")
        if not is_logical:
            all_issues.append("LOGIC GAP: Disconnected steps.")

        return EvaluationResult(
            score=round(total_score, 1),
            dimensions=dimensions,
            issues=all_issues,
            passed=passed,
            ai_feedback=feedback
        )