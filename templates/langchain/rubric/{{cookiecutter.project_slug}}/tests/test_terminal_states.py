from __future__ import annotations

import asyncio
import inspect
import logging
from types import SimpleNamespace
from typing import Any

import pytest
from deepagents.middleware import RubricMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import PrivateAttr

from {{ cookiecutter.project_slug }} import safe_rubric
from {{ cookiecutter.project_slug }}.contracts import (
    BASELINE_RUBRIC,
    TASK_PROMPT,
    build_run_report,
    normalize_candidate_source,
)
from {{ cookiecutter.project_slug }}.demo_models import (
    DEMO_FAILING_SOURCE,
    DemoWorkerModel,
    ScriptedGraderModel,
    build_demo_models,
)
from {{ cookiecutter.project_slug }}.evidence import RunEvidenceLedger
from {{ cookiecutter.project_slug }}.graphs import build_inner_agent
from {{ cookiecutter.project_slug }}.safe_rubric import SafeRubricMiddleware

SENTINEL = "SENTINEL_SECRET_7f2c"


def _config(thread_id: str) -> dict[str, dict[str, str]]:
    return {"configurable": {"thread_id": thread_id}}


def _input(*, rubric: str | None = BASELINE_RUBRIC) -> dict[str, object]:
    value: dict[str, object] = {"messages": [{"role": "user", "content": TASK_PROMPT}]}
    if rubric is not None:
        value["rubric"] = rubric
    return value


def _checkpoint(agent: Any, thread_id: str) -> dict[str, Any]:
    return dict(agent.get_state(_config(thread_id)).values)


def _last_ai(checkpoint: dict[str, Any]) -> AIMessage:
    return next(message for message in reversed(checkpoint["messages"]) if isinstance(message, AIMessage))


def _report(checkpoint: dict[str, Any], ledger: RunEvidenceLedger, thread_id: str):
    last = _last_ai(checkpoint)
    return build_run_report(
        mode="demo",
        thread_id=f"outer-{thread_id}",
        inner_thread_id=thread_id,
        grading_run_id=ledger.grading_run_id,
        terminal_status=checkpoint["_rubric_status"],
        iterations=checkpoint["_rubric_iterations"],
        candidates=ledger.candidates,
        final_candidate=normalize_candidate_source(last),
        evidence=ledger.evidence,
        evaluations=checkpoint.get("_rubric_evaluations", []),
        feedback=[],
    )


def test_iteration_cap_retains_the_first_candidate_and_is_not_accepted() -> None:
    models = build_demo_models()
    ledger = RunEvidenceLedger(grading_run_id="cap-run")
    agent = build_inner_agent(
        worker_model=models.worker,
        grader_model=models.grader,
        max_iterations=1,
        checkpointer=InMemorySaver(),
        ledger=ledger,
    )

    agent.invoke(_input(), config=_config("cap-thread"))
    checkpoint = _checkpoint(agent, "cap-thread")
    report = _report(checkpoint, ledger, "cap-thread")

    assert checkpoint["_rubric_status"] == "max_iterations_reached"
    assert checkpoint["_rubric_iterations"] == 1
    assert isinstance(_last_ai(checkpoint), AIMessage)
    assert normalize_candidate_source(_last_ai(checkpoint)) == normalize_candidate_source(DEMO_FAILING_SOURCE)
    assert models.worker.invocation_count == 1
    assert len(ledger.candidates) == len(ledger.evidence) == 1
    assert report["accepted"] is False


def test_fresh_thread_without_rubric_never_invokes_the_grader_or_evidence() -> None:
    models = build_demo_models()
    ledger = RunEvidenceLedger(grading_run_id="no-rubric-run")
    agent = build_inner_agent(
        worker_model=models.worker,
        grader_model=models.grader,
        max_iterations=3,
        checkpointer=InMemorySaver(),
        ledger=ledger,
    )

    agent.invoke(_input(rubric=None), config=_config("no-rubric-thread"))
    checkpoint = _checkpoint(agent, "no-rubric-thread")

    assert isinstance(_last_ai(checkpoint), AIMessage)
    assert models.grader.call_kinds == []
    assert ledger.evidence == []
    assert checkpoint.get("_rubric_evaluations", []) == []
    assert "_rubric_status" not in checkpoint


