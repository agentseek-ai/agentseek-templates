from __future__ import annotations

import asyncio
import subprocess
import threading
from typing import Any

import pytest

from {{ cookiecutter.project_slug }} import evidence, runner
from {{ cookiecutter.project_slug }}.contracts import candidate_id, normalize_candidate_source
from {{ cookiecutter.project_slug }}.evidence import RunEvidenceLedger, make_run_test_suite

PASSING_SOURCE = """\
def find_duplicates(values):
    seen = []
    duplicates = []
    for value in values:
        if value in seen:
            if value not in duplicates:
                duplicates.append(value)
        else:
            seen.append(value)
    return duplicates
"""

FAILING_SOURCE = """\
def find_duplicates(values):
    return []
"""

INFINITE_SOURCE = """\
def find_duplicates(values):
    while True:
        pass
"""


def test_tool_records_current_candidate_identity_and_emits_the_same_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[dict[str, object]] = []
    monkeypatch.setattr(evidence, "emit_custom_event", events.append)
    ledger = RunEvidenceLedger(grading_run_id="grading-1")
    candidate = ledger.record_candidate(PASSING_SOURCE, iteration=0)

    record = make_run_test_suite(ledger).invoke({"code": PASSING_SOURCE})

    assert record["ok"] is True
    assert (record["grading_run_id"], record["iteration"], record["candidate_version"]) == (
        "grading-1",
        0,
        1,
    )
    assert record["candidate_id"] == record["requested_candidate_id"] == candidate["candidate_id"]
    assert record["event_id"] == "grading-1:evidence:1:0"
    assert ledger.evidence == [record]
    assert events == [{"type": "rubric_evidence", **record}]


def test_mismatched_tool_source_is_bound_as_failure_without_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = RunEvidenceLedger(grading_run_id="grading-1")
    current = ledger.record_candidate(PASSING_SOURCE, iteration=2)
    monkeypatch.setattr(
        evidence,
        "execute_candidate",
        lambda source: (_ for _ in ()).throw(AssertionError("mismatched source was executed")),
    )
    monkeypatch.setattr(evidence, "emit_custom_event", lambda event: None)

    record = make_run_test_suite(ledger).invoke({"code": FAILING_SOURCE})

    assert record["ok"] is False
    assert record["profile_failures"] == ["candidate_binding"]
    assert record["candidate_id"] == current["candidate_id"]
    assert record["requested_candidate_id"] == candidate_id(FAILING_SOURCE)


def test_tampered_tracked_source_is_bound_as_failure_without_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = RunEvidenceLedger(grading_run_id="grading-1")
    current = ledger.record_candidate(PASSING_SOURCE, iteration=2)
    current["source"] = FAILING_SOURCE
    monkeypatch.setattr(
        evidence,
        "execute_candidate",
        lambda source: (_ for _ in ()).throw(AssertionError("tampered tracked source was executed")),
    )
    monkeypatch.setattr(evidence, "emit_custom_event", lambda event: None)

    record = make_run_test_suite(ledger).invoke({"code": PASSING_SOURCE})

    assert record["ok"] is False
    assert record["profile_failures"] == ["candidate_binding"]
    assert record["candidate_id"] == candidate_id(PASSING_SOURCE)


def test_malformed_current_candidate_returns_profile_failure_outside_graph_context() -> None:
    source = "def find_duplicates(values):\n    return [\n"
    ledger = RunEvidenceLedger(grading_run_id="grading-malformed")
    ledger.record_candidate(source, iteration=0)

    record = make_run_test_suite(ledger).invoke({"code": source})

    assert record["ok"] is False
    assert record["behavior_failures"] == []
    assert record["profile_failures"] == ["candidate_load"]


def test_hash_equivalent_request_executes_the_normalized_ledger_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executed: list[str] = []
    ledger = RunEvidenceLedger(grading_run_id="grading-1")
    current = ledger.record_candidate(PASSING_SOURCE, iteration=1)
    monkeypatch.setattr(evidence, "emit_custom_event", lambda event: None)

    def execute(source: str) -> dict[str, object]:
        executed.append(source)
        return {
            "candidate_id": candidate_id(source),
            "ok": True,
            "behavior_failures": [],
            "profile_failures": [],
            "duration_ms": 1,
            "timed_out": False,
            "output_truncated": False,
        }

    monkeypatch.setattr(evidence, "execute_candidate", execute)

    record = make_run_test_suite(ledger).invoke({"code": f"```python\n{PASSING_SOURCE.rstrip()}\n```"})

    assert record["ok"] is True
    assert executed == [current["source"]]
    assert executed[0] == normalize_candidate_source(PASSING_SOURCE)


