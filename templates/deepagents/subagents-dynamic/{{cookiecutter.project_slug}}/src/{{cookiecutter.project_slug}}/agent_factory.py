"""Build one isolated Dynamic Subagents graph for each teaching pattern."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from deepagents import create_deep_agent, register_harness_profile
from deepagents.profiles import GeneralPurposeSubagentProfile, HarnessProfile
from langchain_quickjs import CodeInterpreterMiddleware

from {{ cookiecutter.project_slug }}.fixture_workspace import make_fixture_tools
from {{ cookiecutter.project_slug }}.patterns import PatternSpec

_registered_providers: set[str] = set()


def ensure_harness_profile(provider_key: str) -> None:
    """Disable the implicit general-purpose role once per model provider."""
    if provider_key in _registered_providers:
        return
    profile = HarnessProfile(
        general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
    )
    register_harness_profile(provider_key, profile)
    _registered_providers.add(provider_key)


def build_pattern_graph(
    model: Any,
    spec: PatternSpec,
    examples_root: Path,
    provider_key: str,
) -> Any:
    """Build an agent whose available specialists match exactly one pattern."""
    ensure_harness_profile(provider_key)
    ptc_tools: list[Any] = []
    specialist_tools: list[Any] = []
    if spec.fixture_directory:
        glob_tool, read_file_tool = make_fixture_tools(examples_root / spec.fixture_directory)
        ptc_tools.append(glob_tool)
        specialist_tools.append(read_file_tool)

    subagents = []
    for role in spec.subagents:
        subagent: dict[str, Any] = {
            "name": role.name,
            "description": role.description,
            "system_prompt": role.system_prompt,
        }
        if specialist_tools:
            subagent["tools"] = specialist_tools
        subagents.append(subagent)

    interpreter = CodeInterpreterMiddleware(
        ptc=ptc_tools,
        subagents=True,
        mode="turn",
        max_ptc_calls=32,
        timeout=300.0,
        memory_limit=32 * 1024 * 1024,
        max_result_chars=24_000,
    )
    return create_deep_agent(
        model=model,
        system_prompt=spec.coordinator_prompt,
        subagents=subagents,
        middleware=[interpreter],
    )
