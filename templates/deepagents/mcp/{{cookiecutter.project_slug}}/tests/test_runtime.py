"""Exercise the shipped 0.7 graph and real MCP transport boundaries."""
from __future__ import annotations

import asyncio
import json
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from {{ cookiecutter.project_slug }}.agent import build_graph
from {{ cookiecutter.project_slug }}.approval_smoke import verify_approval
from {{ cookiecutter.project_slug }}.mcp_smoke import run_smoke
from {{ cookiecutter.project_slug }}.mcp_tools import (
    MCPDiscoveryError,
    RESERVED_DEEPAGENTS_TOOL_NAMES,
    _validate_final_names,
)
from {{ cookiecutter.project_slug }}.model import ModelBinding


class PlanningModel(BaseChatModel):
    model_name: str = "mcp-runtime-test"
    seen_tools: list[str] = []

    def _get_ls_params(self, stop=None, **kwargs):
        return {"ls_provider": "openai", "ls_model_name": self.model_name, "ls_model_type": "chat"}

    @property
    def _llm_type(self):
        return "mcp-runtime-test"

    def bind_tools(self, tools, **kwargs):
        self.seen_tools = [tool.name for tool in tools]
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if any(message.type == "tool" for message in messages):
            reply = AIMessage(content="Plan saved.")
        else:
            reply = AIMessage(content="", tool_calls=[{
                "name": "write_todos",
                "args": {"todos": [{"content": "Inspect the MCP calculation", "status": "in_progress"}]},
                "id": "plan",
            }])
        return ChatResult(generations=[ChatGeneration(message=reply)])


def test_graph_keeps_working_todo_planning_with_no_general_purpose_task():
    model = PlanningModel()
    binding = ModelBinding(model, "openai", model.model_name, f"openai:{model.model_name}")
    graph = build_graph(binding, SimpleNamespace(tools=()))
    result = graph.invoke({"messages": [{"role": "user", "content": "Plan the calculator check."}]})

    assert result.get("todos") == [{"content": "Inspect the MCP calculation", "status": "in_progress"}]
    assert "write_todos" in model.seen_tools
    assert "task" not in model.seen_tools
    assert "execute" not in model.seen_tools


def test_collision_guards_match_the_actual_state_backend_tool_registry():
    model = PlanningModel()
    binding = ModelBinding(model, "openai", model.model_name, f"openai:{model.model_name}")
    graph = build_graph(binding, SimpleNamespace(tools=()))
    names = frozenset(graph.nodes["tools"].bound.tools_by_name)

    assert names == frozenset({
        "delete", "edit_file", "execute", "glob", "grep", "ls", "read_file", "write_file", "write_todos",
    })
    assert RESERVED_DEEPAGENTS_TOOL_NAMES == names


def test_external_delete_name_cannot_override_builtin_deletion():
    with pytest.raises(MCPDiscoveryError, match="enabled DeepAgents built-in"):
        _validate_final_names(["external"], [[SimpleNamespace(name="delete")]])


@pytest.fixture
def calculator_config(tmp_path: Path) -> Path:
    root = Path(__file__).resolve().parents[1]
    payload = json.loads((root / ".mcp.json").read_text())
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    payload["mcpServers"]["calculator_http"]["url"] = f"http://127.0.0.1:{port}/mcp"
    path = tmp_path / ".mcp.json"
    path.write_text(json.dumps(payload))
    return path


def test_real_stdio_and_streamable_http_calculators(calculator_config):
    result = asyncio.run(run_smoke(calculator_config))
    assert result.tool_names == (
        "calculator_add", "calculator_multiply", "calculator_http_add", "calculator_http_multiply",
    )
    assert result.stdio_calculation == "95"
    assert result.http_calculation == "2146"


def test_publication_waits_for_approval_and_rejection_has_no_log_delta(calculator_config, tmp_path):
    output = tmp_path / "publication"
    result = asyncio.run(verify_approval(calculator_config, output))
    assert result == {"approve": {"before": 0, "after": 1}, "reject": {"before": 0, "after": 0}}
    assert json.loads((output / "approve.jsonl").read_text()) == {"stdio": "95", "http": "2146"}
    assert not (output / "reject.jsonl").exists()
