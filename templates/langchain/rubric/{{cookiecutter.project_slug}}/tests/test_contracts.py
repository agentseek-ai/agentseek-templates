from __future__ import annotations

import inspect
from typing import get_args

import pytest
from langchain_core.messages import AIMessage
from rubric_lab.contracts import (
    BASELINE_RUBRIC,
    DEFAULT_MAX_ITERATIONS,
    MAX_CANDIDATE_CHARS,
    TASK_PROMPT,
    PublicError,
    RubricResult,
    TerminalStatus,
    build_candidate_record,
    build_run_report,
    candidate_id,
    make_public_error,
    normalize_candidate_source,
    validate_run_input,
)

SOURCE = "def find_duplicates(values):\n    return []\n"
CANDIDATE_ID = candidate_id(SOURCE)
CANDIDATES = [
    {
        "grading_run_id": "grading-1",
        "version": 1,
        "iteration": 0,
        "candidate_id": CANDIDATE_ID,
        "source": SOURCE,
    }
]
CURRENT_EVIDENCE = [
    {
        "event_id": "evidence-1",
        "grading_run_id": "grading-1",
        "iteration": 0,
        "candidate_version": 1,
        "requested_candidate_id": CANDIDATE_ID,
        "candidate_id": CANDIDATE_ID,
        "ok": True,
        "behavior_failures": [],
        "profile_failures": [],
        "duration_ms": 1,
        "timed_out": False,
        "output_truncated": False,
    }
]
REPORT_FIELDS = {
    "mode": "demo",
    "thread_id": "outer-1",
    "inner_thread_id": "inner-1",
    "grading_run_id": "grading-1",
    "iterations": 1,
    "candidates": CANDIDATES,
    "final_candidate": SOURCE,
    "evidence": CURRENT_EVIDENCE,
    "evaluations": [],
    "feedback": [],
}


def test_candidate_id_normalizes_newlines_and_complete_python_fences_only() -> None:
    assert candidate_id("x = 1\r\n") == candidate_id("x = 1\n")
    assert candidate_id("```python\nx = 1\n```") == candidate_id("x = 1\n")
    assert candidate_id("```py\nx = 1\n```") == candidate_id("x = 1\n")
    assert candidate_id("x = 1\n") != candidate_id("x = 2\n")


def test_candidate_normalization_extracts_message_text_without_changing_internal_whitespace() -> None:
    message = AIMessage(
        content=[
            {"type": "text", "text": "```python\r\nx = 1  \r\n\r\n```"},
        ]
    )

    assert normalize_candidate_source(message) == "x = 1  \n"
    assert normalize_candidate_source("prefix\n```python\nx = 1\n```\nsuffix") == (
        "prefix\n```python\nx = 1\n```\nsuffix\n"
    )


def test_identical_source_remains_two_correlated_candidate_versions() -> None:
    first = build_candidate_record(
        grading_run_id="grading-1",
        version=1,
        iteration=0,
        source="x = 1\r\n",
    )
    second = build_candidate_record(
        grading_run_id="grading-1",
        version=2,
        iteration=1,
        source="```python\nx = 1\n```",
    )

    assert first["candidate_id"] == second["candidate_id"]
    assert (first["grading_run_id"], first["version"], first["iteration"]) == (
        "grading-1",
        1,
        0,
    )
    assert (second["grading_run_id"], second["version"], second["iteration"]) == (
        "grading-1",
        2,
        1,
    )
    assert first["source"] == second["source"] == "x = 1\n"


def test_candidate_record_accepts_zero_iteration() -> None:
    record = build_candidate_record(
        grading_run_id="grading-1",
        version=1,
        iteration=0,
        source="x = 1\n",
    )

    assert record["iteration"] == 0


def test_run_report_accepts_candidate_history_starting_at_zero() -> None:
    report = build_run_report(terminal_status="satisfied", **REPORT_FIELDS)

    assert report["accepted"] is True


def test_candidate_record_accepts_exact_normalized_source_limit() -> None:
    record = build_candidate_record(
        grading_run_id="grading-1",
        version=1,
        iteration=0,
        source="x" * 3499,
    )

    assert len(record["source"]) == 3500


def test_candidate_record_rejects_normalized_source_above_limit() -> None:
    with pytest.raises(ValueError, match="at most 3500 characters"):
        build_candidate_record(
            grading_run_id="grading-1",
            version=1,
            iteration=0,
            source="x" * 3500,
        )


@pytest.mark.parametrize("version", [0, -1, True, False, 1.0, 1.5, "1"])
def test_candidate_record_rejects_non_positive_or_non_integer_versions(version: object) -> None:
    with pytest.raises(ValueError, match="version must be a positive integer"):
        build_candidate_record(
            grading_run_id="grading-1",
            version=version,  # type: ignore[arg-type]
            iteration=0,
            source="x = 1\n",
        )


@pytest.mark.parametrize("iteration", [-1, True, False, 1.0, 1.5, "1"])
def test_candidate_record_rejects_negative_or_non_integer_iterations(iteration: object) -> None:
    with pytest.raises(ValueError, match="iteration must be a non-negative integer"):
        build_candidate_record(
            grading_run_id="grading-1",
            version=1,
            iteration=iteration,  # type: ignore[arg-type]
            source="x = 1\n",
        )


