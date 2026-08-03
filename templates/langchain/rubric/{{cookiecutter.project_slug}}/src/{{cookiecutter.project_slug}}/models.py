from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from langchain_anthropic import ChatAnthropic
from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.runnables import Runnable, RunnableConfig
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
        raise LiveConfigurationError("Unsupported RUBRIC_PROVIDER. Expected openai, anthropic, or google.") from None


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
        raise LiveConfigurationError(f"{variable} provider prefix does not match RUBRIC_PROVIDER.")
    return model_id


def resolve_live_config(environ: Mapping[str, str] | None = None) -> LiveModelConfig:
    """Resolve server-only Live configuration when, and only when, invoked."""
    values = os.environ if environ is None else environ
    api_key = _nonempty(values, "RUBRIC_API_KEY")
    if api_key is None:
        missing = ("RUBRIC_API_KEY",)
        raise LiveConfigurationError(
            "Live Model is not configured. Set server variable: RUBRIC_API_KEY.",
            missing=missing,
        )

    provider = _normalize_provider(_nonempty(values, "RUBRIC_PROVIDER") or DEFAULT_PROVIDER)
    worker_raw = _nonempty(values, "RUBRIC_WORKER_MODEL") or DEFAULT_WORKER_MODEL
    grader_raw = _nonempty(values, "RUBRIC_GRADER_MODEL") or DEFAULT_GRADER_MODEL
    return LiveModelConfig(
        provider=provider,
        api_key=api_key,
        api_base=_nonempty(values, "RUBRIC_API_BASE"),
        worker_model=_resolve_model_id(worker_raw, provider, "RUBRIC_WORKER_MODEL"),
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


def _raise_safe_model_error(role: ModelRole, provider: Provider, exc: Exception) -> None:
    raise SafeModelError(_safe_model_message(role, provider, exc)) from None


class _SanitizingRunnable(Runnable[Any, Any]):
    def __init__(self, delegate: Runnable[Any, Any], *, provider: Provider, role: ModelRole) -> None:
        self._delegate = delegate
        self._provider = provider
        self._role = role

    def invoke(
        self,
        input: Any,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> Any:
        try:
            return self._delegate.invoke(input, config=config, **kwargs)
        except Exception as exc:
            _raise_safe_model_error(self._role, self._provider, exc)

    async def ainvoke(
        self,
        input: Any,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> Any:
        try:
            return await self._delegate.ainvoke(input, config=config, **kwargs)
        except Exception as exc:
            _raise_safe_model_error(self._role, self._provider, exc)

    def stream(
        self,
        input: Any,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> Iterator[Any]:
        try:
            yield from self._delegate.stream(input, config=config, **kwargs)
        except Exception as exc:
            _raise_safe_model_error(self._role, self._provider, exc)

    async def astream(
        self,
        input: Any,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[Any]:
        try:
            async for chunk in self._delegate.astream(input, config=config, **kwargs):
                yield chunk
        except Exception as exc:
            _raise_safe_model_error(self._role, self._provider, exc)


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
            _raise_safe_model_error(self.role, self.provider, exc)

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
            _raise_safe_model_error(self.role, self.provider, exc)

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
            _raise_safe_model_error(self.role, self.provider, exc)
        return _SanitizingRunnable(bound, provider=self.provider, role=self.role)

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
            _raise_safe_model_error(self.role, self.provider, exc)
        return _SanitizingRunnable(bound, provider=self.provider, role=self.role)


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
