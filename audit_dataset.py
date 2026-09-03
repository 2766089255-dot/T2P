"""Deterministic, offline quality audit for the T2P golden dataset.

The audit never calls DeepSeek, OCR.Space, or any other network service. It
checks schema completeness, distribution coverage, duplicate questions,
question-type constraints, scaffolding structure, and common LaTeX defects.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable


CORE_FIELDS = (
    "topic",
    "difficulty",
    "problem_statement",
    "scaffolding",
    "solution",
    "question_type",
)

ENRICHMENT_FIELDS = (
    "sub_topic",
    "pedagogical_principle",
    "multiple_representations",
    "concepts",
    "real_world_context",
)

VALID_QUESTION_TYPES = {"calculation", "mcq", "fill_in"}
LATEX_COMMANDS = (
    "lim",
    "frac",
    "int",
    "sqrt",
    "sum",
    "prod",
    "partial",
    "to",
    "infty",
    "sin",
    "cos",
    "tan",
    "ln",
)
PROJECT_ROOT = Path(__file__).resolve().parent


def portable_dataset_path(dataset_path: Path) -> str:
    """Return a repository-relative path without exposing a developer machine path."""
    resolved_path = dataset_path.resolve()
    try:
        return resolved_path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return dataset_path.name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit a T2P dataset without API calls")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/golden_dataset_v3.json"),
        help="Path to the source dataset JSON",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports"),
        help="Directory for the Markdown and JSON reports",
    )
    parser.add_argument(
        "--near-duplicate-threshold",
        type=float,
        default=0.92,
        help="Normalized statement similarity threshold (0-1)",
    )
    parser.add_argument(
        "--max-markdown-issues",
        type=int,
        default=80,
        help="Maximum issue rows included in the human-readable report",
    )
    return parser.parse_args()


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_statement(value: Any) -> str:
    text = normalize_text(value)
    text = re.sub(r"\\(?:left|right|quad|qquad)\b|\\[,;!]", "", text)
    text = re.sub(r"[\s$`*_{}\[\]()]", "", text)
    return text


def problem_identifier(problem: dict[str, Any], index: int) -> str:
    return str(problem.get("problem_id") or problem.get("id") or f"ROW_{index + 1}")


def make_issue(
    severity: str,
    code: str,
    problem_id: str,
    field: str,
    detail: str,
) -> dict[str, str]:
    return {
        "severity": severity,
        "code": code,
        "problem_id": problem_id,
        "field": field,
        "detail": detail,
    }


def field_is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict)):
        return not value
    return False


def count_unescaped_dollars(text: str) -> int:
    return len(re.findall(r"(?<!\\)\$", text))


def latex_issues(problem: dict[str, Any], problem_id: str) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    fields: list[tuple[str, str]] = []

    for field in ("problem_statement", "solution"):
        value = problem.get(field)
        if isinstance(value, str):
            fields.append((field, value))

    scaffolding = problem.get("scaffolding")
    if isinstance(scaffolding, list):
        for position, step in enumerate(scaffolding, start=1):
            if isinstance(step, dict) and isinstance(step.get("hint"), str):
                fields.append((f"scaffolding[{position}].hint", step["hint"]))

    suspicious_command_pattern = re.compile(
        r"\\\\(?:" + "|".join(LATEX_COMMANDS) + r")\b"
    )

    for field, text in fields:
        if count_unescaped_dollars(text) % 2:
            issues.append(
                make_issue(
                    "warning",
                    "unbalanced_math_delimiter",
                    problem_id,
                    field,
                    "The field contains an odd number of unescaped dollar delimiters.",
                )
            )
        if "\\(" in text or "\\)" in text or "\\[" in text or "\\]" in text:
            issues.append(
                make_issue(
                    "warning",
                    "nonstandard_math_delimiter",
                    problem_id,
                    field,
                    "The field uses \\( \\) or \\[ \\] instead of the project's $/$$ convention.",
                )
            )
        if suspicious_command_pattern.search(text):
            issues.append(
                make_issue(
                    "warning",
                    "suspicious_double_backslash",
                    problem_id,
                    field,
                    "A LaTeX command appears to contain two runtime backslashes.",
                )
            )
        if "\ufffd" in text:
            issues.append(
                make_issue(
                    "error",
                    "replacement_character",
                    problem_id,
                    field,
                    "The Unicode replacement character indicates corrupted text.",
                )
            )

    return issues


def validate_problem(problem: Any, index: int) -> list[dict[str, str]]:
    if not isinstance(problem, dict):
        return [
            make_issue(
                "error",
                "invalid_problem_record",
                f"ROW_{index + 1}",
                "record",
                f"Expected an object but found {type(problem).__name__}.",
            )
        ]

    problem_id = problem_identifier(problem, index)
    issues: list[dict[str, str]] = []

    if not problem.get("problem_id") and not problem.get("id"):
        issues.append(
            make_issue("error", "missing_id", problem_id, "problem_id", "No problem_id or id is present.")
        )

    for field in CORE_FIELDS:
        if field_is_empty(problem.get(field)):
            issues.append(
                make_issue("error", "missing_core_field", problem_id, field, "Required field is empty or absent.")
            )

    for field in ENRICHMENT_FIELDS:
        if field_is_empty(problem.get(field)):
            issues.append(
                make_issue(
                    "warning",
                    "missing_enrichment_field",
                    problem_id,
                    field,
                    "Pedagogical enrichment field is empty or absent.",
                )
            )

    difficulty = problem.get("difficulty")
    if not isinstance(difficulty, (int, float)) or isinstance(difficulty, bool) or not 1 <= difficulty <= 5:
        issues.append(
            make_issue(
                "error",
                "invalid_difficulty",
                problem_id,
                "difficulty",
                f"Expected a numeric level from 1 to 5, found {difficulty!r}.",
            )
        )

    question_type = normalize_text(problem.get("question_type") or problem.get("type"))
    if question_type not in VALID_QUESTION_TYPES:
        issues.append(
            make_issue(
                "error",
                "invalid_question_type",
                problem_id,
                "question_type",
                f"Expected one of {sorted(VALID_QUESTION_TYPES)}, found {question_type!r}.",
            )
        )

    if problem.get("type") and problem.get("question_type"):
        if normalize_text(problem["type"]) != normalize_text(problem["question_type"]):
            issues.append(
                make_issue(
                    "warning",
                    "question_type_mismatch",
                    problem_id,
                    "type",
                    "type and question_type contain different values.",
                )
            )

    scaffolding = problem.get("scaffolding")
    if scaffolding is not None and not isinstance(scaffolding, list):
        issues.append(
            make_issue(
                "error",
                "invalid_scaffolding",
                problem_id,
                "scaffolding",
                "Scaffolding must be a list of step objects.",
            )
        )
    elif isinstance(scaffolding, list):
        observed_steps: list[int] = []
        for position, step in enumerate(scaffolding, start=1):
            if not isinstance(step, dict) or field_is_empty(step.get("hint")):
                issues.append(
                    make_issue(
                        "error",
                        "invalid_scaffolding_step",
                        problem_id,
                        f"scaffolding[{position}]",
                        "Each scaffolding step must be an object with a non-empty hint.",
                    )
                )
                continue
            if isinstance(step.get("step"), int):
                observed_steps.append(step["step"])
        if observed_steps and observed_steps != list(range(1, len(observed_steps) + 1)):
            issues.append(
                make_issue(
                    "warning",
                    "nonsequential_scaffolding",
                    problem_id,
                    "scaffolding",
                    f"Observed step numbers: {observed_steps}.",
                )
            )

    if question_type == "mcq":
        options = problem.get("options")
        answer = str(problem.get("answer") or problem.get("correct_answer") or "").strip().upper()
        if not isinstance(options, dict) or set(options) != {"A", "B", "C", "D"}:
            issues.append(
                make_issue(
                    "error",
                    "invalid_mcq_options",
                    problem_id,
                    "options",
                    "MCQ options must contain exactly A, B, C, and D.",
                )
            )
        if answer not in {"A", "B", "C", "D"}:
            issues.append(
                make_issue(
                    "error",
                    "invalid_mcq_answer",
                    problem_id,
                    "answer",
                    f"MCQ answer must be A-D, found {answer!r}.",
                )
            )
        elif not problem.get("answer") and problem.get("correct_answer"):
            issues.append(
                make_issue(
                    "warning",
                    "legacy_answer_field",
                    problem_id,
                    "correct_answer",
                    "The record uses correct_answer while the current generation/grading schema expects answer.",
                )
            )

    if question_type == "fill_in":
        fill_answers = problem.get("correct_values") or problem.get("correct_answer")
        if field_is_empty(fill_answers):
            issues.append(
                make_issue(
                    "error",
                    "missing_fill_in_answers",
                    problem_id,
                    "correct_values",
                    "Fill-in questions require correct_values or correct_answer.",
                )
            )
        elif not problem.get("correct_values") and problem.get("correct_answer"):
            issues.append(
                make_issue(
                    "warning",
                    "legacy_fill_answer_field",
                    problem_id,
                    "correct_answer",
                    "The record uses correct_answer while the current generation schema expects correct_values.",
                )
            )

    issues.extend(latex_issues(problem, problem_id))
    return issues


def distribution(problems: Iterable[dict[str, Any]], field: str) -> dict[str, int]:
    counts = Counter(
        normalize_text(problem.get(field)) or "(missing)"
        for problem in problems
        if isinstance(problem, dict)
    )
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def duplicate_analysis(
    problems: list[Any], threshold: float
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]]]:
    normalized: list[tuple[int, str, str]] = []
    exact_groups: dict[str, list[str]] = defaultdict(list)
    issues: list[dict[str, str]] = []

    for index, problem in enumerate(problems):
        if not isinstance(problem, dict):
            continue
        problem_id = problem_identifier(problem, index)
        statement = normalize_statement(problem.get("problem_statement"))
        if statement:
            normalized.append((index, problem_id, statement))
            exact_groups[statement].append(problem_id)

    exact_duplicates = [
        {"problem_ids": ids, "count": len(ids)}
        for ids in exact_groups.values()
        if len(ids) > 1
    ]
    for group in exact_duplicates:
        for problem_id in group["problem_ids"]:
            issues.append(
                make_issue(
                    "error",
                    "exact_duplicate_statement",
                    problem_id,
                    "problem_statement",
                    f"Exact normalized duplicate group: {', '.join(group['problem_ids'])}.",
                )
            )

    near_duplicates: list[dict[str, Any]] = []
    for left_pos, (_, left_id, left_text) in enumerate(normalized):
        for _, right_id, right_text in normalized[left_pos + 1 :]:
            if left_text == right_text:
                continue
            length_ratio = min(len(left_text), len(right_text)) / max(len(left_text), len(right_text))
            if length_ratio < 0.75:
                continue
            ratio = SequenceMatcher(None, left_text, right_text, autojunk=False).ratio()
            if ratio >= threshold:
                near_duplicates.append(
                    {
                        "left_problem_id": left_id,
                        "right_problem_id": right_id,
                        "similarity": round(ratio, 4),
                    }
                )
                issues.append(
                    make_issue(
                        "warning",
                        "near_duplicate_statement",
                        left_id,
                        "problem_statement",
                        f"Similarity {ratio:.1%} with {right_id}.",
                    )
                )

    near_duplicates.sort(key=lambda item: item["similarity"], reverse=True)
    return exact_duplicates, near_duplicates, issues


def duplicate_id_issues(problems: list[Any]) -> tuple[list[list[str]], list[dict[str, str]]]:
    positions: dict[str, list[int]] = defaultdict(list)
    for index, problem in enumerate(problems):
        if not isinstance(problem, dict):
            continue
        raw_id = problem.get("problem_id") or problem.get("id")
        if raw_id:
            positions[str(raw_id)].append(index + 1)

    groups = [[problem_id, *map(str, rows)] for problem_id, rows in positions.items() if len(rows) > 1]
    issues = [
        make_issue(
            "error",
            "duplicate_problem_id",
            group[0],
            "problem_id",
            f"The identifier occurs on rows {', '.join(group[1:])}.",
        )
        for group in groups
    ]
    return groups, issues


def build_recommendations(report: dict[str, Any]) -> list[str]:
    recommendations: list[str] = []
    issue_counts = report["summary"]["issues_by_code"]

    if issue_counts.get("duplicate_problem_id") or issue_counts.get("exact_duplicate_statement"):
        recommendations.append("Resolve duplicate IDs/statements before using the dataset as retrieval examples.")
    if issue_counts.get("near_duplicate_statement"):
        recommendations.append("Review near-duplicate pairs and keep only pedagogically distinct variants.")
    if issue_counts.get("missing_core_field"):
        recommendations.append("Backfill required schema fields before generation or grading consumes these records.")
    if issue_counts.get("suspicious_double_backslash") or issue_counts.get("unbalanced_math_delimiter"):
        recommendations.append("Normalize the flagged LaTeX fields and verify them in the current KaTeX frontend.")
    if issue_counts.get("invalid_mcq_options") or issue_counts.get("invalid_mcq_answer"):
        recommendations.append("Repair MCQ option/answer mappings before including those records in evaluation.")
    if issue_counts.get("legacy_answer_field") or issue_counts.get("legacy_fill_answer_field"):
        recommendations.append(
            "Define one canonical answer schema and a backward-compatible loader for answer/correct_answer/correct_values."
        )
    if report["summary"]["evaluation_coverage_percent"] < 100:
        recommendations.append(
            "Treat the current dataset as seed content rather than a fully evaluated benchmark; add reproducible quality results."
        )
    if not recommendations:
        recommendations.append("No structural blockers were found; proceed to sampled mathematical and pedagogical review.")

    recommendations.append(
        "Manually review a stratified sample by topic, difficulty, and question type because structural checks cannot prove mathematical correctness."
    )
    return recommendations


def audit_dataset(dataset_path: Path, near_duplicate_threshold: float) -> dict[str, Any]:
    with dataset_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if isinstance(payload, dict):
        dataset_info = payload.get("dataset_info") or {}
        problems = payload.get("problems")
    elif isinstance(payload, list):
        dataset_info = {}
        problems = payload
    else:
        raise ValueError("Dataset root must be an object with a problems list or a list of problems")

    if not isinstance(problems, list):
        raise ValueError("Dataset does not contain a valid problems list")

    issues: list[dict[str, str]] = []
    for index, problem in enumerate(problems):
        issues.extend(validate_problem(problem, index))

    duplicate_id_groups, id_issues = duplicate_id_issues(problems)
    exact_duplicates, near_duplicates, duplicate_issues = duplicate_analysis(
        problems, near_duplicate_threshold
    )
    issues.extend(id_issues)
    issues.extend(duplicate_issues)

    declared_total = dataset_info.get("total_problems") if isinstance(dataset_info, dict) else None
    if declared_total is not None and declared_total != len(problems):
        issues.append(
            make_issue(
                "error",
                "declared_total_mismatch",
                "DATASET",
                "dataset_info.total_problems",
                f"Metadata declares {declared_total}, but {len(problems)} records were loaded.",
            )
        )

    valid_problem_dicts = [problem for problem in problems if isinstance(problem, dict)]
    evaluated_count = sum(bool(problem.get("evaluation")) for problem in valid_problem_dicts)
    tracked_fields = (*CORE_FIELDS, *ENRICHMENT_FIELDS, "evaluation")
    field_coverage = {
        field: round(
            100
            * sum(not field_is_empty(problem.get(field)) for problem in valid_problem_dicts)
            / len(valid_problem_dicts),
            2,
        )
        if valid_problem_dicts
        else 0.0
        for field in tracked_fields
    }
    issue_severity = Counter(issue["severity"] for issue in issues)
    issue_codes = Counter(issue["code"] for issue in issues)

    report: dict[str, Any] = {
        "audit_metadata": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "dataset_path": portable_dataset_path(dataset_path),
            "near_duplicate_threshold": near_duplicate_threshold,
            "network_calls": 0,
        },
        "dataset_info": dataset_info,
        "summary": {
            "problem_count": len(problems),
            "declared_problem_count": declared_total,
            "valid_object_count": len(valid_problem_dicts),
            "evaluation_coverage_percent": round(
                100 * evaluated_count / len(valid_problem_dicts), 2
            )
            if valid_problem_dicts
            else 0.0,
            "field_coverage_percent": field_coverage,
            "issues_total": len(issues),
            "issues_by_severity": dict(sorted(issue_severity.items())),
            "issues_by_code": dict(sorted(issue_codes.items())),
            "duplicate_id_group_count": len(duplicate_id_groups),
            "exact_duplicate_group_count": len(exact_duplicates),
            "near_duplicate_pair_count": len(near_duplicates),
        },
        "distributions": {
            "topic": distribution(valid_problem_dicts, "topic"),
            "sub_topic": distribution(valid_problem_dicts, "sub_topic"),
            "difficulty": distribution(valid_problem_dicts, "difficulty"),
            "question_type": distribution(valid_problem_dicts, "question_type"),
            "pedagogical_principle": distribution(valid_problem_dicts, "pedagogical_principle"),
        },
        "duplicates": {
            "duplicate_id_groups": duplicate_id_groups,
            "exact_statement_groups": exact_duplicates,
            "near_statement_pairs": near_duplicates,
        },
        "issues": sorted(
            issues,
            key=lambda item: (
                {"error": 0, "warning": 1}.get(item["severity"], 2),
                item["code"],
                item["problem_id"],
            ),
        ),
    }
    report["recommendations"] = build_recommendations(report)
    return report


def markdown_table(distribution_values: dict[str, int], total: int) -> list[str]:
    rows = ["| Value | Count | Share |", "| --- | ---: | ---: |"]
    for value, count in distribution_values.items():
        safe_value = value.replace("|", "\\|")
        share = 100 * count / total if total else 0
        rows.append(f"| {safe_value} | {count} | {share:.1f}% |")
    return rows


def render_markdown(report: dict[str, Any], max_issues: int) -> str:
    summary = report["summary"]
    metadata = report["audit_metadata"]
    severity = summary["issues_by_severity"]

    lines = [
        "# T2P Golden Dataset V3 — Offline Quality Audit",
        "",
        f"- Dataset: `{metadata['dataset_path']}`",
        f"- Generated: `{metadata['generated_at_utc']}`",
        f"- Network/API calls: `{metadata['network_calls']}`",
        f"- Near-duplicate threshold: `{metadata['near_duplicate_threshold']:.0%}`",
        "",
        "## Executive summary",
        "",
        f"- Loaded problems: **{summary['problem_count']}**",
        f"- Declared problems: **{summary['declared_problem_count']}**",
        f"- Evaluation-field coverage: **{summary['evaluation_coverage_percent']:.2f}%**",
        f"- Errors: **{severity.get('error', 0)}**",
        f"- Warnings: **{severity.get('warning', 0)}**",
        f"- Duplicate ID groups: **{summary['duplicate_id_group_count']}**",
        f"- Exact duplicate statement groups: **{summary['exact_duplicate_group_count']}**",
        f"- Near-duplicate statement pairs: **{summary['near_duplicate_pair_count']}**",
        "",
        "Structural checks identify review targets; they do not prove mathematical correctness.",
        "",
        "### Field coverage",
        "",
        "| Field | Coverage |",
        "| --- | ---: |",
    ]
    for field, coverage in summary["field_coverage_percent"].items():
        lines.append(f"| `{field}` | {coverage:.2f}% |")

    lines.extend([
        "",
        "## Distribution baseline",
        "",
    ])

    total = summary["problem_count"]
    for label, key in (
        ("Topics", "topic"),
        ("Difficulty", "difficulty"),
        ("Question types", "question_type"),
        ("Pedagogical principles", "pedagogical_principle"),
    ):
        lines.extend([f"### {label}", ""])
        lines.extend(markdown_table(report["distributions"][key], total))
        lines.append("")

    lines.extend(["## Findings by code", "", "| Code | Count |", "| --- | ---: |"])
    for code, count in report["summary"]["issues_by_code"].items():
        lines.append(f"| `{code}` | {count} |")

    lines.extend(
        [
            "",
            f"## Issue sample (first {min(max_issues, len(report['issues']))})",
            "",
            "| Severity | Problem | Field | Code | Detail |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for issue in report["issues"][:max_issues]:
        values = [
            issue["severity"],
            issue["problem_id"],
            issue["field"],
            issue["code"],
            issue["detail"],
        ]
        escaped = [str(value).replace("|", "\\|").replace("\n", " ") for value in values]
        lines.append("| " + " | ".join(escaped) + " |")

    if len(report["issues"]) > max_issues:
        lines.extend(
            [
                "",
                f"The JSON report contains all {len(report['issues'])} findings.",
            ]
        )

    lines.extend(["", "## Recommended next actions", ""])
    for recommendation in report["recommendations"]:
        lines.append(f"- {recommendation}")

    lines.extend(
        [
            "",
            "## Scope",
            "",
            "This audit is deterministic and offline. It does not modify the dataset, call DeepSeek, "
            "change OCR behavior, or alter application business logic.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    if not 0 < args.near_duplicate_threshold <= 1:
        raise SystemExit("--near-duplicate-threshold must be greater than 0 and at most 1")
    if args.max_markdown_issues < 0:
        raise SystemExit("--max-markdown-issues cannot be negative")

    report = audit_dataset(args.dataset, args.near_duplicate_threshold)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "dataset_audit.json"
    markdown_path = args.output_dir / "dataset_audit.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(
        render_markdown(report, args.max_markdown_issues), encoding="utf-8"
    )

    summary = report["summary"]
    print(f"Audited {summary['problem_count']} problems")
    print(f"Issues: {summary['issues_total']} ({summary['issues_by_severity']})")
    print(f"Markdown report: {markdown_path.resolve()}")
    print(f"JSON report: {json_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
