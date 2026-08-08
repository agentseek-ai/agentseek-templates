from __future__ import annotations

import asyncio
import json
import logging
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool
from pydantic import PrivateAttr

from {{ cookiecutter.project_slug }} import evidence
from {{ cookiecutter.project_slug }}.contracts import BASELINE_RUBRIC, build_run_report, candidate_id
from {{ cookiecutter.project_slug }}.demo_models import (
    DEMO_FAILING_SOURCE,
    DemoWorkerModel,
    ScriptedGraderModel,
    build_demo_models,
)
from {{ cookiecutter.project_slug }}.graphs import (
    build_application_graph,
    make_demo_graph,
    make_live_graph,
    reconcile_public_events,
)
from {{ cookiecutter.project_slug }}.models import SanitizingChatModel

SENTINEL = "SENTINEL_SECRET_7f2c"
SensitiveProviderError = type(f"SensitiveProviderError_{SENTINEL}", (Exception,), {})


async def _stream(graph: Any, request: dict[str, object], thread_id: str):
    events: list[dict[str, object]] = []
    report: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    async for stream_mode, chunk in graph.astream(
        {"request": request},
        config={"configurable": {"thread_id": thread_id}},
        stream_mode=["updates", "custom"],
    ):
        if stream_mode == "custom":
            events.append(chunk)
        elif "run" in chunk:
            report = chunk["run"].get("report")
            error = chunk["run"].get("error")
    return events, report, error


def _assert_correlated(report: dict[str, Any]) -> None:
    candidates = {(item["version"], item["candidate_id"]) for item in report["candidates"]}
    for item in [*report["evidence"], *report["evaluations"], *report["feedback"]]:
        assert item["grading_run_id"] == report["grading_run_id"]
        if item["candidate_version"] is not None:
            assert (item["candidate_version"], item["candidate_id"]) in candidates


