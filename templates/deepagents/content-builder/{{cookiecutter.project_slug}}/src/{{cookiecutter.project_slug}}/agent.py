"""DeepAgents content builder graph, served by ``agentseek-api dev``.

This module wires up a ``create_deep_agent`` with brand-voice memory
(``AGENTS.md``), content skills (``skills/``), optional research
(``subagents.yaml``) and image generation tools — mirroring the upstream
``langchain-ai/deepagents/examples/content-builder-agent/content_writer.py``
with provider-first runtime config so the generated app can target OpenAI,
Anthropic, or Gemini from the same ``.env``.
"""

from __future__ import annotations

import os
import warnings
from pathlib import Path

import yaml
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from deepagents.middleware.memory import MemoryMiddleware
from dotenv import load_dotenv
from langchain.agents.middleware import TodoListMiddleware
from langchain.chat_models import init_chat_model

from {{ cookiecutter.project_slug }}.lesson_tools import (
    publish_report,
    read_report,
    read_source,
    save_preference,
    save_report,
)
from {{ cookiecutter.project_slug }}.tools import (
    generate_cover,
    generate_social_image,
    web_search,
)

load_dotenv()

EXAMPLE_DIR = Path(__file__).resolve().parents[2]

SUPPORTED_MODEL_PROVIDERS = {
    "openai": "openai",
    "anthropic": "anthropic",
    "google": "google_genai",
    "google_genai": "google_genai",
    "gemini": "google_genai",
}


def _nonempty_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _normalize_provider(provider: str) -> str:
    normalized = provider.strip().replace("-", "_").lower()
    if normalized in SUPPORTED_MODEL_PROVIDERS:
        return SUPPORTED_MODEL_PROVIDERS[normalized]
    supported = ", ".join(sorted({"openai", "anthropic", "google_genai"}))
    raise ValueError(
        f"Unsupported AGENTSEEK_MODEL_PROVIDER={provider!r}. "
        f"Expected one of: {supported}."
    )


def _split_prefixed_model(model_name: str) -> tuple[str | None, str]:
    if ":" not in model_name:
        return None, model_name
    provider_candidate, bare_model = model_name.split(":", maxsplit=1)
    try:
        normalized_provider = _normalize_provider(provider_candidate)
    except ValueError:
        return None, model_name
    return normalized_provider, bare_model


DEFAULT_MODEL_RAW = (
    _nonempty_env("AGENTSEEK_MODEL")
    or _nonempty_env("DEEPAGENTS_MODEL")
    or _nonempty_env("BUB_MODEL")
    or "{{ cookiecutter.default_model }}".strip()
    or None
)
if not DEFAULT_MODEL_RAW:
    raise ValueError(
        "No model configured. Set AGENTSEEK_MODEL in .env "
        "(e.g. AGENTSEEK_MODEL=gpt-4.1-mini)."
    )
DEFAULT_MODEL_PROVIDER_RAW = os.getenv("AGENTSEEK_MODEL_PROVIDER")
DEFAULT_MODEL_PROVIDER_DEFAULT = "{{ cookiecutter.default_model_provider }}"

prefixed_model_provider, DEFAULT_MODEL = _split_prefixed_model(DEFAULT_MODEL_RAW)
if DEFAULT_MODEL_PROVIDER_RAW:
    MODEL_PROVIDER = _normalize_provider(DEFAULT_MODEL_PROVIDER_RAW)
    if prefixed_model_provider and prefixed_model_provider != MODEL_PROVIDER:
        raise ValueError(
            "AGENTSEEK_MODEL provider prefix does not match AGENTSEEK_MODEL_PROVIDER: "
            f"{DEFAULT_MODEL_RAW!r} vs {DEFAULT_MODEL_PROVIDER_RAW!r}."
        )
else:
    MODEL_PROVIDER = prefixed_model_provider or _normalize_provider(DEFAULT_MODEL_PROVIDER_DEFAULT)

_stream_chunk_timeout_env = os.getenv("LANGCHAIN_OPENAI_STREAM_CHUNK_TIMEOUT_S")
STREAM_CHUNK_TIMEOUT_S: float | None = 300.0
if _stream_chunk_timeout_env not in (None, ""):
    try:
        _parsed_timeout = float(_stream_chunk_timeout_env)
    except ValueError:
        warnings.warn(
            "Ignoring invalid LANGCHAIN_OPENAI_STREAM_CHUNK_TIMEOUT_S value; "
            "using the default 300s timeout instead.",
            stacklevel=2,
        )
    else:
        STREAM_CHUNK_TIMEOUT_S = None if _parsed_timeout <= 0 else _parsed_timeout


SUBAGENT_MODEL_RAW = (
    os.getenv("AGENTSEEK_SUBAGENT_MODEL")
    or os.getenv("DEEPAGENTS_SUBAGENT_MODEL")
    or None
)

# --- Provider kwargs shared by main model and subagents --------------------
# Both use the same provider, API key, and base URL. Only the model name
# differs between them.

PROVIDER_KWARGS: dict[str, object] = {
    "model_provider": MODEL_PROVIDER,
}
if MODEL_PROVIDER == "openai":
    if _nonempty_env("OPENAI_API_KEY"):
        PROVIDER_KWARGS["api_key"] = _nonempty_env("OPENAI_API_KEY")
    if _nonempty_env("OPENAI_API_BASE"):
        PROVIDER_KWARGS["base_url"] = _nonempty_env("OPENAI_API_BASE")
    PROVIDER_KWARGS["stream_chunk_timeout"] = STREAM_CHUNK_TIMEOUT_S
    parallel_tool_calls = _nonempty_env("AGENTSEEK_PARALLEL_TOOL_CALLS")
    if parallel_tool_calls is not None:
        if parallel_tool_calls.lower() not in {"true", "false"}:
            raise ValueError("AGENTSEEK_PARALLEL_TOOL_CALLS must be true or false")
        PROVIDER_KWARGS["model_kwargs"] = {"parallel_tool_calls": parallel_tool_calls.lower() == "true"}
