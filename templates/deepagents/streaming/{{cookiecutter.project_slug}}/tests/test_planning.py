from __future__ import annotations

import json
import os

from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk

os.environ.setdefault("OPENAI_API_KEY", "offline-test-key")
os.environ.setdefault("AGENTSEEK_MODEL_PROVIDER", "openai")
os.environ.setdefault("AGENTSEEK_MODEL", "offline-test-model")

from {{ cookiecutter.project_slug }} import routes  # noqa: E402
from {{ cookiecutter.project_slug }}.agent import build_stream_graph  # noqa: E402


class PlanningModel(GenericFakeChatModel):
    """Replace only the provider; the graph executes real planning and tools."""

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        return self

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        message = self._generate(messages, stop=stop, **kwargs).generations[0].message
        chunk = ChatGenerationChunk(
            message=AIMessageChunk(
                content=message.content,
                tool_call_chunks=[
                    {"name": call["name"], "args": json.dumps(call["args"]), "id": call["id"], "index": index}
                    for index, call in enumerate(message.tool_calls)
                ],
                chunk_position="last",
            )
        )
        if run_manager is not None:
            run_manager.on_llm_new_token(str(message.content), chunk=chunk)
        yield chunk


def tool_call(name, args, call_id):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}])


def planning_model():
    return PlanningModel(
        messages=iter(
            [
                tool_call(
                    "write_todos",
                    {"todos": [{"content": "Coordinate explanation", "status": "in_progress"}]},
                    "coordinator-plan",
                ),
                tool_call(
                    "task", {"description": "Research Event Streaming v3.", "subagent_type": "researcher"}, "delegation"
                ),
                tool_call(
                    "write_todos", {"todos": [{"content": "Inspect topic", "status": "in_progress"}]}, "researcher-plan"
                ),
                tool_call("inspect_streaming_topic", {"topic": "Event Streaming v3"}, "inspect"),
                tool_call(
                    "write_todos", {"todos": [{"content": "Inspect topic", "status": "completed"}]}, "researcher-done"
                ),
                AIMessage(content="Research complete."),
                tool_call(
                    "write_todos",
                    {"todos": [{"content": "Coordinate explanation", "status": "completed"}]},
                    "coordinator-done",
                ),
                AIMessage(content="Coordinator summary."),
            ]
        )
    )


def test_planning_and_delegation_keep_real_v3_tool_boundaries(monkeypatch):
    graph = build_stream_graph(planning_model())
    monkeypatch.setattr(routes, "graph", graph)
    response = TestClient(routes.app).post(
        "/custom/stream", json={"thread_id": "planning-v3", "messages": [{"role": "user", "content": "Explain v3."}]}
    )
    assert response.status_code == 200
    events = [
        json.loads(line.removeprefix("data: ")) for line in response.text.splitlines() if line.startswith("data: ")
    ]
    assert not any(event["kind"] == "error" for event in events)
    snapshot = graph.get_state({"configurable": {"thread_id": "planning-v3"}})
    assert snapshot.values.get("todos") == [{"content": "Coordinate explanation", "status": "completed"}]
    completed = [event for event in events if event["kind"] == "tool_call" and event.get("phase") == "completed"]
    assert any(
        event.get("source") == "coordinator"
        and event.get("tool_name") == "write_todos"
        and "Updated todo list" in str(event.get("output"))
        for event in completed
    )
    assert any(
        event.get("source") == "subagent"
        and event.get("tool_name") == "write_todos"
        and "Updated todo list" in str(event.get("output"))
        for event in completed
    )
    assert any(
        event.get("source") == "subagent"
        and event.get("tool_name") == "inspect_streaming_topic"
        and "Local reference lookup completed" in str(event.get("output"))
        for event in completed
    )
    assert any(
        event["kind"] == "subagent" and event["phase"] == "completed" and event["name"] == "researcher"
        for event in events
    )
    assert {event["kind"] for event in events} >= {"message", "subagent", "tool_call", "values", "output", "raw"}