@pytest.mark.asyncio
async def test_demo_reports_are_isolated_complete_and_keyless(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    first = await make_demo_graph().ainvoke({"request": {}}, config={"configurable": {"thread_id": "outer-one"}})
    second = await make_demo_graph().ainvoke({"request": {}}, config={"configurable": {"thread_id": "outer-two"}})

    first_report = first["report"]
    second_report = second["report"]
    assert first_report["thread_id"] == "outer-one"
    assert second_report["thread_id"] == "outer-two"
    assert first_report["inner_thread_id"] != second_report["inner_thread_id"]
    assert first_report["grading_run_id"] != second_report["grading_run_id"]
    for report in (first_report, second_report):
        assert report["terminal_status"] == "satisfied"
        assert report["accepted"] is True
        assert report["iterations"] == 2
        assert len(report["candidates"]) == len(report["evidence"]) == len(report["evaluations"]) == 2
        assert report["feedback"]
        _assert_correlated(report)
        serialized = json.dumps(report)
        for forbidden in ("_rubric_status", "_rubric_evaluations", "api_key", "authorization"):
            assert forbidden not in serialized.lower()


@pytest.mark.asyncio
async def test_stream_events_agree_with_authoritative_report_and_reconcile_dropped_replays() -> None:
    events, report, error = await _stream(make_demo_graph(), {}, "outer-events")

    assert error is None
    assert report is not None
    final_evaluation = [event for event in events if event["type"] == "rubric_evaluation_end"][-1]
    assert final_evaluation["grading_run_id"] == report["grading_run_id"]
    assert final_evaluation["payload"]["result"] == report["terminal_status"]
    assert report["accepted"] is True
    assert report["gate_reason"] == "satisfied_with_current_evidence"
    candidate_pairs = {
        (event["candidate_version"], event["candidate_id"]) for event in events if event["type"] == "candidate"
    }
    for event in events:
        if event["type"] == "rubric_evidence":
            assert (event["candidate_version"], event["candidate_id"]) in candidate_pairs
    assert [event["type"] for event in events].count("grader_feedback") == 1
    assert "user_message" not in [event["type"] for event in events]

    damaged = list(reversed(events[1:] + events[:2] + events[:1]))
    reconciled = reconcile_public_events(damaged, report)
    assert reconciled == reconcile_public_events(list(reversed(damaged)), report)
    assert len({event["event_id"] for event in reconciled}) == len(reconciled)
    assert len([event for event in reconciled if event["type"] == "candidate"]) == len(report["candidates"])
    assert len([event for event in reconciled if event["type"] == "rubric_evidence"]) == len(report["evidence"])
    assert len([event for event in reconciled if event["type"] == "rubric_evaluation_end"]) == len(
        report["evaluations"]
    )


@pytest.mark.asyncio
async def test_live_uses_invocation_time_models_and_iteration_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    from {{ cookiecutter.project_slug }} import graphs

    calls: list[object] = []
    monkeypatch.setattr(graphs, "resolve_live_config", lambda: calls.append("resolved") or object())
    monkeypatch.setattr(graphs, "build_live_models", lambda config: calls.append(config) or build_demo_models())
    graph = make_live_graph()
    assert calls == []

    state = await graph.ainvoke(
        {"request": {"rubric": "A browser-edited rubric.", "max_iterations": 1}},
        config={"configurable": {"thread_id": "outer-live"}},
    )

    assert calls == ["resolved", calls[1]]
    assert state["report"]["terminal_status"] == "max_iterations_reached"
    assert state["report"]["accepted"] is False
    assert len(state["report"]["candidates"]) == 1
    assert state["report"]["final_candidate"] == state["report"]["candidates"][-1]["source"]


@pytest.mark.asyncio
async def test_validation_and_live_preflight_fail_before_worker_invocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def forbidden_factory() -> object:
        nonlocal called
        called = True
        raise AssertionError("model factory crossed validation boundary")

    graph = build_application_graph(mode="live", model_factory=forbidden_factory)
    invalid = await graph.ainvoke(
        {"request": {"task": "replace the fixed task"}},
        config={"configurable": {"thread_id": "outer-invalid"}},
    )
    assert invalid["error"]["code"] == "invalid_input"
    assert called is False

    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    missing = await make_live_graph().ainvoke({"request": {}}, config={"configurable": {"thread_id": "outer-missing"}})
    assert missing["error"] == {
        "code": "live_configuration",
        "message": "Live Model is not configured. Set server variable: OPENAI_API_KEY.",
        "missing": ["OPENAI_API_KEY"],
    }


class RaisingGrader(BaseChatModel):
    _bound: set[str] = PrivateAttr(default_factory=set)

    @property
    def _llm_type(self) -> str:
        return "raising-grader"

    def bind_tools(self, tools: list[dict[str, Any] | type | BaseTool], **kwargs: Any) -> RaisingGrader:
        del kwargs
        self._bound.update(
            tool.name
            if isinstance(tool, BaseTool)
            else tool.__name__
            if isinstance(tool, type)
            else tool["function"]["name"]
            for tool in tools
        )
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, kwargs
        raise RuntimeError(SENTINEL)


@pytest.mark.asyncio
async def test_grader_failure_is_terminal_and_sanitized_at_outer_boundary() -> None:
    graph = build_application_graph(
        mode="live",
        model_factory=lambda: SimpleNamespace(
            worker=DemoWorkerModel(),
            grader=RaisingGrader(profile={"structured_output": False}),
        ),
    )
    events, report, error = await _stream(
        graph,
        {"rubric": BASELINE_RUBRIC, "max_iterations": 3},
        "outer-grader-error",
    )

    assert error is None
    assert report is not None
    assert report["terminal_status"] == "grader_error"
    assert report["accepted"] is False
    assert SENTINEL not in json.dumps(events)
    assert SENTINEL not in json.dumps(report)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stream_error",
    [
        RuntimeError(f"provider body authorization=Bearer {SENTINEL}"),
        SensitiveProviderError("provider failed"),
    ],
    ids=["secret-in-message", "secret-in-type"],
)
async def test_inner_stream_failure_emits_only_sanitized_server_diagnostics(
    stream_error: Exception,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from {{ cookiecutter.project_slug }} import graphs

    class FailingInnerAgent:
        def astream(self, *args: object, **kwargs: object):
            del args, kwargs

            async def fail():
                raise stream_error
                yield  # pragma: no cover - keeps this an async generator

            return fail()

    monkeypatch.setattr(graphs, "build_inner_agent", lambda **_: FailingInnerAgent())
    graph = build_application_graph(
        mode="live",
        model_factory=lambda: SimpleNamespace(
            worker=SanitizingChatModel(
                delegate=DemoWorkerModel(),
                provider="openai",
                role="worker",
            ),
            grader=RaisingGrader(profile={"structured_output": False}),
        ),
    )

    with caplog.at_level(logging.ERROR):
        state = await graph.ainvoke(
            {"request": {"rubric": BASELINE_RUBRIC, "max_iterations": 3}},
            config={"configurable": {"thread_id": "outer-stream-failure"}},
        )

    assert state["error"] == {
        "code": "runtime",
        "message": "Run failed safely; inspect sanitized server diagnostics.",
        "missing": [],
    }
    assert "mode=live" in caplog.text
    assert "provider=openai" in caplog.text
    assert "error_type=RuntimeError" in caplog.text
    assert SENTINEL not in caplog.text


class OversizedWorker(BaseChatModel):
    source: str

    @property
    def _llm_type(self) -> str:
        return "oversized-worker"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self.source))])