elif MODEL_PROVIDER == "anthropic":
    if _nonempty_env("ANTHROPIC_API_KEY"):
        PROVIDER_KWARGS["api_key"] = _nonempty_env("ANTHROPIC_API_KEY")
    if _nonempty_env("ANTHROPIC_API_URL"):
        PROVIDER_KWARGS["base_url"] = _nonempty_env("ANTHROPIC_API_URL")
elif MODEL_PROVIDER == "google_genai":
    if _nonempty_env("GOOGLE_API_KEY"):
        PROVIDER_KWARGS["api_key"] = _nonempty_env("GOOGLE_API_KEY")
    if _nonempty_env("GOOGLE_API_BASE"):
        PROVIDER_KWARGS["base_url"] = _nonempty_env("GOOGLE_API_BASE")

model = init_chat_model(model=DEFAULT_MODEL, **PROVIDER_KWARGS)


def _make_subagent_model(model_name: str) -> object:
    """Create a subagent LLM sharing the main provider + base URL."""
    _, bare_model = _split_prefixed_model(model_name)
    return init_chat_model(model=bare_model, **PROVIDER_KWARGS)


def _load_subagents(config_path: Path) -> list[dict]:
    """Load subagent definitions from YAML and wire up tools.

    Subagents share the same provider and base URL as the main model.
    The subagent model name can be overridden globally via
    ``AGENTSEEK_SUBAGENT_MODEL`` (or ``DEEPAGENTS_SUBAGENT_MODEL``) env var;
    when set, it takes precedence over the per-subagent ``model`` in YAML.
    """
    available_tools = {
        "web_search": web_search,
    }

    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    subagents = []
    for name, spec in config.items():
        subagent: dict = {
            "name": name,
            "description": spec["description"],
            "system_prompt": spec["system_prompt"],
        }
        model_name = SUBAGENT_MODEL_RAW or spec.get("model")
        if model_name:
            subagent["model"] = _make_subagent_model(model_name)
        if "tools" in spec:
            subagent["tools"] = [available_tools[t] for t in spec["tools"]]
        subagents.append(subagent)

    return subagents


def _enabled(name: str) -> bool:
    value = os.getenv(name, "false").strip().lower()
    if value not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false")
    return value == "true"


def build_graph(chat_model, *, checkpointer=None, approvals: bool = False):
    """Build the app graph; approvals are enabled only in the SDK experiment."""
    mode = os.getenv("CONTENT_MODE", "text").strip().lower()
    if mode not in {"text", "full"}:
        raise ValueError("CONTENT_MODE must be text or full")
    search = mode == "full" and _enabled("CONTENT_ENABLE_SEARCH")
    images = mode == "full" and _enabled("CONTENT_ENABLE_IMAGES")
    if search and not _nonempty_env("TAVILY_API_KEY"):
        raise ValueError("Search enabled but TAVILY_API_KEY is missing")
    if images and not _nonempty_env("GOOGLE_API_KEY"):
        raise ValueError("Images enabled but GOOGLE_API_KEY is missing")
    tools = [read_source, save_report, read_report, save_preference]
    if images:
        tools += [generate_cover, generate_social_image]
    if approvals:
        if checkpointer is None:
            raise ValueError("The SDK approval experiment requires a checkpointer")
        tools += [publish_report]
    backend = FilesystemBackend(root_dir=EXAMPLE_DIR, virtual_mode=True)
    memory_sources = ["/AGENTS.md", "/memory/preferences.md"]
    return create_deep_agent(
        model=chat_model,
        middleware=[
            TodoListMiddleware(),
            MemoryMiddleware(
                backend=backend,
                sources=memory_sources,
                add_cache_control=True,
                system_prompt=(
                    "<agent_memory>\n{agent_memory}\n</agent_memory>\n"
                    "AGENTS.md is fixed project guidance; do not edit it to save preferences. "
                    "Only save preferences with save_preference when the user explicitly asks "
                    "to remember language, tone, or format. Do not infer or save other preferences. "
                    "The returned file contents confirm the write to /memory/preferences.md."
                ),
            ),
        ],
        memory=memory_sources,
        skills=["/skills/"],
        system_prompt=(
            f"Content mode: {mode}. Search enabled: {search}. Images enabled: {images}. "
            "In pure text mode, use local sources and produce text only. "
            "Use write_todos for multistep work. Plan only actual work, never a task to "
            "update or complete the todo list itself. Call write_todos at most once per "
            "response. Wait for each dependent tool's successful result before the next "
            "step; saving, reading back, and marking complete must be separate responses. "
            "Read sources with read_source, save with save_report and verify with "
            "read_report. After successful verification, mark ALL todos completed before "
            "the final answer. If any step fails, keep its todo incomplete. "
            "When using the bundled course notes, label that material as synthetic, "
            "cite the source paths, and keep those claims supported by the notes. "
            "Preserve the provenance of user-provided and researched material; "
            "cite the sources actually used. "
            "Only delegate to researcher when search is enabled. "
            "Generate an image only when images are enabled AND the user requests it. "
            "Save preferences only when the user explicitly asks to remember them."
        ),
        tools=tools,
        subagents=_load_subagents(EXAMPLE_DIR / "subagents.yaml") if search else [],
        backend=backend,
        checkpointer=checkpointer,
        interrupt_on={"publish_report": {"allowed_decisions": ["approve", "reject"]}} if approvals else None,
    )


graph = build_graph(model)