@pytest.mark.parametrize(
    "versions",
    [
        [1, 1],
        [2, 1],
        [True],
        [1.5],
    ],
)
def test_run_report_rejects_non_monotonic_or_non_integer_candidate_versions(
    versions: list[object],
) -> None:
    candidates = [
        {
            **CANDIDATES[0],
            "version": version,
            "iteration": index + 1,
        }
        for index, version in enumerate(versions)
    ]

    with pytest.raises(ValueError, match="candidate versions must be strictly increasing"):
        build_run_report(
            terminal_status="satisfied",
            **{**REPORT_FIELDS, "candidates": candidates},  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("iteration", [-1, True, 1.5, "0"])
def test_run_report_rejects_negative_or_non_integer_candidate_iterations(
    iteration: object,
) -> None:
    candidate = {**CANDIDATES[0], "iteration": iteration}

    with pytest.raises(ValueError, match="iteration must be a non-negative integer"):
        build_run_report(
            terminal_status="satisfied",
            **{**REPORT_FIELDS, "candidates": [candidate]},  # type: ignore[arg-type]
        )


def test_run_report_rejects_candidate_history_from_another_grading_run() -> None:
    candidates = [
        CANDIDATES[0],
        {
            **CANDIDATES[0],
            "grading_run_id": "grading-other",
            "version": 2,
            "iteration": 2,
        },
    ]

    with pytest.raises(ValueError, match="same grading run"):
        build_run_report(
            terminal_status="satisfied",
            **{**REPORT_FIELDS, "candidates": candidates},
        )


@pytest.mark.parametrize(
    ("status", "accepted", "gate_reason"),
    [
        ("satisfied", True, "satisfied_with_current_evidence"),
        ("max_iterations_reached", False, "terminal_status_not_satisfied"),
        ("failed", False, "terminal_status_not_satisfied"),
        ("grader_error", False, "terminal_status_not_satisfied"),
    ],
)
def test_report_acceptance_requires_terminal_status_and_current_evidence(
    status: TerminalStatus,
    accepted: bool,
    gate_reason: str,
) -> None:
    report = build_run_report(terminal_status=status, **REPORT_FIELDS)

    assert report["accepted"] is accepted
    assert report["gate_reason"] == gate_reason


@pytest.mark.parametrize(
    "evidence_patch",
    [
        {"ok": False},
        {"grading_run_id": "grading-old"},
        {"iteration": 2},
        {"candidate_version": 2},
        {"candidate_id": candidate_id("different = True\n")},
        {"requested_candidate_id": candidate_id("different = True\n")},
    ],
)
def test_satisfied_report_rejects_stale_or_mismatched_evidence(
    evidence_patch: dict[str, object],
) -> None:
    stale = {**CURRENT_EVIDENCE[0], **evidence_patch}

    report = build_run_report(
        terminal_status="satisfied",
        **{**REPORT_FIELDS, "evidence": [stale]},
    )

    assert report["accepted"] is False
    assert report["gate_reason"] == "current_evidence_missing"


def test_report_builder_does_not_accept_a_browser_supplied_acceptance_flag() -> None:
    assert "accepted" not in inspect.signature(build_run_report).parameters


def test_needs_revision_is_an_evaluation_result_not_a_terminal_report() -> None:
    assert "needs_revision" in get_args(RubricResult)
    assert "needs_revision" not in get_args(TerminalStatus)


@pytest.mark.parametrize("cap", [0, -1, True, 1.5, "3"])
def test_run_input_rejects_a_non_positive_or_non_integer_iteration_cap(cap: object) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        validate_run_input({"rubric": BASELINE_RUBRIC, "max_iterations": cap})


def test_run_input_rejects_caps_above_the_characterized_middleware_maximum() -> None:
    with pytest.raises(ValueError, match="at most 20"):
        validate_run_input({"rubric": BASELINE_RUBRIC, "max_iterations": 21})


@pytest.mark.parametrize(
    "unknown_field",
    [
        "accepted",
        "task",
        "candidate",
        "command",
        "api_key",
        "RUBRIC_API_KEY",
        "authorization",
        "access_token",
        "credential",
    ],
)
def test_run_input_rejects_every_unknown_browser_field(unknown_field: str) -> None:
    with pytest.raises(ValueError, match="Unsupported input field"):
        validate_run_input({unknown_field: "attacker-controlled"})


def test_run_input_keeps_the_task_fixed_and_applies_reviewed_defaults() -> None:
    result = validate_run_input({})

    assert result == {
        "rubric": BASELINE_RUBRIC,
        "max_iterations": DEFAULT_MAX_ITERATIONS,
    }
    assert TASK_PROMPT == "Implement find_duplicates(values). Return valid Python source only."
    assert MAX_CANDIDATE_CHARS == 3500


def test_baseline_rubric_has_six_atomic_criteria_and_a_fail_closed_evidence_gate() -> None:
    criteria = [line for line in BASELINE_RUBRIC.splitlines() if line.startswith("- ")]

    assert len(criteria) == 6
    assert "exact current candidate" in criteria[-1]
    assert "run_test_suite" in criteria[-1]
    assert "ok=true" in criteria[-1]


@pytest.mark.parametrize(
    ("code", "message", "missing"),
    [
        ("invalid_input", "Request validation failed.", []),
        ("live_configuration", "Live Model is not configured.", ["OPENAI_API_KEY"]),
        ("runtime", "The run failed safely.", []),
    ],
)
def test_public_errors_use_setup_codes_instead_of_grader_status(
    code: str,
    message: str,
    missing: list[str],
) -> None:
    error: PublicError = make_public_error(code, message, missing=missing)  # type: ignore[arg-type]

    assert error == {"code": code, "message": message, "missing": missing}
    assert error["code"] != "grader_error"
