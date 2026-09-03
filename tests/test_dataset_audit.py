import copy
import json
import tempfile
import unittest
from pathlib import Path

from audit_dataset import (
    audit_dataset,
    duplicate_analysis,
    portable_dataset_path,
    validate_problem,
)


def base_problem(**overrides):
    problem = {
        "problem_id": "TEST_001",
        "topic": "Limits and Continuity",
        "sub_topic": "One-sided limits",
        "difficulty": 3,
        "problem_statement": "Evaluate $\\lim_{x \\to 0} x$.",
        "scaffolding": [{"step": 1, "hint": "Substitute $x=0$."}],
        "solution": "The limit is $0$.",
        "question_type": "calculation",
        "pedagogical_principle": "Scaffolding Steps",
        "multiple_representations": ["symbolic"],
        "concepts": ["limit"],
        "real_world_context": "Not applicable",
    }
    problem.update(overrides)
    return problem


class DatasetAuditValidationTests(unittest.TestCase):
    def test_report_path_does_not_expose_external_directories(self):
        external_path = Path(tempfile.gettempdir()) / "private" / "dataset.json"

        self.assertEqual(portable_dataset_path(external_path), "dataset.json")

    def test_legacy_mcq_answer_is_accepted_with_compatibility_warning(self):
        problem = base_problem(
            question_type="mcq",
            options={"A": "0", "B": "1", "C": "2", "D": "Undefined"},
            correct_answer="A",
        )

        issues = validate_problem(problem, 0)
        codes = {issue["code"] for issue in issues}

        self.assertIn("legacy_answer_field", codes)
        self.assertNotIn("invalid_mcq_answer", codes)

    def test_legacy_fill_answer_is_accepted_with_compatibility_warning(self):
        problem = base_problem(question_type="fill_in", correct_answer=["0"])

        issues = validate_problem(problem, 0)
        codes = {issue["code"] for issue in issues}

        self.assertIn("legacy_fill_answer_field", codes)
        self.assertNotIn("missing_fill_in_answers", codes)

    def test_validation_does_not_mutate_problem(self):
        problem = base_problem(question_type="fill_in", correct_values=["0"])
        original = copy.deepcopy(problem)

        validate_problem(problem, 0)

        self.assertEqual(problem, original)


class DatasetAuditDuplicateTests(unittest.TestCase):
    def test_exact_and_near_duplicates_are_reported_separately(self):
        problems = [
            base_problem(problem_id="A", problem_statement="Find $\\int x \\, dx$."),
            base_problem(problem_id="B", problem_statement="Find $\\int x \\, dx$."),
            base_problem(problem_id="C", problem_statement="Find $\\int x^2 \\, dx$."),
        ]

        exact, near, issues = duplicate_analysis(problems, threshold=0.80)

        self.assertEqual(exact, [{"problem_ids": ["A", "B"], "count": 2}])
        self.assertTrue(any(pair["right_problem_id"] == "C" for pair in near))
        self.assertEqual(
            sum(issue["code"] == "exact_duplicate_statement" for issue in issues),
            2,
        )

    def test_full_audit_detects_duplicate_ids_without_network_calls(self):
        first = base_problem(problem_id="DUPLICATE")
        second = base_problem(
            problem_id="DUPLICATE",
            problem_statement="Different problem: calculate $1+1$.",
        )
        payload = {
            "dataset_info": {"total_problems": 2},
            "problems": [first, second],
        }

        with tempfile.TemporaryDirectory() as temporary_directory:
            dataset_path = Path(temporary_directory) / "dataset.json"
            dataset_path.write_text(json.dumps(payload), encoding="utf-8")
            report = audit_dataset(dataset_path, near_duplicate_threshold=0.92)

        self.assertEqual(report["audit_metadata"]["network_calls"], 0)
        self.assertEqual(report["summary"]["duplicate_id_group_count"], 1)
        self.assertEqual(
            report["summary"]["issues_by_code"]["duplicate_problem_id"],
            1,
        )


if __name__ == "__main__":
    unittest.main()
