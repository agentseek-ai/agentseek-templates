from __future__ import annotations

import json
from typing import Any

import pytest
from deepagents.middleware import GraderResponse, RubricMiddleware
from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import PrivateAttr

from {{ cookiecutter.project_slug }} import evidence
from {{ cookiecutter.project_slug }}.contracts import (
    BASELINE_RUBRIC,
    TASK_PROMPT,
    build_run_report,
    candidate_id,
    normalize_candidate_source,
)
from {{ cookiecutter.project_slug }}.demo_models import (
    DEMO_FAILING_SOURCE,
    DEMO_PASSING_SOURCE,
    ScriptedGraderModel,
    build_demo_models,
)
from {{ cookiecutter.project_slug }}.evidence import RunEvidenceLedger, make_run_test_suite
from {{ cookiecutter.project_slug }}.graphs import CandidateTrackingMiddleware, build_inner_agent


def _run(agent: Any, *, thread_id: str, rubric: str | None = BASELINE_RUBRIC) -> dict[str, Any]:
    config = {"configurable": {"thread_id": thread_id}}
    inputs: dict[str, object] = {"messages": [{"role": "user", "content": TASK_PROMPT}]}
    if rubric is not None:
        inputs["rubric"] = rubric
    agent.invoke(inputs, config=config)
    return dict(agent.get_state(config).values)


def _last_candidate(checkpoint: dict[str, Any]) -> str:
    messages = checkpoint["messages"]
    final = next(message for message in reversed(messages) if isinstance(message, AIMessage))
    return normalize_candidate_source(final)


def test_deepagents_071_runs_real_evidence_before_revising_to_satisfied() -> None:
    models = build_demo_models()
    ledger = RunEvidenceLedger(grading_run_id="characterization-run")
    agent = create_agent(
        model=models.worker,
        tools=[],
        middleware=[
            CandidateTrackingMiddleware(ledger),
            RubricMiddleware(
                model=models.grader,
                tools=[make_run_test_suite(ledger)],
                max_iterations=3,
            ),
        ],
        checkpointer=InMemorySaver(),
    )

    checkpoint = _run(agent, thread_id="characterization-thread")

    assert checkpoint["_rubric_status"] == "satisfied"
    assert checkpoint["_rubric_iterations"] == 2
    assert [item["result"] for item in checkpoint["_rubric_evaluations"]] == [
        "needs_revision",
        "satisfied",
    ]
    feedback = [
        message
        for message in checkpoint["messages"]
        if isinstance(message, HumanMessage)
        and message.name == "rubric_grader"
        and message.additional_kwargs.get("lc_source") == "rubric_grader"
    ]
    assert len(feedback) == 1
    assert len(ledger.candidates) == len(ledger.evidence) == 2
    assert ledger.candidates[0]["candidate_id"] != ledger.candidates[1]["candidate_id"]
    assert [record["candidate_id"] for record in ledger.evidence] == [
        record["candidate_id"] for record in ledger.candidates
    ]
    assert [record["ok"] for record in ledger.evidence] == [False, True]
    first_failures = ledger.evidence[0]["behavior_failures"] + ledger.evidence[0]["profile_failures"]
    first_criteria = checkpoint["_rubric_evaluations"][0]["criteria"]
    assert {criterion["name"] for criterion in first_criteria} == set(first_failures)
    assert all(criterion["passed"] is False and criterion["gap"] for criterion in first_criteria)
    assert _last_candidate(checkpoint) == normalize_candidate_source(DEMO_PASSING_SOURCE)
    assert models.worker.invocation_count == 2
    assert models.grader.call_kinds == [
        "request_evidence",
        "return_needs_revision",
        "request_evidence",
        "return_satisfied",
    ]
    assert models.grader.bound_tool_names == {"run_test_suite", "GraderResponse"}


