from __future__ import annotations

import os

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

os.environ.setdefault("OPENAI_API_KEY", "offline-test-key")
os.environ.setdefault("AGENTSEEK_MODEL_PROVIDER", "openai")
os.environ.setdefault("AGENTSEEK_MODEL", "offline-test-model")

from {{ cookiecutter.project_slug }}.agent import build_stream_graph  # noqa: E402


class PlanningModel(GenericFakeChatModel):
    """Replace only the provider; the graph executes real planning and tools."""

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        return self


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
                tool_call("release_checklist", {"topic": "Event Streaming v3"}, "inspect"),
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


@pytest.mark.anyio
async def test_planning_state_remains_separate_for_coordinator_and_researcher():
    from {{ cookiecutter.project_slug }}.powercontext_middleware import recall_options

    token = recall_options.set((False, None))
    try:
        graph = build_stream_graph(planning_model())
        snapshots = [
            item
            async for item in graph.astream(
                {"messages": [{"role": "user", "content": "Explain v3."}]},
                {"configurable": {"thread_id": "planning-subgraphs"}},
                stream_mode="values",
                subgraphs=True,
            )
        ]
    finally:
        recall_options.reset(token)
    coordinator = [
        state["todos"][0]["status"] for namespace, state in snapshots if not namespace and state.get("todos")
    ]
    researcher = [state["todos"][0]["status"] for namespace, state in snapshots if namespace and state.get("todos")]
    assert "in_progress" in coordinator and coordinator[-1] == "completed"
    assert "in_progress" in researcher and researcher[-1] == "completed"
    tool_messages = [
        message for namespace, state in snapshots for message in state.get("messages", []) if message.type == "tool"
    ]
    assert all(message.status == "success" for message in tool_messages)
    assert any(
        message.name == "release_checklist" and "Release planning checklist" in message.content
        for message in tool_messages
    )