class NormalThenOversizedWorker(BaseChatModel):
    normal_source: str
    oversized_source: str
    _invocation_count: int = PrivateAttr(default=0)

    @property
    def _llm_type(self) -> str:
        return "normal-then-oversized-worker"

    @property
    def invocation_count(self) -> int:
        return self._invocation_count

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        self._invocation_count += 1
        source = self.normal_source if self._invocation_count == 1 else self.oversized_source
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=source))])


class ForbiddenGrader(BaseChatModel):
    _invocation_count: int = PrivateAttr(default=0)

    @property
    def _llm_type(self) -> str:
        return "forbidden-grader"

    @property
    def invocation_count(self) -> int:
        return self._invocation_count

    def bind_tools(self, tools: list[dict[str, Any] | type | BaseTool], **kwargs: Any) -> ForbiddenGrader:
        del tools, kwargs
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        self._invocation_count += 1
        raise AssertionError("oversized candidate reached the grader")


def _public_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _public_strings(item)]
    if isinstance(value, list):
        return [text for item in value for text in _public_strings(item)]
    return []


@pytest.mark.asyncio
async def test_oversized_worker_candidate_returns_a_typed_rejected_report_without_grading_or_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    oversized = "x" * 3500 + "\n"
    assert len(oversized) == 3501
    grader = ForbiddenGrader(profile={"structured_output": False})
    executed: list[str] = []
    monkeypatch.setattr(evidence, "execute_candidate", executed.append)
    graph = build_application_graph(
        mode="live",
        model_factory=lambda: SimpleNamespace(
            worker=OversizedWorker(source=oversized),
            grader=grader,
        ),
    )

    events, report, error = await _stream(
        graph,
        {"rubric": BASELINE_RUBRIC, "max_iterations": 3},
        "outer-oversized",
    )

    assert error is None
    assert report is not None
    assert report["terminal_status"] == "failed"
    assert report["accepted"] is False
    assert report["gate_reason"] == "terminal_status_not_satisfied"
    assert report["iterations"] == 1
    assert report["final_candidate"] is None
    assert report["evaluations"] == []
    assert report["feedback"] == []
    rejected = report["candidates"]
    assert rejected == [
        {
            "grading_run_id": report["grading_run_id"],
            "version": 1,
            "iteration": 0,
            "candidate_id": candidate_id(oversized),
            "source": None,
            "source_omitted": True,
        }
    ]
    assert report["evidence"] == [
        {
            "event_id": f"{report['grading_run_id']}:rubric_evidence:0:1:0",
            "grading_run_id": report["grading_run_id"],
            "iteration": 0,
            "candidate_version": 1,
            "candidate_id": rejected[0]["candidate_id"],
            "requested_candidate_id": rejected[0]["candidate_id"],
            "ok": False,
            "behavior_failures": [],
            "profile_failures": ["candidate_too_long"],
            "duration_ms": 0,
            "timed_out": False,
            "output_truncated": False,
        }
    ]
    assert [event["type"] for event in events] == ["candidate", "rubric_evidence"]
    assert events[0]["candidate_id"] == rejected[0]["candidate_id"]
    assert events[0]["payload"] == {"source": None, "source_omitted": True}
    assert events[1]["payload"]["profile_failures"] == ["candidate_too_long"]
    assert grader.invocation_count == 0
    assert executed == []
    assert oversized not in json.dumps({"events": events, "report": report})
    assert max(map(len, _public_strings({"events": events, "report": report}))) <= 3500