class AdversarialSatisfiedGrader(BaseChatModel):
    _bound_tool_names: set[str] = PrivateAttr(default_factory=set)

    @property
    def _llm_type(self) -> str:
        return "adversarial-satisfied-grader"

    @property
    def bound_tool_names(self) -> set[str]:
        return set(self._bound_tool_names)

    def bind_tools(
        self,
        tools: list[dict[str, Any] | type | BaseTool],
        **kwargs: Any,
    ) -> AdversarialSatisfiedGrader:
        del kwargs
        self._bound_tool_names.update(
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
        del stop, kwargs
        tool_message = next((message for message in reversed(messages) if isinstance(message, ToolMessage)), None)
        if tool_message is None:
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "mismatched-evidence",
                        "name": "run_test_suite",
                        "args": {"code": DEMO_PASSING_SOURCE},
                        "type": "tool_call",
                    }
                ],
            )
        else:
            assert json.loads(str(tool_message.content))["ok"] is False
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "dishonest-verdict",
                        "name": GraderResponse.__name__,
                        "args": {
                            "result": "satisfied",
                            "explanation": "Claims success despite mismatched evidence.",
                            "criteria": [{"name": "claimed", "passed": True}],
                        },
                        "type": "tool_call",
                    }
                ],
            )
        return ChatResult(generations=[ChatGeneration(message=message)])


def test_satisfied_verdict_with_mismatched_evidence_fails_closed_without_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = RunEvidenceLedger(grading_run_id="adversarial-run")
    models = build_demo_models()
    grader = AdversarialSatisfiedGrader(profile={"structured_output": False})
    monkeypatch.setattr(
        evidence,
        "execute_candidate",
        lambda source: (_ for _ in ()).throw(AssertionError(f"mismatched source executed: {source}")),
    )
    agent = build_inner_agent(
        worker_model=models.worker,
        grader_model=grader,
        max_iterations=3,
        checkpointer=InMemorySaver(),
        ledger=ledger,
    )

    checkpoint = _run(agent, thread_id="adversarial-thread")
    report = build_run_report(
        mode="demo",
        thread_id="outer-adversarial",
        inner_thread_id="adversarial-thread",
        grading_run_id=ledger.grading_run_id,
        terminal_status=checkpoint["_rubric_status"],
        iterations=checkpoint["_rubric_iterations"],
        candidates=ledger.candidates,
        final_candidate=_last_candidate(checkpoint),
        evidence=ledger.evidence,
        evaluations=checkpoint["_rubric_evaluations"],
        feedback=[],
    )

    assert checkpoint["_rubric_status"] == "satisfied"
    assert grader.bound_tool_names == {"run_test_suite", "GraderResponse"}
    assert len(ledger.evidence) == 1
    assert ledger.evidence[0]["profile_failures"] == ["candidate_binding"]
    assert ledger.evidence[0]["candidate_id"] == candidate_id(DEMO_FAILING_SOURCE)
    assert ledger.evidence[0]["requested_candidate_id"] == candidate_id(DEMO_PASSING_SOURCE)
    assert report["accepted"] is False
    assert report["gate_reason"] == "current_evidence_missing"


def test_shared_builder_rejects_a_non_positive_iteration_cap() -> None:
    models = build_demo_models()

    with pytest.raises(ValueError, match="positive integer"):
        build_inner_agent(
            worker_model=models.worker,
            grader_model=models.grader,
            max_iterations=0,
            checkpointer=InMemorySaver(),
            ledger=RunEvidenceLedger(grading_run_id="invalid-cap"),
        )


def test_each_demo_model_build_has_isolated_invocation_state() -> None:
    first = build_demo_models()
    second = build_demo_models()

    assert first.worker is not second.worker
    assert first.grader is not second.grader
    assert first.worker.invocation_count == second.worker.invocation_count == 0
    assert first.grader.call_kinds == second.grader.call_kinds == []
    assert isinstance(first.grader, ScriptedGraderModel)
