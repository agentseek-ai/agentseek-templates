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

from {{ cookiecutter.project_slug }} import routes  # noqa: E402
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
    tool_name = "inspect_streaming_topic"
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


class FailingGraph:
    async def astream_events(self, input: dict[str, Any], *, config: Any, version: str) -> FakeRun:
        raise RuntimeError("local provider unavailable")


class OutputFailRun(FakeRun):
    async def output(self) -> dict[str, list[str]]:
        raise RuntimeError("output projection unavailable")


class OutputFailGraph:
    async def astream_events(self, input: dict[str, Any], *, config: Any, version: str) -> OutputFailRun:
        return OutputFailRun()


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


def test_stream_projects_all_v3_channels_and_preserves_thread_config(
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
    events = sse_events(response.text)
    assert {event["kind"] for event in events} == {
        "message",
        "subagent",
        "tool_call",
        "values",
        "output",
        "raw",
    }
    assert any(event.get("source") == "coordinator" for event in events if event["kind"] == "message")
    assert any(event.get("path") == ["researcher:fake"] for event in events if event["kind"] == "subagent")
    assert any(event.get("phase") == "completed" for event in events if event["kind"] == "tool_call")
    assert any(event.get("sequence") == 7 for event in events if event["kind"] == "raw")
    output_events = [event for event in events if event["kind"] == "output"]
    assert output_events == [{"kind": "output", "output": {"messages": ["final"]}, "phase": "completed"}]


def test_stream_returns_structured_error_event(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes, "graph", FailingGraph())
    response = TestClient(routes.app).post(
        "/custom/stream",
        json={"messages": [{"role": "user", "content": "fail"}]},
    )

    assert response.status_code == 200
    assert sse_events(response.text) == [
        {"kind": "error", "message": "Event stream failed: local provider unavailable"}
    ]


def test_output_method_is_called_and_output_failure_is_structured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(routes, "graph", OutputFailGraph())
    response = TestClient(routes.app).post(
        "/custom/stream",
        json={"messages": [{"role": "user", "content": "output failure"}]},
    )

    assert response.status_code == 200
    assert {
        "kind": "output",
        "output": None,
        "phase": "failed",
        "error": "output projection unavailable",
    } in sse_events(response.text)


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


def test_stream_rejects_empty_messages() -> None:
    response = TestClient(routes.app).post("/custom/stream", json={"messages": []})
    assert response.status_code == 422