@pytest.mark.asyncio
async def test_oversized_second_candidate_preserves_completed_history_without_grading_or_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    oversized = "x" * 3500 + "\n"
    worker = NormalThenOversizedWorker(
        normal_source=DEMO_FAILING_SOURCE,
        oversized_source=oversized,
    )
    grader = ScriptedGraderModel(profile={"structured_output": False})
    real_execute_candidate = evidence.execute_candidate
    executed: list[str] = []

    def tracked_execute_candidate(source: str):
        executed.append(source)
        return real_execute_candidate(source)

    monkeypatch.setattr(evidence, "execute_candidate", tracked_execute_candidate)
    graph = build_application_graph(
        mode="live",
        model_factory=lambda: SimpleNamespace(worker=worker, grader=grader),
    )

    events, report, error = await _stream(
        graph,
        {"rubric": BASELINE_RUBRIC, "max_iterations": 3},
        "outer-normal-then-oversized",
    )

    assert error is None
    assert report is not None
    assert report["terminal_status"] == "failed"
    assert report["accepted"] is False
    assert report["gate_reason"] == "terminal_status_not_satisfied"
    assert report["iterations"] == 2
    assert report["final_candidate"] is None
    first, rejected = report["candidates"]
    assert (first["version"], first["iteration"], first["candidate_id"], first["source"]) == (
        1,
        0,
        candidate_id(DEMO_FAILING_SOURCE),
        DEMO_FAILING_SOURCE,
    )
    assert rejected == {
        "grading_run_id": report["grading_run_id"],
        "version": 2,
        "iteration": 1,
        "candidate_id": candidate_id(oversized),
        "source": None,
        "source_omitted": True,
    }
    assert [(item["candidate_version"], item["ok"]) for item in report["evidence"]] == [
        (1, False),
        (2, False),
    ]
    assert report["evidence"][1]["profile_failures"] == ["candidate_too_long"]
    assert [(item["candidate_version"], item["result"]) for item in report["evaluations"]] == [(1, "needs_revision")]
    assert len(report["feedback"]) == 1
    assert report["feedback"][0]["candidate_version"] == 1
    assert report["feedback"][0]["candidate_id"] == first["candidate_id"]

    reconciled = reconcile_public_events(events, report)
    assert [
        (item["candidate_version"], item["payload"]["result"])
        for item in reconciled
        if item["type"] == "rubric_evaluation_end"
    ] == [(1, "needs_revision")]
    assert [item["candidate_version"] for item in reconciled if item["type"] == "grader_feedback"] == [1]
    assert [item["candidate_version"] for item in reconciled if item["type"] == "rubric_evidence"] == [1, 2]
    assert worker.invocation_count == 2
    assert grader.call_kinds == ["request_evidence", "return_needs_revision"]
    assert executed == [DEMO_FAILING_SOURCE]
    public_result = {"events": events, "reconciled": reconciled, "report": report}
    assert oversized not in json.dumps(public_result)
    assert max(map(len, _public_strings(public_result))) <= 3500


def test_report_rejects_candidate_id_that_does_not_match_normalized_source() -> None:
    with pytest.raises(ValueError, match="candidate ID"):
        build_run_report(
            mode="demo",
            thread_id="outer",
            inner_thread_id="inner",
            grading_run_id="run",
            terminal_status="satisfied",
            iterations=1,
            candidates=[
                {
                    "grading_run_id": "run",
                    "version": 1,
                    "iteration": 0,
                    "candidate_id": "tampered",
                    "source": "def find_duplicates(values):\n    return []\n",
                }
            ],
            final_candidate="def find_duplicates(values):\n    return []\n",
            evidence=[],
            evaluations=[],
            feedback=[],
        )