def test_failed_verdict_retains_the_last_candidate_and_is_not_accepted() -> None:
    worker = DemoWorkerModel()
    grader = ScriptedGraderModel(terminal_result="failed", profile={"structured_output": False})
    ledger = RunEvidenceLedger(grading_run_id="failed-run")
    agent = build_inner_agent(
        worker_model=worker,
        grader_model=grader,
        max_iterations=3,
        checkpointer=InMemorySaver(),
        ledger=ledger,
    )

    agent.invoke(_input(), config=_config("failed-thread"))
    checkpoint = _checkpoint(agent, "failed-thread")
    report = _report(checkpoint, ledger, "failed-thread")

    assert checkpoint["_rubric_status"] == "failed"
    assert isinstance(_last_ai(checkpoint), AIMessage)
    assert normalize_candidate_source(_last_ai(checkpoint)) == normalize_candidate_source(DEMO_FAILING_SOURCE)
    assert report["accepted"] is False


class RaisingGraderModel(BaseChatModel):
    error: BaseException
    _bound_tool_names: set[str] = PrivateAttr(default_factory=set)

    @property
    def _llm_type(self) -> str:
        return "raising-grader"

    def bind_tools(
        self,
        tools: list[dict[str, Any] | type | BaseTool],
        **kwargs: Any,
    ) -> RaisingGraderModel:
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
        del messages, stop, kwargs
        raise self.error

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, kwargs
        raise self.error


class MalformedStructuredOutputGraderModel(BaseChatModel):
    _bound_tool_names: set[str] = PrivateAttr(default_factory=set)
    _validation_error_text: str | None = PrivateAttr(default=None)
    _failure: RuntimeError | None = PrivateAttr(default=None)

    @property
    def _llm_type(self) -> str:
        return "malformed-structured-output-grader"

    @property
    def bound_tool_names(self) -> set[str]:
        return set(self._bound_tool_names)

    @property
    def validation_error_text(self) -> str | None:
        return self._validation_error_text

    @property
    def failure(self) -> RuntimeError | None:
        return self._failure

    def bind_tools(
        self,
        tools: list[dict[str, Any] | type | BaseTool],
        **kwargs: Any,
    ) -> MalformedStructuredOutputGraderModel:
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
        validation_message = next(
            (
                message
                for message in reversed(messages)
                if isinstance(message, ToolMessage) and message.name == "GraderResponse"
            ),
            None,
        )
        if validation_message is not None:
            self._validation_error_text = str(validation_message.content)
            self._failure = RuntimeError(self._validation_error_text)
            raise self._failure

        malformed = AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "malformed-grader-response",
                    "name": "GraderResponse",
                    "args": {
                        "result": "satisfied",
                        "explanation": SENTINEL,
                        "criteria": [
                            {
                                "name": "sentinel-criterion",
                                "passed": False,
                                "gap": SENTINEL,
                            }
                        ],
                    },
                    "type": "tool_call",
                }
            ],
        )
        return ChatResult(generations=[ChatGeneration(message=malformed)])


