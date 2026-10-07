from types import SimpleNamespace

from langchain_core.messages import AIMessage, ToolMessage
from scripted_model import ScriptedModel, call

from {{ cookiecutter.project_slug }} import demo_binding


def test_default_streams_planning_state_while_executing_its_tool(monkeypatch) -> None:
    model = ScriptedModel(
        replies=[
            call("write_todos", {"todos": [{"content": "Outline the answer", "status": "in_progress"}]}, "plan"),
            call("outline_answer", {"topic": "0.7 compatibility"}, "outline"),
            call("write_todos", {"todos": [{"content": "Outline the answer", "status": "completed"}]}, "done"),
            AIMessage(content="Outlined."),
        ]
    )
    monkeypatch.setattr(
        demo_binding,
        "get_settings",
        lambda: SimpleNamespace(
            require_model=lambda: model,
            apply_openai_env_bridge=lambda: None,
        ),
    )

    snapshots = list(
        demo_binding.build_agent().stream(
            {"messages": [{"role": "user", "content": "Plan and outline a compatibility answer."}]},
            stream_mode="values",
        )
    )

    statuses = [state["todos"][0]["status"] for state in snapshots if state.get("todos")]
    assert "in_progress" in statuses
    assert statuses[-1] == "completed"
    assert snapshots[-1]["messages"][-1].content == "Outlined."
    outline_results = [
        message
        for message in snapshots[-1]["messages"]
        if isinstance(message, ToolMessage) and message.name == "outline_answer"
    ]
    assert len(outline_results) == 1
    assert "Suggested outline for 0.7 compatibility" in outline_results[0].content
