from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypedDict

from langchain.agents import create_agent
from langchain.agents.middleware.types import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from .contracts import normalize_candidate_source
from .evidence import RunEvidenceLedger, make_run_test_suite
from .models import build_live_models, resolve_live_config
from .safe_rubric import SafeRubricMiddleware


class ApplicationState(TypedDict, total=False):
    request: dict[str, object]


class CandidateTrackingMiddleware(AgentMiddleware):
    """Record each Worker response against the active zero-based rubric iteration."""

    def __init__(self, ledger: RunEvidenceLedger) -> None:
        self._ledger = ledger

    def _record(self, response: ModelResponse[Any] | AIMessage, request: ModelRequest[Any]) -> None:
        messages = [response] if isinstance(response, AIMessage) else response.result
        candidate = next((message for message in reversed(messages) if isinstance(message, AIMessage)), None)
        if candidate is None:
            return
        iteration = request.state.get("_rubric_iterations", 0) or 0
        self._ledger.record_candidate(normalize_candidate_source(candidate), iteration)

    def wrap_model_call(self, request: ModelRequest[Any], handler: Callable[[ModelRequest[Any]], Any]):
        response = handler(request)
        self._record(response, request)
        return response

    async def awrap_model_call(self, request: ModelRequest[Any], handler: Callable[[ModelRequest[Any]], Any]):
        response = await handler(request)
        self._record(response, request)
        return response


def build_inner_agent(
    *,
    worker_model: BaseChatModel,
    grader_model: BaseChatModel,
    max_iterations: int,
    checkpointer: BaseCheckpointSaver,
    ledger: RunEvidenceLedger,
):
    if max_iterations < 1:
        raise ValueError("max_iterations must be a positive integer")
    return create_agent(
        model=worker_model,
        tools=[],
        middleware=[
            CandidateTrackingMiddleware(ledger),
            SafeRubricMiddleware(
                model=grader_model,
                tools=[make_run_test_suite(ledger)],
                max_iterations=max_iterations,
            ),
        ],
        checkpointer=checkpointer,
    )


def build_application_graph(*, model_factory: Callable[[], object]):
    """Build stable topology while deferring model work to graph invocation."""

    async def run(_: ApplicationState) -> ApplicationState:
        model_factory()
        return {}

    builder = StateGraph(ApplicationState)
    builder.add_node("run", run)
    builder.add_edge(START, "run")
    builder.add_edge("run", END)
    return builder.compile()


def make_demo_graph():
    return build_application_graph(model_factory=lambda: None)


def make_live_graph():
    return build_application_graph(
        model_factory=lambda: build_live_models(resolve_live_config()),
    )
