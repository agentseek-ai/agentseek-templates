from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from langchain_anthropic import ChatAnthropic
from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_core.runnables import (
    Runnable,
    RunnableAssign,
    RunnableBinding,
    RunnableParallel,
    RunnableSequence,
    RunnableWithFallbacks,
)
from langchain_core.tools import BaseTool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

Provider = Literal["openai", "anthropic", "google"]
ModelRole = Literal["worker", "grader"]

DEFAULT_PROVIDER = "{{ cookiecutter.default_provider }}"
DEFAULT_WORKER_MODEL = "{{ cookiecutter.worker_model }}"
DEFAULT_GRADER_MODEL = "{{ cookiecutter.grader_model }}"

_PROVIDER_ALIASES: dict[str, Provider] = {
    "openai": "openai",
    "anthropic": "anthropic",
    "google": "google",
    "google_genai": "google",
    "gemini": "google",
}
_PROVIDER_ENVIRONMENT: dict[Provider, tuple[str, str]] = {
    "openai": ("OPENAI_API_KEY", "OPENAI_API_BASE"),
    "anthropic": ("ANTHROPIC_API_KEY", "ANTHROPIC_API_URL"),
    "google": ("GOOGLE_API_KEY", "GOOGLE_API_BASE"),
}
_SAFE_ERROR_TYPES = frozenset(
    {
        "APIConnectionError",
        "APIStatusError",
        "AnthropicError",
        "AuthenticationError",
        "BadRequestError",
        "ConnectionError",
        "GoogleAPIError",
        "NotImplementedError",
        "PermissionDeniedError",
        "RateLimitError",
        "RuntimeError",
        "TimeoutError",
        "TypeError",
        "ValidationError",
        "ValueError",
    }
)


class LiveConfigurationError(ValueError):
    """A bounded, credential-free Live Model setup error."""

    def __init__(self, message: str, *, missing: Sequence[str] = ()) -> None:
        super().__init__(message)
        self.missing = tuple(missing)


class SafeModelError(RuntimeError):
    """A provider failure safe to place at the application boundary."""


@dataclass(frozen=True, slots=True)
class LiveModelConfig:
    provider: Provider
    api_key: str
    api_base: str | None
    worker_model: str
    grader_model: str


@dataclass(frozen=True, slots=True)
class ModelPair:
    worker: BaseChatModel
    grader: BaseChatModel


