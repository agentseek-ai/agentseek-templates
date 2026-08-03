from __future__ import annotations

from collections.abc import Callable
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from .models import build_live_models, resolve_live_config


class ApplicationState(TypedDict, total=False):
    request: dict[str, object]


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
