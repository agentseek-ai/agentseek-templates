from __future__ import annotations

import asyncio
import sys
import uuid

from .contracts import BASELINE_RUBRIC, DEFAULT_MAX_ITERATIONS, RunReport
from .graphs import make_demo_graph


async def _run_smoke() -> tuple[list[dict[str, object]], RunReport]:
    graph = make_demo_graph()
    events: list[dict[str, object]] = []
    report: RunReport | None = None
    async for stream_mode, chunk in graph.astream(
        {
            "request": {
                "rubric": BASELINE_RUBRIC,
                "max_iterations": DEFAULT_MAX_ITERATIONS,
            }
        },
        config={"configurable": {"thread_id": str(uuid.uuid4())}},
        stream_mode=["updates", "custom"],
    ):
        if stream_mode == "custom":
            events.append(chunk)
        elif isinstance(chunk, dict) and isinstance(chunk.get("run"), dict):
            report = chunk["run"].get("report")
    if report is None:
        raise AssertionError("Demo did not produce an authoritative report")
    return events, report


def _verify(events: list[dict[str, object]], report: RunReport) -> None:
    del events
    evaluation_results = [item["result"] for item in report["evaluations"]]
    evidence_by_version = {item["candidate_version"]: item for item in report["evidence"]}
    assert evaluation_results == ["needs_revision", "satisfied"]
    assert report["terminal_status"] == "satisfied"
    assert report["accepted"] is True
    assert report["iterations"] == 2
    assert report["gate_reason"] == "satisfied_with_current_evidence"
    assert evidence_by_version[report["candidates"][-1]["version"]]["ok"] is True
    assert evidence_by_version[report["candidates"][-1]["version"]]["output_truncated"] is False, (
        "final Evidence output was truncated"
    )


def _print_summary(report: RunReport) -> None:
    for candidate in report["candidates"]:
        print(f"candidate_version={candidate['version']} candidate_id={candidate['candidate_id']}")
    for evidence in report["evidence"]:
        ok = str(evidence["ok"]).lower()
        print(f"evidence_version={evidence['candidate_version']} ok={ok}")
    results = ",".join(item["result"] for item in report["evaluations"])
    print(f"evaluation_results={results}")
    accepted = str(report["accepted"]).lower()
    print(f"gate={report['gate_reason']} accepted={accepted}")


def main() -> int:
    try:
        events, report = asyncio.run(_run_smoke())
        _verify(events, report)
    except (AssertionError, KeyError, RuntimeError, TypeError, ValueError) as exc:
        print(f"rubric smoke contract failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    _print_summary(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
