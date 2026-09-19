"""A deliberately observable Deep Agents graph for the streaming template."""

from __future__ import annotations

import os
import warnings

from deepagents import create_deep_agent
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import tool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph

from .openai_compat import OpenAICompatibleChatModel
from .powercontext_middleware import powercontext_middleware

load_dotenv()

SUPPORTED_MODEL_PROVIDERS = {
    "openai": "openai",
    "anthropic": "anthropic",
    "google": "google_genai",
    "google_genai": "google_genai",
    "gemini": "google_genai",
}


def _nonempty_env(name: str) -> str | None:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else None


def _normalize_provider(value: str) -> str:
    provider = value.strip().replace("-", "_").lower()
    if provider not in SUPPORTED_MODEL_PROVIDERS:
        raise ValueError("AGENTSEEK_MODEL_PROVIDER must be openai, anthropic, or google_genai")
    return SUPPORTED_MODEL_PROVIDERS[provider]


MODEL = os.getenv("AGENTSEEK_MODEL") or os.getenv("DEEPAGENTS_MODEL") or "{{ cookiecutter.default_model }}"
MODEL_PROVIDER = _normalize_provider(os.getenv("AGENTSEEK_MODEL_PROVIDER", "{{ cookiecutter.default_model_provider }}"))

STREAM_CHUNK_TIMEOUT_S: float | None = 300.0
timeout_value = _nonempty_env("LANGCHAIN_OPENAI_STREAM_CHUNK_TIMEOUT_S")
if timeout_value:
    try:
        parsed_timeout = float(timeout_value)
    except ValueError:
        warnings.warn("Ignoring invalid LANGCHAIN_OPENAI_STREAM_CHUNK_TIMEOUT_S", stacklevel=2)
    else:
        STREAM_CHUNK_TIMEOUT_S = None if parsed_timeout <= 0 else parsed_timeout


@tool
def release_checklist(topic: str) -> str:
    """Return a generic release checklist; it contains no saved project decisions."""
    cleaned = topic.strip() or "the requested topic"
    return (
        f"Release planning checklist for {cleaned}: verify the target environment, "
        "deployment window, approval requirements, rollback plan, and success checks. "
        "This generic checklist does not establish any project-specific decision."
    )


MODEL_INIT_KWARGS: dict[str, object] = {
    "model": MODEL,
    "model_provider": MODEL_PROVIDER,
}
if MODEL_PROVIDER == "openai":
    if _nonempty_env("OPENAI_API_KEY"):
        MODEL_INIT_KWARGS["api_key"] = _nonempty_env("OPENAI_API_KEY")
    if _nonempty_env("OPENAI_API_BASE"):
        MODEL_INIT_KWARGS["base_url"] = _nonempty_env("OPENAI_API_BASE")
    MODEL_INIT_KWARGS["stream_chunk_timeout"] = STREAM_CHUNK_TIMEOUT_S
elif MODEL_PROVIDER == "anthropic":
    if _nonempty_env("ANTHROPIC_API_KEY"):
        MODEL_INIT_KWARGS["api_key"] = _nonempty_env("ANTHROPIC_API_KEY")
    if _nonempty_env("ANTHROPIC_API_URL"):
        MODEL_INIT_KWARGS["base_url"] = _nonempty_env("ANTHROPIC_API_URL")
elif MODEL_PROVIDER == "google_genai":
    if _nonempty_env("GOOGLE_API_KEY"):
        MODEL_INIT_KWARGS["api_key"] = _nonempty_env("GOOGLE_API_KEY")
    if _nonempty_env("GOOGLE_API_BASE"):
        MODEL_INIT_KWARGS["base_url"] = _nonempty_env("GOOGLE_API_BASE")

model = (
    OpenAICompatibleChatModel(**{key: value for key, value in MODEL_INIT_KWARGS.items() if key != "model_provider"})
    if MODEL_PROVIDER == "openai"
    else init_chat_model(**MODEL_INIT_KWARGS)
)

researcher = {
    "name": "researcher",
    "description": "Review a release plan against project decisions and a deployment checklist.",
    "system_prompt": (
        "You are the release researcher. Use release_checklist once. "
        "Use relevant PowerContext evidence to identify project constraints. "
        "If the evidence is absent, say which decisions are unknown instead of inventing them. "
        "Current user instructions override historical notes. Return a concise release recommendation."
    ),
    "tools": [release_checklist],
    "middleware": [powercontext_middleware],
}


def _build_graph(
    agent_model: BaseChatModel,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    return create_deep_agent(
        model=agent_model,
        tools=[release_checklist],
        system_prompt=(
            "You are a project release assistant. Delegate a release review to the researcher, "
            "including the project name and any relevant recalled constraints in the task. "
            "Then provide a concise actionable plan. Distinguish saved project decisions from "
            "generic suggestions, and state unknowns when no evidence was supplied. "
            "Follow current user instructions over conflicting history. Do not claim to remember "
            "or save new facts: the user saves durable decisions in the Memory panel. "
            "Answer in the language used by the user."
        ),
        subagents=[researcher],
        middleware=[powercontext_middleware],
        checkpointer=checkpointer,
    )


def build_stream_graph(agent_model: BaseChatModel) -> CompiledStateGraph:
    """Build an in-process graph that preserves custom-route thread state."""
    return _build_graph(agent_model, checkpointer=InMemorySaver())


# LangGraph API injects managed persistence into this registered graph.
graph = _build_graph(model)

# The custom FastAPI route invokes its graph directly, so it owns a checkpointer.
stream_graph = build_stream_graph(model)
