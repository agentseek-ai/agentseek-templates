"""A deliberately observable DeepAgents graph for the streaming template."""

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
MODEL_PROVIDER = _normalize_provider(
    os.getenv("AGENTSEEK_MODEL_PROVIDER", "{{ cookiecutter.default_model_provider }}")
)

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
def inspect_streaming_topic(topic: str) -> str:
    """Return a local reference note so the UI can show a real tool lifecycle."""
    cleaned = topic.strip() or "the requested topic"
    return (
        f"Local reference lookup completed for {cleaned}. "
        "The coordinator should explain the researcher messages, tool calls, "
        "state snapshots, and final output separately."
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

model = init_chat_model(**MODEL_INIT_KWARGS)

researcher = {
    "name": "researcher",
    "description": "Investigate one streaming concept and return a concise explanation.",
    "system_prompt": (
        "You are the researcher sub-agent. Always use inspect_streaming_topic "
        "once, then explain one concrete Event Streaming v3 concept. Return "
        "a concise note for the coordinator."
    ),
    "tools": [inspect_streaming_topic],
}


def _build_graph(
    agent_model: BaseChatModel,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    return create_deep_agent(
        model=agent_model,
        tools=[inspect_streaming_topic],
        system_prompt=(
            "You are a coordinator demonstrating Deep Agents Event Streaming. "
            "For every user request, delegate the explanation to the researcher "
            "sub-agent before answering. Do not answer from memory first. After "
            "the researcher returns, summarize the result and explicitly mention "
            "that the UI can observe messages, tool calls, values, subagents, and output."
        ),
        subagents=[researcher],
        checkpointer=checkpointer,
    )


def build_stream_graph(agent_model: BaseChatModel) -> CompiledStateGraph:
    """Build an in-process graph that preserves custom-route thread state."""
    return _build_graph(agent_model, checkpointer=InMemorySaver())


# LangGraph API injects managed persistence into this registered graph.
graph = _build_graph(model)

# The custom FastAPI route invokes its graph directly, so it owns a checkpointer.
stream_graph = build_stream_graph(model)