def test_safe_middleware_matches_the_pinned_private_handler_and_only_overrides_it() -> None:
    assert str(inspect.signature(RubricMiddleware._handle_grader_exception)) == (
        "(self, runtime: 'Runtime[ContextT]', state: 'RubricState', grading_run_id: 'str', "
        "iteration: 'int', exc: 'Exception') -> 'dict[str, Any]'"
    )
    assert list(inspect.signature(SafeRubricMiddleware._handle_grader_exception).parameters) == [
        "self",
        "runtime",
        "state",
        "grading_run_id",
        "iteration",
        "exc",
    ]
    assert {
        name for name, value in SafeRubricMiddleware.__dict__.items() if callable(value) and not name.startswith("__")
    } == {"_handle_grader_exception"}


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError(SENTINEL),
        type(SENTINEL, (RuntimeError,), {})(SENTINEL),
    ],
)
def test_direct_grader_error_is_sanitized_across_logs_events_checkpoint_and_report(
    error: Exception,
    caplog: pytest.LogCaptureFixture,
) -> None:
    worker = DemoWorkerModel()
    grader = RaisingGraderModel(error=error, profile={"structured_output": False})
    ledger = RunEvidenceLedger(grading_run_id="grader-error-run")
    agent = build_inner_agent(
        worker_model=worker,
        grader_model=grader,
        max_iterations=3,
        checkpointer=InMemorySaver(),
        ledger=ledger,
    )

    with caplog.at_level(logging.ERROR):
        events = list(
            agent.stream(
                _input(),
                config=_config("grader-error-thread"),
                stream_mode="custom",
            )
        )
    checkpoint = _checkpoint(agent, "grader-error-thread")
    report = _report(checkpoint, ledger, "grader-error-thread")

    assert checkpoint["_rubric_status"] == "grader_error"
    assert checkpoint["_rubric_iterations"] == 1
    assert isinstance(_last_ai(checkpoint), AIMessage)
    assert report["accepted"] is False
    assert SENTINEL not in caplog.text
    assert SENTINEL not in repr(events)
    assert SENTINEL not in repr(checkpoint["_rubric_evaluations"])
    assert SENTINEL not in repr(report)
    assert checkpoint["_rubric_evaluations"][0]["explanation"] in {
        "Grader failed with RuntimeError; inspect sanitized server diagnostics.",
        "Grader failed with GraderError; inspect sanitized server diagnostics.",
    }


def test_real_tool_strategy_validation_failure_projects_a_safe_public_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    grader = MalformedStructuredOutputGraderModel(profile={"structured_output": False})
    ledger = RunEvidenceLedger(grading_run_id="structured-output-error-run")
    agent = build_inner_agent(
        worker_model=DemoWorkerModel(),
        grader_model=grader,
        max_iterations=3,
        checkpointer=InMemorySaver(),
        ledger=ledger,
    )

    with caplog.at_level(logging.ERROR):
        events = list(
            agent.stream(
                _input(),
                config=_config("structured-output-error-thread"),
                stream_mode="custom",
            )
        )
    checkpoint = _checkpoint(agent, "structured-output-error-thread")
    report = _report(checkpoint, ledger, "structured-output-error-thread")

    assert grader.bound_tool_names == {"run_test_suite", "GraderResponse"}
    assert grader.validation_error_text is not None
    assert "Failed to parse structured output for tool 'GraderResponse'" in grader.validation_error_text
    assert SENTINEL in grader.validation_error_text
    assert grader.failure is not None
    assert SENTINEL in str(grader.failure)
    projector = getattr(safe_rubric, "make_grader_public_error", None)
    assert callable(projector), "Task 5 must expose the production grader-error projection boundary"
    public_error = projector(grader.failure)

    assert checkpoint["_rubric_status"] == "grader_error"
    assert report["accepted"] is False
    assert public_error == {
        "code": "runtime",
        "message": "Grader failed with RuntimeError; inspect sanitized server diagnostics.",
        "missing": [],
    }
    assert SENTINEL not in caplog.text
    assert SENTINEL not in repr(events)
    assert SENTINEL not in repr(checkpoint["_rubric_evaluations"])
    assert SENTINEL not in repr(report)
    assert SENTINEL not in repr(public_error)


@pytest.mark.asyncio
async def test_async_cancellation_at_the_middleware_boundary_is_not_converted_to_grader_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    middleware = SafeRubricMiddleware(
        model=ScriptedGraderModel(profile={"structured_output": False}),
        max_iterations=3,
    )

    async def cancel(state: object, iteration: int) -> None:
        del state, iteration
        raise asyncio.CancelledError

    monkeypatch.setattr(middleware, "_agrade", cancel)

    with pytest.raises(asyncio.CancelledError):
        await middleware.aafter_agent(
            {"rubric": BASELINE_RUBRIC, "messages": []},
            SimpleNamespace(stream_writer=None),
        )
