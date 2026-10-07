import importlib
import os
import sys

from deepagents.backends import LocalShellBackend
from langchain_core.messages import AIMessage, ToolMessage
from scripted_model import ScriptedModel, call

from {{ cookiecutter.project_slug }} import runtime


def test_sandbox_streams_planning_state_and_executes_inside_its_workspace(tmp_path, monkeypatch):
    model = ScriptedModel(
        replies=[
            call("write_todos", {"todos": [{"content": "Check the file", "status": "in_progress"}]}, "plan"),
            call("write_file", {"file_path": "/answer.txt", "content": "workspace evidence"}, "write"),
            call("execute", {"command": "cat answer.txt"}, "execute"),
            call("write_todos", {"todos": [{"content": "Check the file", "status": "completed"}]}, "done"),
            AIMessage(content="Checked the workspace."),
        ]
    )
    backend = LocalShellBackend(root_dir=tmp_path, env={"PATH": os.environ["PATH"]})
    monkeypatch.setattr(runtime, "get_backend", lambda: backend)
    monkeypatch.setattr("langchain.chat_models.init_chat_model", lambda **kwargs: model)
    monkeypatch.delitem(sys.modules, "{{ cookiecutter.project_slug }}.agent", raising=False)
    agent = importlib.import_module("{{ cookiecutter.project_slug }}.agent")

    snapshots = list(
        agent.graph.stream(
            {"messages": [{"role": "user", "content": "Plan, write a file, and check its contents."}]},
            stream_mode="values",
        )
    )

    statuses = [state["todos"][0]["status"] for state in snapshots if state.get("todos")]
    assert "in_progress" in statuses
    assert statuses[-1] == "completed"
    assert (tmp_path / "answer.txt").read_text() == "workspace evidence"
    execute_results = [
        message
        for message in snapshots[-1]["messages"]
        if isinstance(message, ToolMessage) and message.name == "execute"
    ]
    assert len(execute_results) == 1
    assert "workspace evidence" in execute_results[0].content
