from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Literal, NotRequired, TypedDict, cast

RunMode = Literal["demo", "live"]
RubricResult = Literal[
    "satisfied",
    "needs_revision",
    "max_iterations_reached",
    "failed",
    "grader_error",
]
TerminalStatus = Literal[
    "satisfied",
    "max_iterations_reached",
    "failed",
    "grader_error",
]
GateReason = Literal[
    "satisfied_with_current_evidence",
    "terminal_status_not_satisfied",
    "current_evidence_missing",
]
PublicErrorCode = Literal["invalid_input", "live_configuration", "runtime"]
UIEventType = Literal[
    "candidate",
    "grader_feedback",
    "rubric_evidence",
    "rubric_evaluation_start",
    "rubric_evaluation_end",
]

TASK_PROMPT = "Implement find_duplicates(values). Return valid Python source only."
BASELINE_RUBRIC = """\
- The response is valid Python source that defines find_duplicates(values).
- Each duplicated value appears exactly once in the returned list.
- Result order follows when each value first becomes a duplicate.
- Unhashable values such as nested lists are supported.
- The input sequence is not mutated.
- Before satisfied, call run_test_suite with the exact current candidate and receive ok=true.
"""
DEFAULT_MAX_ITERATIONS = 3
MAX_ITERATIONS = 20
MAX_CANDIDATE_CHARS = 3500
UI_EVENT_TYPES: tuple[UIEventType, ...] = (
    "candidate",
    "grader_feedback",
    "rubric_evidence",
    "rubric_evaluation_start",
    "rubric_evaluation_end",
)


class RunInput(TypedDict):
    rubric: str
    max_iterations: int


class EvidenceResult(TypedDict):
    candidate_id: str
    ok: bool
    behavior_failures: list[str]
    profile_failures: list[str]
    duration_ms: int
    timed_out: bool
    output_truncated: bool


class CandidateRecord(TypedDict):
    grading_run_id: str
    version: int
    iteration: int
    candidate_id: str
    source: str | None
    source_omitted: NotRequired[bool]


class EvidenceRecord(EvidenceResult):
    event_id: str
    grading_run_id: str
    iteration: int
    candidate_version: int
    requested_candidate_id: str


class CriterionResult(TypedDict):
    criterion: str
    passed: bool
    gap: str


class EvaluationEvent(TypedDict):
    event_id: str
    grading_run_id: str
    iteration: int
    candidate_version: int | None
    candidate_id: str | None
    result: RubricResult
    explanation: str
    criteria: list[CriterionResult]


class FeedbackRecord(TypedDict):
    event_id: str
    grading_run_id: str
    iteration: int
    candidate_version: int | None
    candidate_id: str | None
    message: str


class RunReport(TypedDict):
    mode: RunMode
    thread_id: str
    inner_thread_id: str
    grading_run_id: str
    terminal_status: TerminalStatus
    accepted: bool
    gate_reason: GateReason
    iterations: int
    candidates: list[CandidateRecord]
    final_candidate: str | None
    evidence: list[EvidenceRecord]
    evaluations: list[EvaluationEvent]
    feedback: list[FeedbackRecord]


class PublicError(TypedDict):
    code: PublicErrorCode
    message: str
    missing: list[str]


class UIEvent(TypedDict):
    event_id: str
    type: UIEventType
    grading_run_id: str
    iteration: int
    candidate_version: int | None
    candidate_id: str | None
    payload: dict[str, object]


_COMPLETE_PYTHON_FENCE = re.compile(
    r"\A[ \t]*```(?:python|py)[ \t]*\n(?P<source>.*)\n```[ \t]*\Z",
    flags=re.IGNORECASE | re.DOTALL,
)
_ALLOWED_INPUT_FIELDS = frozenset({"rubric", "max_iterations"})


class CandidateTooLongError(ValueError):
    """The normalized Worker output cannot cross the public/execution boundary."""


