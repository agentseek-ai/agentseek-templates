from __future__ import annotations

import asyncio
import contextvars
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import cast

from langchain_core.tools import BaseTool, StructuredTool
from langgraph.config import get_stream_writer

from .contracts import (
    CandidateRecord,
    CandidateTooLongError,
    EvidenceRecord,
    EvidenceResult,
    build_candidate_record,
    build_rejected_candidate_record,
    candidate_id,
)
from .runner import CandidateExecutionCancelled, candidate_cancellation_scope, execute_candidate


@dataclass(slots=True)
class RunEvidenceLedger:
    grading_run_id: str
    candidates: list[CandidateRecord] = field(default_factory=list)
    evidence: list[EvidenceRecord] = field(default_factory=list)

    @property
    def current_candidate(self) -> CandidateRecord | None:
        return self.candidates[-1] if self.candidates else None

    def record_candidate(self, source: str, iteration: int) -> CandidateRecord:
        version = len(self.candidates) + 1
        try:
            candidate = build_candidate_record(
                grading_run_id=self.grading_run_id,
                version=version,
                iteration=iteration,
                source=source,
            )
        except CandidateTooLongError:
            candidate = build_rejected_candidate_record(
                grading_run_id=self.grading_run_id,
                version=version,
                iteration=iteration,
                source=source,
            )
            self.candidates.append(candidate)
            self.record_evidence(
                {
                    "candidate_id": candidate["candidate_id"],
                    "ok": False,
                    "behavior_failures": [],
                    "profile_failures": ["candidate_too_long"],
                    "duration_ms": 0,
                    "timed_out": False,
                    "output_truncated": False,
                },
                candidate=candidate,
                requested_candidate_id=candidate["candidate_id"],
            )
            raise
        else:
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


def _prepare_execution(
    ledger: RunEvidenceLedger,
    code: str,
) -> tuple[str, CandidateRecord | None, EvidenceResult | None]:
    requested_id = candidate_id(code)
    tracked_candidate = ledger.current_candidate
    current = cast(CandidateRecord, dict(tracked_candidate)) if tracked_candidate is not None else None
    current_source = current["source"] if current is not None else None
    current_source_id = candidate_id(current_source) if isinstance(current_source, str) else None
    if current is None or current_source_id != current["candidate_id"] or requested_id != current["candidate_id"]:
        return requested_id, current, candidate_binding_failure(requested_id, current)
    return requested_id, current, None


def _record_result(
    ledger: RunEvidenceLedger,
    result: EvidenceResult,
    *,
    current: CandidateRecord | None,
    requested_id: str,
) -> dict[str, object]:
    record = ledger.record_evidence(
        result,
        candidate=current,
        requested_candidate_id=requested_id,
    )
    emit_custom_event({"type": "rubric_evidence", **record})
    return record


@dataclass(slots=True)
class _CandidateExecutionOutcome:
    result: EvidenceResult | None = None
    error: BaseException | None = None


def _capture_candidate_execution(source: str) -> _CandidateExecutionOutcome:
    try:
        return _CandidateExecutionOutcome(result=execute_candidate(source))
    except BaseException as error:
        return _CandidateExecutionOutcome(error=error)


async def _execute_candidate_async(source: str) -> EvidenceResult:
    cancellation_event = threading.Event()
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rubric-candidate")
    try:
        with candidate_cancellation_scope(cancellation_event):
            context = contextvars.copy_context()
        concurrent_future = executor.submit(context.run, _capture_candidate_execution, source)
        execution = asyncio.wrap_future(concurrent_future)
        try:
            outcome = await asyncio.shield(execution)
        except asyncio.CancelledError as cancellation:
            cancellation_event.set()
            while not execution.done():
                try:
                    await asyncio.shield(execution)
                except asyncio.CancelledError:
                    continue
            outcome = execution.result()
            if outcome.error is not None and not isinstance(outcome.error, CandidateExecutionCancelled):
                cancellation.add_note(f"candidate cleanup raised {type(outcome.error).__name__}")
            raise
        if outcome.error is not None:
            raise outcome.error
        if outcome.result is None:
            raise RuntimeError("candidate execution produced no result")
        return outcome.result
    finally:
        executor.shutdown(wait=True, cancel_futures=False)


def make_run_test_suite(ledger: RunEvidenceLedger) -> BaseTool:
    def run_test_suite(code: str) -> dict[str, object]:
        """Run the fixed find_duplicates evidence suite for this candidate source."""
        requested_id, current, result = _prepare_execution(ledger, code)
        if result is None:
            result = execute_candidate(cast(str, current["source"]))
        return _record_result(
            ledger,
            result,
            current=current,
            requested_id=requested_id,
        )

    async def arun_test_suite(code: str) -> dict[str, object]:
        """Run the fixed suite and synchronously reap its child when cancelled."""
        requested_id, current, result = _prepare_execution(ledger, code)
        if result is None:
            result = await _execute_candidate_async(cast(str, current["source"]))
        return _record_result(
            ledger,
            result,
            current=current,
            requested_id=requested_id,
        )

    return StructuredTool.from_function(
        func=run_test_suite,
        coroutine=arun_test_suite,
        name="run_test_suite",
        description="Run the fixed find_duplicates evidence suite for this candidate source.",
    )
