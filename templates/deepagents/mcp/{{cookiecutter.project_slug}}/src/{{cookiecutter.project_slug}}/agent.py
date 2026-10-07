"""Lazy DeepAgents graph assembly from configured MCP tools."""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from deepagents import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    create_deep_agent,
    register_harness_profile,
)
from langgraph.graph.state import CompiledStateGraph

from {{ cookiecutter.project_slug }}.config import load_mcp_config
from {{ cookiecutter.project_slug }}.mcp_tools import load_mcp_tools
from {{ cookiecutter.project_slug }}.model import resolve_model_binding


@dataclass(frozen=True)
class RuntimeBundle:
    """Resources retained for the lifetime of a successfully built graph."""

    client: object
    tool_names: tuple[str, ...]
    graph: CompiledStateGraph


_runtime: RuntimeBundle | None = None
_runtime_lock = threading.Lock()


def build_graph(model_binding, loaded, *, checkpointer=None, extra_tools=(), interrupt_on=None):
    """Use the reviewed 0.6.12 profile for app and SDK approval experiments."""
    profile = HarnessProfile(
        general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
    )
    register_harness_profile(model_binding.profile_key, profile)
    graph = create_deep_agent(
        model=model_binding.model,
        tools=[*loaded.tools, *extra_tools],
        checkpointer=checkpointer,
        interrupt_on=interrupt_on,
        subagents=[],
        system_prompt=(
            "You are an assistant connected to external tools through MCP. "
            "Use the available tools when they are relevant. "
            "Answer in the same language as the user's question."
        ),
    )
    return graph


async def _build_runtime() -> RuntimeBundle:
    config = load_mcp_config(Path(".mcp.json"))
    model_binding = resolve_model_binding()
    loaded = await load_mcp_tools(config)
    graph = build_graph(model_binding, loaded)
    return RuntimeBundle(
        client=loaded.client,
        tool_names=loaded.tool_names,
        graph=graph,
    )


def _build_runtime_in_worker() -> RuntimeBundle:
    return asyncio.run(_build_runtime())


def make_graph() -> CompiledStateGraph:
    """Return the cached graph, building one complete runtime on first use."""
    global _runtime
    if _runtime is not None:
        return _runtime.graph
    with _runtime_lock:
        if _runtime is None:
            # AgentSeek API 0.2.3 invokes graph factories synchronously from an
            # async request. Use a worker so MCP discovery can own its event loop.
            with ThreadPoolExecutor(max_workers=1, thread_name_prefix="mcp-graph-build") as executor:
                _runtime = executor.submit(_build_runtime_in_worker).result()
        return _runtime.graph
