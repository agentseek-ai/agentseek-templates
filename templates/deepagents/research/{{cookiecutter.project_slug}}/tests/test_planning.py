from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from scripted_model import ScriptedModel, call

from {{ cookiecutter.project_slug }}.agent import build_graph


def test_research_streams_real_todo_state():
    model = ScriptedModel(replies=[
        call("write_todos", {"todos": [{"content": "Review evidence", "status": "in_progress"}]}, "plan"),
        call("write_todos", {"todos": [{"content": "Review evidence", "status": "completed"}]}, "done"),
        AIMessage(content="Checked."),
    ])
    graph = build_graph(model, checkpointer=InMemorySaver())
    snapshots = list(graph.stream({"messages": [{"role": "user", "content": "Plan the research."}]},
                                 {"configurable": {"thread_id": "research"}}, stream_mode="values"))
    statuses = [s["todos"][0]["status"] for s in snapshots if s.get("todos")]
    assert "in_progress" in statuses and statuses[-1] == "completed"
    assert graph.get_state({"configurable": {"thread_id": "research"}}).values["todos"][0]["status"] == "completed"