def test_timed_out_evidence_cannot_open_the_acceptance_gate() -> None:
    source = "def find_duplicates(values):\n    return []\n"
    candidate_id = "d99a66c638782bf38e02a818855afd652b45952c2d26676ba85ec941a617a1f3"
    report = build_run_report(
        mode="demo",
        thread_id="outer",
        inner_thread_id="inner",
        grading_run_id="run",
        terminal_status="satisfied",
        iterations=1,
        candidates=[
            {
                "grading_run_id": "run",
                "version": 1,
                "iteration": 0,
                "candidate_id": candidate_id,
                "source": source,
            }
        ],
        final_candidate=source,
        evidence=[
            {
                "event_id": "run:rubric_evidence:0:1:0",
                "grading_run_id": "run",
                "iteration": 0,
                "candidate_version": 1,
                "candidate_id": candidate_id,
                "requested_candidate_id": candidate_id,
                "ok": True,
                "behavior_failures": [],
                "profile_failures": [],
                "duration_ms": 1000,
                "timed_out": True,
                "output_truncated": False,
            }
        ],
        evaluations=[],
        feedback=[],
    )

    assert report["accepted"] is False
    assert report["gate_reason"] == "current_evidence_missing"


def test_truncated_evidence_cannot_open_the_acceptance_gate() -> None:
    source = "def find_duplicates(values):\n    return []\n"
    candidate_id = "d99a66c638782bf38e02a818855afd652b45952c2d26676ba85ec941a617a1f3"
    report = build_run_report(
        mode="demo",
        thread_id="outer",
        inner_thread_id="inner",
        grading_run_id="run",
        terminal_status="satisfied",
        iterations=1,
        candidates=[
            {
                "grading_run_id": "run",
                "version": 1,
                "iteration": 0,
                "candidate_id": candidate_id,
                "source": source,
            }
        ],
        final_candidate=source,
        evidence=[
            {
                "event_id": "run:rubric_evidence:0:1:0",
                "grading_run_id": "run",
                "iteration": 0,
                "candidate_version": 1,
                "candidate_id": candidate_id,
                "requested_candidate_id": candidate_id,
                "ok": True,
                "behavior_failures": [],
                "profile_failures": [],
                "duration_ms": 1000,
                "timed_out": False,
                "output_truncated": True,
            }
        ],
        evaluations=[],
        feedback=[],
    )

    assert report["accepted"] is False
    assert report["gate_reason"] == "current_evidence_missing"


class BlockingWorker(BaseChatModel):
    started: asyncio.Event

    @property
    def _llm_type(self) -> str:
        return "blocking-worker"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, kwargs
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="unused"))])

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, kwargs
        self.started.set()
        await asyncio.Future()
        raise AssertionError("unreachable")


@pytest.mark.asyncio
async def test_cancellation_propagates_and_does_not_poison_a_fresh_demo_run() -> None:
    started = asyncio.Event()
    graph = build_application_graph(
        mode="live",
        model_factory=lambda: SimpleNamespace(
            worker=BlockingWorker(started=started),
            grader=build_demo_models().grader,
        ),
    )
    task = asyncio.create_task(
        graph.ainvoke(
            {"request": {"rubric": BASELINE_RUBRIC, "max_iterations": 3}},
            config={"configurable": {"thread_id": "outer-cancelled"}},
        )
    )
    await asyncio.wait_for(started.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    fresh = await make_demo_graph().ainvoke(
        {"request": {}}, config={"configurable": {"thread_id": "outer-after-cancel"}}
    )
    assert fresh["report"]["terminal_status"] == "satisfied"
    assert fresh["report"]["accepted"] is True


def test_keyless_smoke_executes_the_evidence_backed_revision_loop(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    from {{ cookiecutter.project_slug }}.smoke import main

    assert main() == 0
    output = capsys.readouterr().out
    assert "evaluation_results=needs_revision,satisfied" in output
    assert "evidence_version=2 ok=true" in output
    assert "gate=satisfied_with_current_evidence accepted=true" in output


def test_smoke_verifier_rejects_truncated_final_evidence() -> None:
    from {{ cookiecutter.project_slug }}.smoke import _verify

    report = {
        "terminal_status": "satisfied",
        "accepted": True,
        "iterations": 2,
        "gate_reason": "satisfied_with_current_evidence",
        "candidates": [{"version": 2}],
        "evaluations": [{"result": "needs_revision"}, {"result": "satisfied"}],
        "evidence": [{"candidate_version": 2, "ok": True, "output_truncated": True}],
    }
    with pytest.raises(AssertionError, match="truncated"):
        _verify([], report)  # type: ignore[arg-type]
