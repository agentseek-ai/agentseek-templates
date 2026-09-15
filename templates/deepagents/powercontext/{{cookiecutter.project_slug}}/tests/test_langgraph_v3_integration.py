from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeListChatModel, GenericFakeChatModel
from langchain_core.messages import AIMessage

os.environ.setdefault("OPENAI_API_KEY", "offline-test-key")
os.environ.setdefault("AGENTSEEK_MODEL_PROVIDER", "openai")
os.environ.setdefault("AGENTSEEK_MODEL", "offline-test-model")

from deepagents import create_deep_agent  # noqa: E402
from {{ cookiecutter.project_slug }} import routes  # noqa: E402
from {{ cookiecutter.project_slug }}.agent import build_stream_graph  # noqa: E402


class ToolCapableFakeModel(FakeListChatModel):
    """Offline chat model that supports the tool-binding path used by DeepAgents."""

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):  # type: ignore[no-untyped-def]
        return self


class ToolCapableScriptedModel(GenericFakeChatModel):
    """Offline model that drives one coordinator-to-researcher delegation."""

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):  # type: ignore[no-untyped-def]
        return self


class SuccessfulPowerContextClient:
    requests: list[object] = []

    def __init__(self, _url: str) -> None:
        pass

    async def __aenter__(self) -> SuccessfulPowerContextClient:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def resolve_scope_binding(self, request: object) -> SimpleNamespace:
        return SimpleNamespace(scope_id="server-owned-test-scope")

    async def prepare_context(self, request: object) -> SimpleNamespace:
        self.requests.append(request)
        return SimpleNamespace(status="ready", content="retrieved reference", content_bytes=19)


def test_real_deepagents_graph_reaches_v3_projection_route(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    graph = create_deep_agent(model=ToolCapableFakeModel(responses=["offline answer"]))
    monkeypatch.setattr(routes, "graph", graph)

    response = TestClient(routes.app).post(
        "/custom/stream",
        json={"thread_id": "offline-v3", "messages": [{"role": "user", "content": "Explain v3."}]},
    )

    assert response.status_code == 200
    events = [
        json.loads(line.removeprefix("data: ")) for line in response.text.splitlines() if line.startswith("data: ")
    ]
    assert {event["kind"] for event in events} >= {"message", "values", "raw", "output"}
    output_events = [event for event in events if event["kind"] == "output"]
    assert output_events
    assert output_events[-1]["phase"] == "completed"
    assert "bound method" not in response.text
    assert "AsyncGraphRunStream.output" not in response.text


def test_stream_route_persists_history_across_follow_up_requests(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    persistent_graph = build_stream_graph(
        ToolCapableFakeModel(responses=["first offline answer", "second offline answer"])
    )
    monkeypatch.setattr(routes, "graph", persistent_graph)
    client = TestClient(routes.app)

    for content in ("first question", "follow up question"):
        response = client.post(
            "/custom/stream",
            json={"thread_id": "persisted-thread", "messages": [{"role": "user", "content": content}]},
        )
        assert response.status_code == 200

    snapshot = persistent_graph.get_state({"configurable": {"thread_id": "persisted-thread"}})
    user_messages = [message.content for message in snapshot.values["messages"] if message.type == "human"]
    assert user_messages == ["first question", "follow up question"]


@pytest.mark.anyio
async def test_delegation_applies_powercontext_to_coordinator_and_researcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    SuccessfulPowerContextClient.requests = []
    monkeypatch.setattr(
        "{{ cookiecutter.project_slug }}.powercontext_middleware.open_client",
        lambda: SuccessfulPowerContextClient("unused"),
    )
    graph = build_stream_graph(
        ToolCapableScriptedModel(
            messages=iter(
                [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "task",
                                "args": {
                                    "description": "Research Event Streaming v3.",
                                    "subagent_type": "researcher",
                                },
                                "id": "task-1",
                                "type": "tool_call",
                            }
                        ],
                    ),
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "release_checklist",
                                "args": {"topic": "Event Streaming v3"},
                                "id": "inspect-1",
                                "type": "tool_call",
                            }
                        ],
                    ),
                    AIMessage(content="Research complete."),
                    AIMessage(content="Coordinator summary."),
                ]
            )
        )
    )

    await graph.ainvoke(
        {"messages": [{"role": "user", "content": "Explain Event Streaming v3."}]},
        {"configurable": {"thread_id": "delegation-powercontext"}},
    )

    assert len(SuccessfulPowerContextClient.requests) == 4
    assert [request.query for request in SuccessfulPowerContextClient.requests] == [
        "Explain Event Streaming v3.",
        "Research Event Streaming v3.",
        "Research Event Streaming v3.",
        "Explain Event Streaming v3.",
    ]


@pytest.mark.anyio
async def test_recalled_context_is_not_saved_in_checkpoint(monkeypatch):
    monkeypatch.setattr(
        "{{ cookiecutter.project_slug }}.powercontext_middleware.open_client",
        lambda: SuccessfulPowerContextClient("unused"),
    )
    graph = build_stream_graph(ToolCapableFakeModel(responses=["answer"]))
    config = {"configurable": {"thread_id": "ephemeral-recall"}}
    await graph.ainvoke({"messages": [{"role": "user", "content": "Project release?"}]}, config)
    snapshot = await graph.aget_state(config)
    messages = snapshot.values["messages"]
    assert [message.content for message in messages] == ["Project release?", "answer"]
    assert "retrieved reference" not in str(messages)