def _extract_text_content(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        text = value.get("text")
        return text if isinstance(text, str) else ""
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return "".join(_extract_text_content(item) for item in value)
    content = getattr(value, "content", None)
    if content is not None and content is not value:
        return _extract_text_content(content)
    raise TypeError("Candidate content must contain text.")


def normalize_candidate_source(value: object) -> str:
    """Return the one source representation used for hashing and execution."""
    source = _extract_text_content(value).replace("\r\n", "\n").replace("\r", "\n")
    if match := _COMPLETE_PYTHON_FENCE.fullmatch(source):
        source = match.group("source")
    return source.rstrip("\n") + "\n"


def candidate_id(value: object) -> str:
    source = normalize_candidate_source(value)
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _require_positive_integer(value: object, name: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _require_non_negative_integer(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _require_candidate_source_limit(source: str) -> None:
    if len(source) > MAX_CANDIDATE_CHARS:
        raise CandidateTooLongError(f"normalized candidate source must be at most {MAX_CANDIDATE_CHARS} characters")


def build_candidate_record(
    *,
    grading_run_id: str,
    version: int,
    iteration: int,
    source: object,
) -> CandidateRecord:
    version = _require_positive_integer(version, "candidate version")
    iteration = _require_non_negative_integer(iteration, "candidate iteration")
    normalized = normalize_candidate_source(source)
    _require_candidate_source_limit(normalized)
    return {
        "grading_run_id": grading_run_id,
        "version": version,
        "iteration": iteration,
        "candidate_id": candidate_id(normalized),
        "source": normalized,
    }


def build_rejected_candidate_record(
    *,
    grading_run_id: str,
    version: int,
    iteration: int,
    source: object,
) -> CandidateRecord:
    """Retain only identity for an oversized candidate, never an executable prefix."""
    version = _require_positive_integer(version, "candidate version")
    iteration = _require_non_negative_integer(iteration, "candidate iteration")
    normalized = normalize_candidate_source(source)
    if len(normalized) <= MAX_CANDIDATE_CHARS:
        raise ValueError("rejected candidate source must exceed the public source limit")
    return {
        "grading_run_id": grading_run_id,
        "version": version,
        "iteration": iteration,
        "candidate_id": candidate_id(normalized),
        "source": None,
        "source_omitted": True,
    }


def _validate_candidate_history(
    grading_run_id: str,
    candidates: Sequence[CandidateRecord],
) -> None:
    previous_version = 0
    for candidate in candidates:
        if candidate["grading_run_id"] != grading_run_id:
            raise ValueError("candidate history must belong to the same grading run")
        version = candidate["version"]
        if type(version) is not int or version <= previous_version:
            raise ValueError("candidate versions must be strictly increasing positive integers")
        _require_non_negative_integer(candidate["iteration"], "candidate iteration")
        if candidate.get("source_omitted") is True:
            if candidate["source"] is not None or re.fullmatch(r"[0-9a-f]{64}", candidate["candidate_id"]) is None:
                raise ValueError("omitted candidate source must retain only a valid candidate ID")
        else:
            normalized_source = normalize_candidate_source(candidate["source"])
            _require_candidate_source_limit(normalized_source)
            if candidate["candidate_id"] != candidate_id(normalized_source):
                raise ValueError("candidate ID must match normalized source")
        previous_version = version


def validate_run_input(value: Mapping[str, object]) -> RunInput:
    unknown = sorted(set(value) - _ALLOWED_INPUT_FIELDS)
    if unknown:
        raise ValueError(f"Unsupported input field: {unknown[0]}")

    rubric = value.get("rubric", BASELINE_RUBRIC)
    if not isinstance(rubric, str) or not rubric.strip():
        raise ValueError("rubric must be a non-empty string")

    max_iterations = value.get("max_iterations", DEFAULT_MAX_ITERATIONS)
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations < 1:
        raise ValueError("max_iterations must be a positive integer")
    if max_iterations > MAX_ITERATIONS:
        raise ValueError(f"max_iterations must be at most {MAX_ITERATIONS}")

    return {"rubric": rubric, "max_iterations": max_iterations}


def make_public_error(
    code: PublicErrorCode,
    message: str,
    *,
    missing: Sequence[str] = (),
) -> PublicError:
    return {"code": code, "message": message, "missing": list(missing)}


def _has_current_passing_evidence(
    *,
    grading_run_id: str,
    final_candidate: str | None,
    candidates: Sequence[CandidateRecord],
    evidence: Sequence[EvidenceRecord],
) -> bool:
    if final_candidate is None or not candidates:
        return False

    current = candidates[-1]
    if current.get("source_omitted") is True or current["source"] is None:
        return False
    normalized_final = normalize_candidate_source(final_candidate)
    current_id = candidate_id(normalized_final)
    if (
        current["grading_run_id"] != grading_run_id
        or current["candidate_id"] != current_id
        or normalize_candidate_source(current["source"]) != normalized_final
    ):
        return False

    return any(
        record["grading_run_id"] == grading_run_id
        and record["iteration"] == current["iteration"]
        and record["candidate_version"] == current["version"]
        and record["candidate_id"] == current_id
        and record["requested_candidate_id"] == current_id
        and record["ok"] is True
        and record["timed_out"] is False
        and record["output_truncated"] is False
        for record in evidence
    )


def build_run_report(
    *,
    mode: RunMode,
    thread_id: str,
    inner_thread_id: str,
    grading_run_id: str,
    terminal_status: TerminalStatus,
    iterations: int,
    candidates: Sequence[CandidateRecord],
    final_candidate: str | None,
    evidence: Sequence[EvidenceRecord],
    evaluations: Sequence[EvaluationEvent],
    feedback: Sequence[FeedbackRecord],
) -> RunReport:
    _validate_candidate_history(grading_run_id, candidates)
    normalized_final = None if final_candidate is None else normalize_candidate_source(final_candidate)
    if terminal_status != "satisfied":
        accepted = False
        gate_reason: GateReason = "terminal_status_not_satisfied"
    elif _has_current_passing_evidence(
        grading_run_id=grading_run_id,
        final_candidate=normalized_final,
        candidates=candidates,
        evidence=evidence,
    ):
        accepted = True
        gate_reason = "satisfied_with_current_evidence"
    else:
        accepted = False
        gate_reason = "current_evidence_missing"

    return {
        "mode": mode,
        "thread_id": thread_id,
        "inner_thread_id": inner_thread_id,
        "grading_run_id": grading_run_id,
        "terminal_status": terminal_status,
        "accepted": accepted,
        "gate_reason": gate_reason,
        "iterations": iterations,
        "candidates": [cast(CandidateRecord, dict(item)) for item in candidates],
        "final_candidate": normalized_final,
        "evidence": [cast(EvidenceRecord, dict(item)) for item in evidence],
        "evaluations": [cast(EvaluationEvent, dict(item)) for item in evaluations],
        "feedback": [cast(FeedbackRecord, dict(item)) for item in feedback],
    }
