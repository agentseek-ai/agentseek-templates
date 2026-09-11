from __future__ import annotations

import json
import os

from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeListChatModel

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


def test_real_deepagents_graph_reaches_v3_projection_route(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    graph = create_deep_agent(model=ToolCapableFakeModel(responses=["offline answer"]))
    monkeypatch.setattr(routes, "graph", graph)

    response = TestClient(routes.app).post(
        "/custom/stream",
        json={"thread_id": "offline-v3", "messages": [{"role": "user", "content": "Explain v3."}]},
    )

    assert response.status_code == 200
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
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
