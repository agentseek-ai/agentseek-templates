import shutil
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from scripted_model import ScriptedModel, call

from {{ cookiecutter.project_slug }} import agent, lesson_tools


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = Path(agent.EXAMPLE_DIR)
    for relative in ("AGENTS.md", "memory/preferences.md", "subagents.yaml"):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((root / relative).read_text())
    shutil.copytree(root / "skills", tmp_path / "skills")
    (tmp_path / "sources").mkdir()
    for source in (root / "sources").glob("*.md"):
        (tmp_path / "sources" / source.name).write_text(source.read_text())
    monkeypatch.setattr(agent, "EXAMPLE_DIR", tmp_path)
    monkeypatch.setattr(lesson_tools, "EXAMPLE_DIR", tmp_path)
    return tmp_path


def test_text_mode_plans_reads_saves_and_reads_back(workspace):
    report = "# Course report\n\n## Context\nPlan before acting.\n\n## Findings\nCheck real files.\n\n## Sources\n- sources/planning.md\n- sources/files.md\n- sources/memory.md\n"
    model = ScriptedModel(replies=[
        call("write_todos", {"todos": [{"content": "Write report", "status": "in_progress"}]}, "plan"),
        call("read_source", {"name": "planning.md"}, "source1"),
        call("read_source", {"name": "files.md"}, "source2"),
        call("read_source", {"name": "memory.md"}, "source3"),
        call("save_report", {"slug": "course", "content": report}, "save"),
        call("read_report", {"slug": "course"}, "readback"),
        call("write_todos", {"todos": [{"content": "Write report", "status": "completed"}]}, "done"),
        AIMessage(content="Report checked."),
    ])
    graph = agent.build_graph(model, checkpointer=InMemorySaver())
    snapshots = list(graph.stream({"messages": [{"role": "user", "content": "Write from local sources."}]},
                                 {"configurable": {"thread_id": "text"}}, stream_mode="values"))
    statuses = [s["todos"][0]["status"] for s in snapshots if s.get("todos")]
    assert "in_progress" in statuses and statuses[-1] == "completed"
    assert (workspace / "blogs/course/post.md").read_text() == report
    tool_messages = {m.tool_call_id: m.content for m in snapshots[-1]["messages"] if m.type == "tool"}
    assert report == tool_messages["readback"]
    assert "Task planning" in tool_messages["source1"]
    assert not {"web_search", "generate_cover", "generate_social_image"} & set(model.seen_tools)
    assert "pure text" in model.prompts[0].lower()


def test_saved_preference_reaches_new_thread_without_old_messages(workspace):
    writer = ScriptedModel(replies=[
        call("save_preference", {"key": "language", "value": "Chinese"}, "remember"),
        AIMessage(content="Saved."),
    ])
    agent.build_graph(writer, checkpointer=InMemorySaver()).invoke(
        {"messages": [{"role": "user", "content": "Remember my language."}]},
        {"configurable": {"thread_id": "old"}},
    )
    assert "language: Chinese" in (workspace / "memory/preferences.md").read_text()
    reader = ScriptedModel(replies=[AIMessage(content="New session.")])
    agent.build_graph(reader, checkpointer=InMemorySaver()).invoke(
        {"messages": [{"role": "user", "content": "Hello fresh session."}]},
        {"configurable": {"thread_id": "new"}},
    )
    assert "language: Chinese" in reader.prompts[0]
    assert "Remember my language." not in reader.prompts[0]
    assert "Only save preferences with save_preference" in reader.prompts[0]
    assert "The user might not explicitly ask" not in reader.prompts[0]
    assert "save new knowledge by calling edit_file" not in reader.prompts[0]


@pytest.mark.parametrize("decision, expected", [("approve", 1), ("reject", 0)])
def test_publication_executes_only_after_approval(workspace, decision, expected):
    lesson_tools.save_report.invoke({"slug": "approval", "content": "# Test report"})
    model = ScriptedModel(replies=[
        call("publish_report", {"slug": "approval"}, "publish"), AIMessage(content="Finished."),
    ])
    graph = agent.build_graph(model, checkpointer=InMemorySaver(), approvals=True)
    config = {"configurable": {"thread_id": decision}}
    paused = graph.invoke({"messages": [{"role": "user", "content": "Publish test report."}]}, config)
    request = paused["__interrupt__"][0].value
    assert request["action_requests"][0]["name"] == "publish_report"
    assert set(request["review_configs"][0]["allowed_decisions"]) == {"approve", "reject"}
    log = workspace / "reports/publications.jsonl"
    assert not log.exists()
    resumed = graph.invoke(Command(resume={"decisions": [{"type": decision}]}), config)
    assert not resumed.get("__interrupt__")
    lines = log.read_text().splitlines() if log.exists() else []
    assert len(lines) == expected
    if lines:
        import json
        assert json.loads(lines[0])["report"] == "blogs/approval/post.md"


@pytest.mark.parametrize("slug", ["../escape", "/tmp/escape", "a/b", ""])
def test_report_tools_reject_escaping_paths(workspace, slug):
    with pytest.raises(ValueError):
        lesson_tools.save_report.invoke({"slug": slug, "content": "Bad"})


def test_optional_tools_need_both_opt_in_and_credentials(workspace, monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("CONTENT_MODE", "full")
    monkeypatch.setenv("CONTENT_ENABLE_SEARCH", "true")
    monkeypatch.setenv("CONTENT_ENABLE_IMAGES", "true")
    with pytest.raises(ValueError, match="TAVILY_API_KEY"):
        agent.build_graph(ScriptedModel(replies=[]))
    monkeypatch.setenv("TAVILY_API_KEY", "unused")
    with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
        agent.build_graph(ScriptedModel(replies=[]))
    monkeypatch.setenv("GOOGLE_API_KEY", "unused")
    model = ScriptedModel(replies=[AIMessage(content="Configured.")])
    agent.build_graph(model).invoke({"messages": [{"role": "user", "content": "Hello"}]})
    assert {"generate_cover", "generate_social_image"} <= set(model.seen_tools)