def test_evidence_remains_bound_when_ledger_advances_during_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = RunEvidenceLedger(grading_run_id="grading-atomic")
    current = ledger.record_candidate(PASSING_SOURCE, iteration=0)
    monkeypatch.setattr(evidence, "emit_custom_event", lambda event: None)

    def execute(source: str) -> dict[str, object]:
        ledger.record_candidate(FAILING_SOURCE, iteration=1)
        return {
            "candidate_id": candidate_id(source),
            "ok": True,
            "behavior_failures": [],
            "profile_failures": [],
            "duration_ms": 1,
            "timed_out": False,
            "output_truncated": False,
        }

    monkeypatch.setattr(evidence, "execute_candidate", execute)

    record = make_run_test_suite(ledger).invoke({"code": PASSING_SOURCE})

    assert record["candidate_version"] == current["version"] == 1
    assert record["iteration"] == current["iteration"] == 0
    assert record["candidate_id"] == current["candidate_id"]
    assert record["event_id"] == "grading-atomic:evidence:1:0"
    assert ledger.current_candidate is not None
    assert ledger.current_candidate["version"] == 2


def test_identical_source_across_iterations_keeps_version_at_execution_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(evidence, "emit_custom_event", lambda event: None)
    ledger = RunEvidenceLedger(grading_run_id="grading-versions")
    tool = make_run_test_suite(ledger)

    first_candidate = ledger.record_candidate(PASSING_SOURCE, iteration=0)
    first_evidence = tool.invoke({"code": PASSING_SOURCE})
    second_candidate = ledger.record_candidate(PASSING_SOURCE, iteration=1)
    second_evidence = tool.invoke({"code": PASSING_SOURCE})

    assert first_candidate["candidate_id"] == second_candidate["candidate_id"]
    assert (first_candidate["version"], second_candidate["version"]) == (1, 2)
    assert (first_evidence["candidate_version"], first_evidence["iteration"]) == (1, 0)
    assert (second_evidence["candidate_version"], second_evidence["iteration"]) == (2, 1)
    assert first_evidence["event_id"] == "grading-versions:evidence:1:0"
    assert second_evidence["event_id"] == "grading-versions:evidence:2:1"


def test_recording_evidence_without_a_candidate_is_rejected() -> None:
    ledger = RunEvidenceLedger(grading_run_id="grading-empty")
    result = {
        "candidate_id": candidate_id(PASSING_SOURCE),
        "ok": False,
        "behavior_failures": [],
        "profile_failures": ["candidate_binding"],
        "duration_ms": 0,
        "timed_out": False,
        "output_truncated": False,
    }

    with pytest.raises(RuntimeError, match="candidate must be recorded before evidence"):
        ledger.record_evidence(
            result,
            candidate=None,
            requested_candidate_id=candidate_id(PASSING_SOURCE),
        )


@pytest.mark.asyncio
async def test_async_tool_cancellation_reaps_real_candidate_before_returning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    processes: list[subprocess.Popen[bytes]] = []
    process_started = threading.Event()
    execution_finished = threading.Event()
    loop_errors: list[dict[str, Any]] = []
    real_execute_candidate = evidence.execute_candidate
    loop = asyncio.get_running_loop()
    previous_exception_handler = loop.get_exception_handler()

    def capture_loop_error(
        event_loop: asyncio.AbstractEventLoop,
        context: dict[str, Any],
    ) -> None:
        del event_loop
        loop_errors.append(context)

    def process_factory(*args: Any, **kwargs: Any) -> subprocess.Popen[bytes]:
        process = subprocess.Popen(*args, **kwargs)
        processes.append(process)
        process_started.set()
        return process

    def observed_execute_candidate(source: str, **kwargs: Any) -> dict[str, object]:
        try:
            return real_execute_candidate(source, **kwargs)
        finally:
            execution_finished.set()

    monkeypatch.setattr(runner, "_PROCESS_FACTORY", process_factory)
    monkeypatch.setattr(evidence, "execute_candidate", observed_execute_candidate)
    monkeypatch.setattr(evidence, "emit_custom_event", lambda event: None)
    ledger = RunEvidenceLedger(grading_run_id="grading-cancel")
    ledger.record_candidate(INFINITE_SOURCE, iteration=0)
    suite = make_run_test_suite(ledger)
    task = asyncio.create_task(suite.ainvoke({"code": INFINITE_SOURCE}))
    loop.set_exception_handler(capture_loop_error)

    try:
        assert await asyncio.wait_for(asyncio.to_thread(process_started.wait, 1.0), timeout=1.5)

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=1.0)

        assert execution_finished.is_set()
        assert processes and all(process.poll() is not None for process in processes)
        assert not any(thread.is_alive() and thread.name.startswith("rubric-") for thread in threading.enumerate())
        assert getattr(suite, "coroutine", None) is not None
        assert ledger.evidence == []
        await asyncio.sleep(0)
        assert loop_errors == []
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=1.0)
        await asyncio.to_thread(execution_finished.wait, 3.0)
        loop.set_exception_handler(previous_exception_handler)