def _nonempty(environ: Mapping[str, str], name: str) -> str | None:
    value = environ.get(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _normalize_provider(value: str) -> Provider:
    alias = value.strip().replace("-", "_").lower()
    try:
        return _PROVIDER_ALIASES[alias]
    except KeyError:
        raise LiveConfigurationError(
            "Unsupported AGENTSEEK_MODEL_PROVIDER. Expected openai, anthropic, or google."
        ) from None


def _split_model_provider(model_id: str) -> tuple[Provider | None, str]:
    if ":" not in model_id:
        return None, model_id
    prefix, bare_model = model_id.split(":", maxsplit=1)
    try:
        provider = _normalize_provider(prefix)
    except LiveConfigurationError:
        return None, model_id
    if not bare_model.strip():
        raise LiveConfigurationError("Live Model IDs must not be empty.")
    return provider, bare_model.strip()


def _resolve_model_id(raw_model: str, provider: Provider, variable: str) -> str:
    prefixed_provider, model_id = _split_model_provider(raw_model)
    if prefixed_provider is not None and prefixed_provider != provider:
        raise LiveConfigurationError(f"{variable} provider prefix does not match AGENTSEEK_MODEL_PROVIDER.")
    return model_id


def resolve_live_config(environ: Mapping[str, str] | None = None) -> LiveModelConfig:
    """Resolve server-only Live configuration when, and only when, invoked."""
    values = os.environ if environ is None else environ
    provider = _normalize_provider(_nonempty(values, "AGENTSEEK_MODEL_PROVIDER") or DEFAULT_PROVIDER)
    api_key_name, api_base_name = _PROVIDER_ENVIRONMENT[provider]
    api_key = _nonempty(values, api_key_name)
    if api_key is None:
        missing = (api_key_name,)
        raise LiveConfigurationError(
            f"Live Model is not configured. Set server variable: {api_key_name}.",
            missing=missing,
        )

    worker_raw = _nonempty(values, "AGENTSEEK_MODEL") or DEFAULT_WORKER_MODEL
    grader_raw = _nonempty(values, "RUBRIC_GRADER_MODEL") or DEFAULT_GRADER_MODEL
    return LiveModelConfig(
        provider=provider,
        api_key=api_key,
        api_base=_nonempty(values, api_base_name),
        worker_model=_resolve_model_id(worker_raw, provider, "AGENTSEEK_MODEL"),
        grader_model=_resolve_model_id(grader_raw, provider, "RUBRIC_GRADER_MODEL"),
    )


def _safe_error_type(exc: Exception) -> str:
    error_type = type(exc).__name__
    return error_type if error_type in _SAFE_ERROR_TYPES else "ProviderError"


def _safe_model_message(role: ModelRole, provider: Provider, exc: Exception) -> str:
    error_type = _safe_error_type(exc)
    return (
        f"{role.title()} model call failed safely "
        f"(provider={provider}, error_type={error_type}). "
        "Check the Live Model server configuration and provider compatibility."
    )


def _safe_model_error(role: ModelRole, provider: Provider, exc: Exception) -> SafeModelError:
    return SafeModelError(_safe_model_message(role, provider, exc))


def _replace_model_binding(
    runnable: Runnable[Any, Any],
    *,
    delegate: BaseChatModel,
    replacement: BaseChatModel,
) -> tuple[Runnable[Any, Any], bool]:
    """Copy a provider-built runnable graph with its model leaf made safe."""
    memo: dict[int, Runnable[Any, Any]] = {}
    active: set[int] = set()
    replacements = 0

    def visit(node: Runnable[Any, Any]) -> Runnable[Any, Any]:
        nonlocal replacements
        node_id = id(node)
        if node_id in memo:
            return memo[node_id]
        if node_id in active:
            raise TypeError("Cyclic provider binding graph")
        if node is delegate:
            raise TypeError("Unbound provider model in runnable graph")

        active.add(node_id)
        try:
            updated: Runnable[Any, Any] = node
            if isinstance(node, RunnableBinding):
                if node.bound is delegate:
                    replacements += 1
                    updated = node.model_copy(update={"bound": replacement})
                else:
                    bound = visit(node.bound)
                    if bound is not node.bound:
                        updated = node.model_copy(update={"bound": bound})
            elif isinstance(node, RunnableSequence):
                first = visit(node.first)
                middle = [visit(step) for step in node.middle]
                last = visit(node.last)
                if (
                    first is not node.first
                    or last is not node.last
                    or any(new is not old for new, old in zip(middle, node.middle, strict=True))
                ):
                    updated = node.model_copy(update={"first": first, "middle": middle, "last": last})
            elif isinstance(node, RunnableParallel):
                steps = {key: visit(step) for key, step in node.steps__.items()}
                if any(steps[key] is not step for key, step in node.steps__.items()):
                    updated = node.model_copy(update={"steps__": steps})
            elif isinstance(node, RunnableWithFallbacks):
                primary = visit(node.runnable)
                fallbacks = [visit(fallback) for fallback in node.fallbacks]
                if primary is not node.runnable or any(
                    new is not old for new, old in zip(fallbacks, node.fallbacks, strict=True)
                ):
                    updated = node.model_copy(update={"runnable": primary, "fallbacks": fallbacks})
            elif isinstance(node, RunnableAssign):
                mapper = visit(node.mapper)
                if mapper is not node.mapper:
                    updated = node.model_copy(update={"mapper": mapper})
            memo[node_id] = updated
            return updated
        finally:
            active.remove(node_id)

    rebound = visit(runnable)
    try:
        contains_raw_delegate = any(graph_node.data is delegate for graph_node in rebound.get_graph().nodes.values())
    except Exception as exc:
        raise TypeError("Unable to verify provider binding graph") from exc
    if contains_raw_delegate:
        raise TypeError("Raw provider remained in runnable graph")
    return rebound, replacements > 0


class SanitizingChatModel(BaseChatModel):
    """A transparent provider proxy that never forwards raw exception text."""

    delegate: BaseChatModel
    provider: Provider
    role: ModelRole

    @property
    def _llm_type(self) -> str:
        return f"sanitized-{self.provider}-{self.role}"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {"provider": self.provider, "role": self.role}

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        try:
            return self.delegate._generate(
                messages,
                stop=stop,
                run_manager=run_manager,
                **kwargs,
            )
        except Exception as exc:
            safe_error = _safe_model_error(self.role, self.provider, exc)
        raise safe_error

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        try:
            return await self.delegate._agenerate(
                messages,
                stop=stop,
                run_manager=run_manager,
                **kwargs,
            )
        except Exception as exc:
            safe_error = _safe_model_error(self.role, self.provider, exc)
        raise safe_error

    def _should_stream(
        self,
        *,
        async_api: bool,
        run_manager: CallbackManagerForLLMRun | AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> bool:
        return self.delegate._should_stream(  # noqa: SLF001
            async_api=async_api,
            run_manager=run_manager,
            **kwargs,
        )

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        try:
            yield from self.delegate._stream(  # noqa: SLF001
                messages,
                stop=stop,
                run_manager=run_manager,
                **kwargs,
            )
        except Exception as exc:
            safe_error = _safe_model_error(self.role, self.provider, exc)
        else:
            return
        raise safe_error

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        try:
            async for chunk in self.delegate._astream(  # noqa: SLF001
                messages,
                stop=stop,
                run_manager=run_manager,
                **kwargs,
            ):
                yield chunk
        except Exception as exc:
            safe_error = _safe_model_error(self.role, self.provider, exc)
        else:
            return
        raise safe_error

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Any | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        try:
            bound = self.delegate.bind_tools(tools, tool_choice=tool_choice, **kwargs)
        except Exception as exc:
            safe_error = _safe_model_error(self.role, self.provider, exc)
        else:
            try:
                rebound, replaced = _replace_model_binding(
                    bound,
                    delegate=self.delegate,
                    replacement=self,
                )
            except Exception as exc:
                safe_error = _safe_model_error(self.role, self.provider, exc)
            else:
                if replaced:
                    return rebound
                safe_error = _safe_model_error(
                    self.role,
                    self.provider,
                    TypeError("Unsupported provider tool binding"),
                )
        raise safe_error

    def with_structured_output(
        self,
        schema: dict[str, Any] | type,
        *,
        include_raw: bool = False,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, dict[str, Any] | Any]:
        try:
            bound = self.delegate.with_structured_output(
                schema,
                include_raw=include_raw,
                **kwargs,
            )
        except Exception as exc:
            safe_error = _safe_model_error(self.role, self.provider, exc)
        else:
            try:
                rebound, replaced = _replace_model_binding(
                    bound,
                    delegate=self.delegate,
                    replacement=self,
                )
            except Exception as exc:
                safe_error = _safe_model_error(self.role, self.provider, exc)
            else:
                if replaced:
                    return rebound
                safe_error = _safe_model_error(
                    self.role,
                    self.provider,
                    TypeError("Unsupported provider structured-output binding"),
                )
        raise safe_error


def _build_provider_model(config: LiveModelConfig, model_id: str) -> BaseChatModel:
    kwargs: dict[str, object] = {
        "model": model_id,
        "api_key": config.api_key,
    }
    if config.api_base is not None:
        if config.provider == "google":
            kwargs["client_options"] = {"api_endpoint": config.api_base}
        else:
            kwargs["base_url"] = config.api_base

    constructor: type[BaseChatModel]
    if config.provider == "openai":
        constructor = ChatOpenAI
    elif config.provider == "anthropic":
        constructor = ChatAnthropic
    else:
        constructor = ChatGoogleGenerativeAI
    try:
        return constructor(**kwargs)
    except Exception as exc:
        raise LiveConfigurationError(
            f"Unable to initialize {config.provider} Live models "
            f"(error_type={_safe_error_type(exc)}). Check server configuration."
        ) from None


def build_live_models(config: LiveModelConfig) -> ModelPair:
    worker = _build_provider_model(config, config.worker_model)
    grader = _build_provider_model(config, config.grader_model)
    return ModelPair(
        worker=SanitizingChatModel(delegate=worker, provider=config.provider, role="worker"),
        grader=SanitizingChatModel(delegate=grader, provider=config.provider, role="grader"),
    )
