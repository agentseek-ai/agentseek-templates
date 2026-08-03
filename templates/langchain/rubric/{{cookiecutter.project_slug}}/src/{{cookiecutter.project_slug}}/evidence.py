from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

from langchain_core.tools import BaseTool, tool
from langgraph.config import get_stream_writer

from .contracts import (
    CandidateRecord,
    EvidenceRecord,
    EvidenceResult,
    build_candidate_record,
    candidate_id,
)
from .runner import execute_candidate


@dataclass(slots=True)
class RunEvidenceLedger:
    grading_run_id: str
    candidates: list[CandidateRecord] = field(default_factory=list)
    evidence: list[EvidenceRecord] = field(default_factory=list)

    @property
    def current_candidate(self) -> CandidateRecord | None:
        return self.candidates[-1] if self.candidates else None

    def record_candidate(self, source: str, iteration: int) -> CandidateRecord:
        candidate = build_candidate_record(
            grading_run_id=self.grading_run_id,
            version=len(self.candidates) + 1,
            iteration=iteration,
            source=source,
        )
        self.candidates.append(candidate)
        return candidate

    def record_evidence(
        self,
        result: EvidenceResult,
        *,
        candidate: CandidateRecord | None,
        requested_candidate_id: str,
    ) -> EvidenceRecord:
        if candidate is None:
            raise RuntimeError("candidate must be recorded before evidence")
        record: EvidenceRecord = {
            "event_id": f"{candidate['grading_run_id']}:evidence:{candidate['version']}:{len(self.evidence)}",
            "grading_run_id": candidate["grading_run_id"],
            "candidate_version": candidate["version"],
            "iteration": candidate["iteration"],
            "candidate_id": candidate["candidate_id"],
            "requested_candidate_id": requested_candidate_id,
            "ok": result["ok"],
            "behavior_failures": list(result["behavior_failures"]),
            "profile_failures": list(result["profile_failures"]),
            "duration_ms": result["duration_ms"],
            "timed_out": result["timed_out"],
            "output_truncated": result["output_truncated"],
        }
        self.evidence.append(record)
        return record


def candidate_binding_failure(requested_candidate_id: str, current: CandidateRecord | None) -> EvidenceResult:
    return {
        "candidate_id": current["candidate_id"] if current is not None else requested_candidate_id,
        "ok": False,
        "behavior_failures": [],
        "profile_failures": ["candidate_binding"],
        "duration_ms": 0,
        "timed_out": False,
        "output_truncated": False,
    }


def emit_custom_event(payload: dict[str, object]) -> None:
    try:
        writer = get_stream_writer()
    except (KeyError, RuntimeError):
        return
    writer(payload)


def make_run_test_suite(ledger: RunEvidenceLedger) -> BaseTool:
    @tool("run_test_suite")
    def run_test_suite(code: str) -> dict[str, object]:
        """Run the fixed find_duplicates evidence suite for this candidate source."""
        requested_id = candidate_id(code)
        tracked_candidate = ledger.current_candidate
        current = cast(CandidateRecord, dict(tracked_candidate)) if tracked_candidate is not None else None
        current_source_id = candidate_id(current["source"]) if current is not None else None
        if current is None or current_source_id != current["candidate_id"] or requested_id != current["candidate_id"]:
            result = candidate_binding_failure(requested_id, current)
        else:
            result = execute_candidate(current["source"])
        record = ledger.record_evidence(
            result,
            candidate=current,
            requested_candidate_id=requested_id,
        )
        emit_custom_event({"type": "rubric_evidence", **record})
        return record

    return run_test_suite
