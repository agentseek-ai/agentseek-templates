"""Two-stage LangChain research and presentation binding, driven through Bub."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypedDict

from agentseek_langchain import messages_spec
from agentseek_langchain.spec import default_runnable_config
from copilotkit import CopilotKitMiddleware, CopilotKitState
from langchain.agents import create_agent
from langchain_core.callbacks.manager import AsyncCallbackManagerForChainRun
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig, RunnableLambda
from langchain_core.runnables.config import patch_config

from .middleware import normalize_context
from .relay import configure_relay, relay_config_builder, relay_middleware
from .settings import get_settings
from .tools import tavily_search, think_tool


class AgentState(CopilotKitState):
    pass


class AgentContext(TypedDict, total=False):
    output_schema: dict[str, Any]


RESEARCH_SYSTEM_PROMPT = """你是研究阶段 Agent。

当用户要求搜索、查资料、获取最新信息或验证事实时，必须调用 tavily_search。
只有在 tavily_search 返回结果后，才能结束研究阶段。
不得把“正在搜索”“正在检索”“请稍候”作为最终研究结果。
如果搜索失败，必须明确返回失败原因。
请保留搜索结果中的标题、URL 和关键内容，供后续展示阶段使用。"""

PRESENTATION_SYSTEM_PROMPT = """你是最终展示阶段 Agent。

请根据研究阶段已经返回的内容生成最终回答。
使用普通 Markdown 输出，确保前端可以直接展示。

研究阶段的结果必须被完整、准确地展示。
不要自行编造搜索结果。
不要再次调用搜索工具。
不要输出 JSON。
不要输出 ui、Markdown、props 等结构化 UI 字段。
不要输出“正在搜索”“正在检索”“请稍候”等占位内容。

