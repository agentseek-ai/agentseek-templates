from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from {{ cookiecutter.project_slug }}.demo_binding import (
    MAX_PRESENTATION_RESEARCH_CHARS,
    PRESENTATION_SYSTEM_PROMPT,
    build_presentation_agent,
    build_research_agent,
    _has_tavily_evidence,
    _research_failure,
    _search_requested,
    build_presentation_input,
)


class _Settings:
    model = "openai:gpt-4o-mini"
    relay_enabled = False


def _middleware_names(agent: object) -> list[str]:
    return [
        getattr(item, "__name__", type(item).__name__)
        for item in getattr(agent, "middleware", [])
    ]


def test_presentation_agent_does_not_force_provider_strategy() -> None:
    agent = build_presentation_agent(_Settings())

    assert "apply_structured_output_schema" not in _middleware_names(agent)
    assert agent.tools == []
    assert "普通 Markdown" in PRESENTATION_SYSTEM_PROMPT
    assert "不要输出 JSON" in PRESENTATION_SYSTEM_PROMPT


def test_research_agent_keeps_tavily_and_think_tool() -> None:
    agent = build_research_agent(_Settings())

    tool_names = {getattr(tool, "name", "") for tool in agent.tools}
    assert {"tavily_search", "think_tool"} <= tool_names
    assert "apply_structured_output_schema" not in _middleware_names(agent)


def test_presentation_input_preserves_question_and_research_evidence() -> None:
    original = {
        "messages": [HumanMessage(content="请搜索 NeMo Relay 官方文档")],
        "copilotkit": {"context": []},
    }
    research = {
        "messages": [
            HumanMessage(content="请搜索 NeMo Relay 官方文档"),
            ToolMessage(
                content="## Official docs\nURL: https://docs.nvidia.com/nemo/relay",
                tool_call_id="call-1",
                name="tavily_search",
            ),
            AIMessage(content="已找到官方文档，标题和 URL 如上。"),
        ]
    }

    presentation = build_presentation_input(original, research)

    assert presentation["copilotkit"] == original["copilotkit"]
    prompt = presentation["messages"][-1].content
    assert "原始用户问题：" in prompt
    assert "https://docs.nvidia.com/nemo/relay" in prompt
    assert "研究阶段结果：" in prompt


def test_presentation_input_bounds_research_context() -> None:
    original = {"messages": [HumanMessage(content="search")]}
    research = {"messages": [AIMessage(content="x" * (MAX_PRESENTATION_RESEARCH_CHARS + 500))]}

    presentation = build_presentation_input(original, research)

    assert len(presentation["messages"][-1].content) < MAX_PRESENTATION_RESEARCH_CHARS + 1_000


def test_search_request_requires_named_tavily_tool_evidence() -> None:
    search_input = {"messages": [HumanMessage(content="请搜索最新 NeMo Relay 文档")]}
    result = {
        "messages": [
            ToolMessage(
                content="URL: https://docs.nvidia.com",
                tool_call_id="call-1",
                name="tavily_search",
            )
        ]
    }

    assert _search_requested(search_input)
    assert _has_tavily_evidence(result)


def test_research_failure_is_passed_to_presentation() -> None:
    original = {"messages": [HumanMessage(content="请搜索")]}

    presentation = build_presentation_input(original, _research_failure(original, "Tavily timeout"))

    assert "研究阶段错误：\nTavily timeout" in presentation["messages"][-1].content
