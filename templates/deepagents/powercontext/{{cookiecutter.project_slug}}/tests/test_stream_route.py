from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Iterable
from typing import Any

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("AGENTSEEK_MODEL_PROVIDER", "openai")
os.environ.setdefault("AGENTSEEK_MODEL", "gpt-4.1-mini")

from {{ cookiecutter.project_slug }} import powercontext_middleware, routes  # noqa: E402
from {{ cookiecutter.project_slug }}.routes import _resolve  # noqa: E402


class AsyncItems:
    def __init__(self, items: Iterable[Any]) -> None:
        self.items = list(items)

    def __aiter__(self) -> AsyncIterator[Any]:
        async def iterator() -> AsyncIterator[Any]:
            for item in self.items:
                yield item

        return iterator()


class FakeMessage:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeToolCall:
    tool_name = "release_checklist"
    input = {"topic": "v3"}
    output_deltas = AsyncItems(["first", " second"])
    completed = True
    error = None
    output = {"result": "local reference"}


class FakeSubagent:
    name = "researcher"
    path = ["researcher:fake"]
    status = "completed"
    messages = AsyncItems([FakeMessage("research result")])
    tool_calls = AsyncItems([FakeToolCall()])
    subagents = AsyncItems([])


class FakeRun:
    """Exposes every v3 projection so the route can prove it discards most of them."""

    messages = AsyncItems([FakeMessage("coordinator result")])
    tool_calls = AsyncItems([FakeToolCall()])
    subagents = AsyncItems([FakeSubagent()])
    values = AsyncItems([{"messages": ["snapshot"]}])

    async def output(self) -> dict[str, list[str]]:
        return {"messages": ["final"]}

    def __aiter__(self) -> AsyncIterator[dict[str, Any]]:
        async def iterator() -> AsyncIterator[dict[str, Any]]:
            yield {
                "seq": 7,
                "method": "messages",
                "params": {
                    "namespace": ["researcher:fake"],
                    "timestamp": 1,
                    "data": [{"event": "content-block-delta", "delta": {"type": "text-delta", "text": "hi"}}],
                },
            }

        return iterator()


class FakeGraph:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def astream_events(self, input: dict[str, Any], *, config: Any, version: str) -> FakeRun:
        self.calls.append({"input": input, "config": config, "version": version})
        return FakeRun()


class PowerContextFakeGraph(FakeGraph):
    async def astream_events(self, input: dict[str, Any], *, config: Any, version: str) -> FakeRun:
        await powercontext_middleware._publish(
            {"status": "ready", "content_bytes": 12, "max_bytes": 8000, "scope_id": "scope-1", "content": "evidence"}
        )
        return await super().astream_events(input, config=config, version=version)


class FailingGraph:
    async def astream_events(self, input: dict[str, Any], *, config: Any, version: str) -> FakeRun:
        raise RuntimeError("local provider unavailable")


def sse_events(body: str) -> list[dict[str, Any]]:
    return [json.loads(line.removeprefix("data: ")) for line in body.splitlines() if line.startswith("data: ")]


@pytest.mark.anyio
async def test_resolve_calls_sync_and_async_output_projections() -> None:
    async def async_output() -> dict[str, str]:
        return {"status": "completed"}

    assert await _resolve(lambda: {"status": "completed"}) == {"status": "completed"}
    assert await _resolve(lambda: async_output()) == {"status": "completed"}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, FakeGraph]:
    fake_graph = FakeGraph()
    monkeypatch.setattr(routes, "graph", fake_graph)
    return TestClient(routes.app), fake_graph


def test_custom_health_is_public() -> None:
    response = TestClient(routes.app).get("/custom/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_stream_returns_only_the_answer_and_discards_protocol_projections(
    client: tuple[TestClient, FakeGraph],
) -> None:
    test_client, fake_graph = client
    response = test_client.post(
        "/custom/stream",
        json={"thread_id": "thread-123", "messages": [{"role": "user", "content": "Explain v3"}]},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert fake_graph.calls == [
        {
            "input": {"messages": [{"role": "user", "content": "Explain v3"}]},
            "config": {"configurable": {"thread_id": "thread-123"}},
            "version": "v3",
        }
    ]
    assert sse_events(response.text) == [
        {
            "kind": "message",
            "source": "coordinator",
            "path": [],
            "text": "coordinator result",
            "final": False,
        }
    ]


def test_stream_forwards_powercontext_recall_events(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes, "graph", PowerContextFakeGraph())
    response = TestClient(routes.app).post(
        "/custom/stream",
        json={"thread_id": "recall-thread", "messages": [{"role": "user", "content": "recall"}]},
    )

    assert response.status_code == 200
    events = sse_events(response.text)
    assert [event["kind"] for event in events] == ["powercontext", "message"]
    assert events[0] == {
        "kind": "powercontext",
        "status": "ready",
        "content_bytes": 12,
        "max_bytes": 8000,
        "scope_id": "scope-1",
        "content": "evidence",
    }


def test_stream_returns_structured_error_event(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes, "graph", FailingGraph())
    response = TestClient(routes.app).post(
        "/custom/stream",
        json={"thread_id": "failing-thread", "messages": [{"role": "user", "content": "fail"}]},
    )

    assert response.status_code == 200
    assert sse_events(response.text) == [
        {"kind": "error", "message": "Event stream failed: local provider unavailable"}
    ]


def test_stream_reuses_the_same_thread_id_for_follow_up_requests(
    client: tuple[TestClient, FakeGraph],
) -> None:
    test_client, fake_graph = client
    for content in ("first", "follow up"):
        response = test_client.post(
            "/custom/stream",
            json={"thread_id": "stable-thread", "messages": [{"role": "user", "content": content}]},
        )
        assert response.status_code == 200

    assert [call["config"] for call in fake_graph.calls] == [
        {"configurable": {"thread_id": "stable-thread"}},
        {"configurable": {"thread_id": "stable-thread"}},
    ]


@pytest.mark.parametrize(
    "thread_fields",
    [{}, {"thread_id": None}, {"thread_id": ""}, {"thread_id": " \t\n"}],
    ids=["missing", "null", "empty", "whitespace"],
)
def test_stream_rejects_invalid_thread_before_starting_graph(
    client: tuple[TestClient, FakeGraph], thread_fields: dict[str, Any]
) -> None:
    test_client, fake_graph = client
    response = test_client.post(
        "/custom/stream",
        json={**thread_fields, "messages": [{"role": "user", "content": "hello"}]},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "thread_id"]
    assert fake_graph.calls == []


def test_stream_rejects_empty_messages() -> None:
    response = TestClient(routes.app).post("/custom/stream", json={"thread_id": "empty-messages", "messages": []})
    assert response.status_code == 422