最终结果应当包含：
- 对用户问题的直接回答；
- 搜索结果标题；
- 搜索结果 URL；
- 必要时提供简短摘要；
- 如果研究阶段失败，明确说明失败原因和重试建议。"""

MAX_PRESENTATION_RESEARCH_CHARS = 12_000
_SEARCH_TERMS = (
    "搜索",
    "检索",
    "查资料",
    "最新",
    "验证事实",
    "search",
    "research",
    "latest",
    "verify",
)


def _base_agent_options(settings: Any) -> dict[str, Any]:
    """Return the shared model/state configuration without creating a second Relay."""
    model = settings.model.strip()
    if not model:
        msg = "Set BUB_MODEL (e.g. openai:gpt-4o-mini) for the {{ cookiecutter.project_name }} agent."
        raise RuntimeError(msg)
    return {"model": model, "context_schema": AgentContext, "state_schema": AgentState}


def build_research_agent(settings: Any | None = None) -> Any:
    """Build the tool-enabled stage; it deliberately has no structured output."""
    settings = settings or get_settings()
    return create_agent(
        **_base_agent_options(settings),
        tools=[tavily_search, think_tool],
        middleware=[
            normalize_context,
            CopilotKitMiddleware(),
            *relay_middleware(settings),
        ],
        system_prompt=RESEARCH_SYSTEM_PROMPT,
    )


def build_presentation_agent(settings: Any | None = None) -> Any:
    """Build the Markdown-only stage; it cannot make a second web request."""
    settings = settings or get_settings()
    return create_agent(
        **_base_agent_options(settings),
        tools=[],
        middleware=[
            normalize_context,
            CopilotKitMiddleware(),
            *relay_middleware(settings),
        ],
        system_prompt=PRESENTATION_SYSTEM_PROMPT,
    )


def _message_text(message: Any) -> str:
    content = getattr(message, "content", message)
    return content if isinstance(content, str) else str(content)


def _search_requested(input: object) -> bool:
    """Identify requests whose research stage must produce Tavily evidence."""
    if not isinstance(input, Mapping):
        return False
    messages = input.get("messages", [])
    if not isinstance(messages, list) or not messages:
        return False
    question = _message_text(messages[-1]).lower()
    return any(term in question for term in _SEARCH_TERMS)


def _has_tavily_evidence(result: object) -> bool:
    """Return whether the research graph actually completed a Tavily tool call."""
    if not isinstance(result, Mapping):
        return False
    messages = result.get("messages", [])
    return isinstance(messages, list) and any(
        getattr(message, "name", None) == "tavily_search" for message in messages
    )


def _research_failure(input: object, error: str) -> dict[str, Any]:
    """Represent a failed research stage so presentation can produce final UI."""
    messages = list(input.get("messages", [])) if isinstance(input, Mapping) else []
    messages.append(AIMessage(content=f"研究阶段失败：{error}"))
    return {"messages": messages, "research_error": error}


def _research_summary(result: object) -> str:
    """Extract bounded evidence while retaining Tavily titles and URLs first."""
    if isinstance(result, Mapping):
        messages = result.get("messages", [])
        if isinstance(messages, list):
            tool_evidence = [
                _message_text(message).strip()
                for message in messages
                if getattr(message, "name", None) == "tavily_search"
                and _message_text(message).strip()
            ]
            rendered = [
                _message_text(message).strip()
                for message in messages
                if getattr(message, "type", None) == "ai"
                and _message_text(message).strip()
            ]
            evidence = "\n\n".join(tool_evidence + rendered)
            if evidence:
                return evidence[:MAX_PRESENTATION_RESEARCH_CHARS]
    return _message_text(result).strip()[:MAX_PRESENTATION_RESEARCH_CHARS]


def build_presentation_input(
    original_input: object, research_result: object
) -> dict[str, Any]:
    """Pass original context plus bounded research evidence to the UI-only agent."""
    state = (
        dict(original_input)
        if isinstance(original_input, Mapping)
        else {"messages": []}
    )
    messages = list(state.get("messages", []))
    original_question = _message_text(messages[-1]) if messages else "(未提供原始问题)"
    research = (
        _research_summary(research_result)
        or "研究阶段没有返回内容；请说明无法完成研究并给出重试建议。"
    )
    research_error = "无"
    if isinstance(research_result, Mapping):
        candidate = research_result.get("research_error")
        if isinstance(candidate, str) and candidate.strip():
            research_error = candidate.strip()
    messages.append(
        HumanMessage(
            content=(
                "请把以下已完成的研究结果转换为最终 Markdown 回答。\n\n"
                f"原始用户问题：\n{original_question}\n\n"
                f"研究阶段结果：\n{research}\n\n"
                f"研究阶段错误：\n{research_error}"
            )
        )
    )
    state["messages"] = messages
    return state


def build_agent() -> Any:
    """Build one protocol-compatible runnable that nests both Relay-instrumented stages."""
    settings = get_settings()
    settings.apply_openai_env_bridge()
    configure_relay(settings)
    research_agent = build_research_agent(settings)
    presentation_agent = build_presentation_agent(settings)

    async def run_research_then_present(
        input: object,
        config: RunnableConfig | None = None,
        context: AgentContext | None = None,
        run_manager: AsyncCallbackManagerForChainRun | None = None,
    ) -> object:
        """Run both stages under the request callback config supplied by ``messages_spec``."""
        research_config = patch_config(
            config,
            callbacks=run_manager.get_child() if run_manager else None,
            run_name="research_agent",
        )
        try:
            research_result = await research_agent.ainvoke(
                input, config=research_config, context=context
            )
            if _search_requested(input) and not _has_tavily_evidence(research_result):
                retry_input = (
                    dict(input) if isinstance(input, Mapping) else {"messages": []}
                )
                retry_messages = list(retry_input.get("messages", []))
                retry_messages.append(
                    HumanMessage(
                        content="这是搜索类请求。你尚未调用 tavily_search；现在必须调用它并返回标题、URL 和关键内容。"
                    )
                )
                retry_input["messages"] = retry_messages
                research_result = await research_agent.ainvoke(
                    retry_input, config=research_config, context=context
                )
            if _search_requested(input) and not _has_tavily_evidence(research_result):
                research_result = _research_failure(
                    input,
                    "研究 Agent 未调用 tavily_search，因此不能把未验证内容作为联网搜索结果展示。",
                )
        except Exception as exc:
            research_result = _research_failure(input, f"{type(exc).__name__}: {exc}")
        presentation_input = build_presentation_input(input, research_result)
        presentation_config = patch_config(
            config,
            callbacks=run_manager.get_child() if run_manager else None,
            run_name="presentation_agent",
        )
        return await presentation_agent.ainvoke(
            presentation_input, config=presentation_config, context=context
        )

    return RunnableLambda(run_research_then_present, name="research_then_present")


def build_spec():
    """Return a `RunnableSpec` for ``BUB_LANGCHAIN_SPEC``."""
    settings = get_settings()
    return messages_spec(
        build_agent(),
        include_agents_md=True,
        config_builder=relay_config_builder
        if settings.relay_enabled
        else default_runnable_config,
    )
