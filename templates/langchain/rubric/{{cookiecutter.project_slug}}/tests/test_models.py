from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any

import pytest
from langchain_anthropic import ChatAnthropic
from langchain_core.callbacks import AsyncCallbackHandler, BaseCallbackHandler
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import Runnable, RunnableBinding, RunnableParallel, RunnableSequence
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, PrivateAttr
from rubric_lab.models import (
    LiveConfigurationError,
    LiveModelConfig,
    SafeModelError,
    SanitizingChatModel,
    build_live_models,
    resolve_live_config,
)

LIVE_AND_PROVIDER_VARIABLES = (
    "AGENTSEEK_MODEL_PROVIDER",
    "AGENTSEEK_MODEL",
    "RUBRIC_GRADER_MODEL",
    "OPENAI_API_KEY",
    "OPENAI_API_BASE",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_API_URL",
    "GOOGLE_API_KEY",
    "GOOGLE_API_BASE",
)


def test_models_and_graphs_import_without_provider_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in LIVE_AND_PROVIDER_VARIABLES:
        monkeypatch.delenv(variable, raising=False)

    environ = os.environ.copy()
    for variable in LIVE_AND_PROVIDER_VARIABLES:
        environ.pop(variable, None)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from rubric_lab import graphs, models; "
                "assert models.LiveModelConfig; "
                "assert graphs.make_demo_graph; "
                "assert graphs.make_live_graph"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environ,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("alias", "provider"),
    [
        ("openai", "openai"),
        ("OpenAI", "openai"),
        ("anthropic", "anthropic"),
        ("Anthropic", "anthropic"),
        ("google", "google"),
        ("google_genai", "google"),
        ("google-genai", "google"),
        ("gemini", "google"),
    ],
)
def test_live_configuration_normalizes_supported_provider_aliases(alias: str, provider: str) -> None:
    key_name = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "google": "GOOGLE_API_KEY",
    }[provider]
    config = resolve_live_config(
        {
            "AGENTSEEK_MODEL_PROVIDER": alias,
            key_name: "shared-secret",
            "AGENTSEEK_MODEL": f"{alias}:worker-model",
            "RUBRIC_GRADER_MODEL": f"{alias}:grader-model",
        }
    )

    assert config.provider == provider
    assert config.worker_model == "worker-model"
    assert config.grader_model == "grader-model"
    assert config.api_key == "shared-secret"


@pytest.mark.parametrize("model_variable", ["AGENTSEEK_MODEL", "RUBRIC_GRADER_MODEL"])
def test_live_configuration_rejects_provider_prefixed_model_conflicts(
    model_variable: str,
) -> None:
    environ = {
        "AGENTSEEK_MODEL_PROVIDER": "openai",
        "OPENAI_API_KEY": "SENTINEL_SECRET_7f2c",
        "AGENTSEEK_MODEL": "openai:worker-model",
        "RUBRIC_GRADER_MODEL": "openai:grader-model",
    }
    environ[model_variable] = "anthropic:wrong-provider-model"

    with pytest.raises(LiveConfigurationError, match="provider prefix") as error:
        resolve_live_config(environ)

    assert "SENTINEL_SECRET_7f2c" not in str(error.value)


@pytest.mark.parametrize(
    ("provider", "key_name", "base_name"),
    [
        ("openai", "OPENAI_API_KEY", "OPENAI_API_BASE"),
        ("anthropic", "ANTHROPIC_API_KEY", "ANTHROPIC_API_URL"),
        ("google", "GOOGLE_API_KEY", "GOOGLE_API_BASE"),
    ],
)
def test_live_configuration_reads_only_the_selected_provider_native_key_and_base(
    provider: str,
    key_name: str,
    base_name: str,
) -> None:
    environ = {
        "AGENTSEEK_MODEL_PROVIDER": provider,
        "AGENTSEEK_MODEL": "worker-model",
        "RUBRIC_GRADER_MODEL": "grader-model",
        "OPENAI_API_KEY": "not-the-selected-key",
        "OPENAI_API_BASE": "https://not-openai.example.test/v1",
        "ANTHROPIC_API_KEY": "not-the-selected-key",
        "ANTHROPIC_API_URL": "https://not-anthropic.example.test/v1",
        "GOOGLE_API_KEY": "not-the-selected-key",
        "GOOGLE_API_BASE": "https://not-google.example.test/v1",
        key_name: f"{provider}-selected-key",
        base_name: f"https://{provider}.example.test/v1",
    }

    config = resolve_live_config(environ)

    assert config == LiveModelConfig(
        provider=provider,  # type: ignore[arg-type]
        api_key=f"{provider}-selected-key",
        api_base=f"https://{provider}.example.test/v1",
        worker_model="worker-model",
        grader_model="grader-model",
    )


def test_live_configuration_preserves_separate_model_ids_and_one_shared_credential() -> None:
    config = resolve_live_config(
        {
            "AGENTSEEK_MODEL_PROVIDER": "openai",
            "OPENAI_API_KEY": "shared-secret",
            "OPENAI_API_BASE": "https://models.example.test/v1",
            "AGENTSEEK_MODEL": "openai:worker-model",
            "RUBRIC_GRADER_MODEL": "openai:grader-model",
        }
    )

    assert config == LiveModelConfig(
        provider="openai",
        api_key="shared-secret",
        api_base="https://models.example.test/v1",
        worker_model="worker-model",
        grader_model="grader-model",
    )


def test_missing_live_configuration_lists_server_variables() -> None:
    with pytest.raises(LiveConfigurationError) as error:
        resolve_live_config({})

    assert error.value.missing == ("OPENAI_API_KEY",)
    assert "sk-" not in str(error.value)
    assert "OPENAI_API_KEY" in str(error.value)


def test_invalid_live_configuration_does_not_echo_unknown_values() -> None:
    with pytest.raises(LiveConfigurationError) as error:
        resolve_live_config(
            {
                "AGENTSEEK_MODEL_PROVIDER": "SENTINEL_SECRET_7f2c",
                "OPENAI_API_KEY": "sk-SENTINEL_SECRET_7f2c",
            }
        )

    assert "SENTINEL_SECRET_7f2c" not in str(error.value)


@pytest.mark.parametrize(
    ("provider", "model_type", "key_field", "base_field"),
    [
        ("openai", ChatOpenAI, "openai_api_key", "openai_api_base"),
        ("anthropic", ChatAnthropic, "anthropic_api_key", "anthropic_api_url"),
        (
            "google",
            ChatGoogleGenerativeAI,
            "google_api_key",
            "base_url",
        ),
    ],
)
def test_live_model_builder_uses_one_credential_and_separate_model_ids(
    provider: str,
    model_type: type[BaseChatModel],
    key_field: str,
    base_field: str,
) -> None:
    config = LiveModelConfig(
        provider=provider,  # type: ignore[arg-type]
        api_key="one-shared-key",
        api_base="https://models.example.test/v1",
        worker_model="worker-id",
        grader_model="grader-id",
    )

    pair = build_live_models(config)

    assert isinstance(pair.worker, SanitizingChatModel)
    assert isinstance(pair.grader, SanitizingChatModel)
    for role, expected_model in ((pair.worker, "worker-id"), (pair.grader, "grader-id")):
        delegate = role.delegate  # type: ignore[attr-defined]
        assert isinstance(delegate, model_type)
        assert delegate.model == expected_model  # type: ignore[attr-defined]
        assert getattr(delegate, key_field).get_secret_value() == "one-shared-key"
        expected_base: object = "https://models.example.test/v1"
        if provider == "google":
            expected_base = {"api_endpoint": expected_base}
        assert delegate.model_dump()[base_field] == expected_base


def test_live_model_constructor_errors_hide_even_hostile_exception_class_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hostile_error = type("SENTINEL_SECRET_7f2c", (RuntimeError,), {})

    def fail_constructor(**_: object) -> None:
        raise hostile_error()

    monkeypatch.setattr("rubric_lab.models.ChatOpenAI", fail_constructor)
    config = LiveModelConfig(
        provider="openai",
        api_key="sk-SENTINEL_SECRET_7f2c",
        api_base=None,
        worker_model="worker-id",
        grader_model="grader-id",
    )

    with pytest.raises(LiveConfigurationError) as error:
        build_live_models(config)

    assert "SENTINEL_SECRET_7f2c" not in str(error.value)


def test_live_graph_factory_and_schema_inspection_do_not_construct_provider_clients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from rubric_lab import graphs

    def fail_constructor(**_: object) -> None:
        raise AssertionError("provider constructor called during graph inspection")

    monkeypatch.setattr("rubric_lab.models.ChatOpenAI", fail_constructor)
    monkeypatch.setattr("rubric_lab.models.ChatAnthropic", fail_constructor)
    monkeypatch.setattr("rubric_lab.models.ChatGoogleGenerativeAI", fail_constructor)

    graph = graphs.make_live_graph()

    assert graph.get_graph().nodes
    assert graph.get_input_jsonschema()["type"] == "object"


class RaisingChatModel(BaseChatModel):
    message: str
    _calls: int = PrivateAttr(default=0)

    @property
    def _llm_type(self) -> str:
        return "raising-test-model"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: object | None = None,
        **kwargs: object,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        self._calls += 1
        raise RuntimeError(self.message)


RawProviderError = type(
    "RawProviderError_SENTINEL_SECRET_7f2c",
    (RuntimeError,),
    {},
)


class GradePayload(BaseModel):
    verdict: str


class ProviderBindingModel(RaisingChatModel):
    """A provider-like model using LangChain's real tool-binding machinery."""

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: object,
    ):
        formatted_tools = [convert_to_openai_tool(tool) for tool in tools]
        return self.bind(tools=formatted_tools, tool_choice=tool_choice, **kwargs)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: object | None = None,
        **kwargs: object,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        self._calls += 1
        error = RawProviderError("provider body=raw-body-marker authorization=Bearer SENTINEL_SECRET_7f2c")
        error.headers = {"authorization": "Bearer SENTINEL_SECRET_7f2c"}
        error.body = {"detail": "raw-body-marker SENTINEL_SECRET_7f2c"}
        raise error


class WorkingProviderBindingModel(ProviderBindingModel):
    _seen_tools: list[object] = PrivateAttr(default_factory=list)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: object | None = None,
        **kwargs: object,
    ) -> ChatResult:
        del messages, stop, run_manager
        self._seen_tools.append(kwargs.get("tools"))
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "GradePayload",
                                "args": {"verdict": "satisfied"},
                                "id": "grade-call",
                                "type": "tool_call",
                            }
                        ],
                    )
                )
            ]
        )


class StreamingProviderBindingModel(WorkingProviderBindingModel):
    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: object | None = None,
        **kwargs: object,
    ) -> Iterator[ChatGenerationChunk]:
        del messages, stop, run_manager, kwargs
        yield ChatGenerationChunk(message=AIMessageChunk(content="sync-stream"))

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: object | None = None,
        **kwargs: object,
    ) -> AsyncIterator[ChatGenerationChunk]:
        del messages, stop, run_manager, kwargs
        yield ChatGenerationChunk(message=AIMessageChunk(content="async-stream"))


class BlockingProviderBindingModel(ProviderBindingModel):
    _started: asyncio.Event = PrivateAttr(default_factory=asyncio.Event)
    _finished: asyncio.Event = PrivateAttr(default_factory=asyncio.Event)

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: object | None = None,
        **kwargs: object,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        self._started.set()
        try:
            await asyncio.Event().wait()
        finally:
            self._finished.set()


def _error_trace_projection(error: BaseException) -> str:
    """Approximate the exception material a callback-backed trace can inspect."""
    projection: list[dict[str, Any]] = []
    current: BaseException | None = error
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        projection.append(
            {
                "type": type(current).__name__,
                "message": str(current),
                "attributes": vars(current),
            }
        )
        current = current.__cause__ or current.__context__
    return repr(projection)


class RecordingTraceHandler(BaseCallbackHandler):
    def __init__(self) -> None:
        self.llm_errors: list[BaseException] = []
        self.chain_errors: list[BaseException] = []

    def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        del kwargs
        self.llm_errors.append(error)

    def on_chain_error(self, error: BaseException, **kwargs: Any) -> None:
        del kwargs
        self.chain_errors.append(error)


class AsyncRecordingTraceHandler(AsyncCallbackHandler):
    def __init__(self) -> None:
        self.llm_errors: list[BaseException] = []
        self.chain_errors: list[BaseException] = []

    async def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        del kwargs
        self.llm_errors.append(error)

    async def on_chain_error(self, error: BaseException, **kwargs: Any) -> None:
        del kwargs
        self.chain_errors.append(error)


def _assert_provider_failure_is_sanitized_everywhere(
    public_error: BaseException,
    callback_errors: list[BaseException],
    logs: str,
) -> None:
    assert callback_errors, "the sanitized model failure must remain observable"
    assert isinstance(public_error, SafeModelError)
    assert all(isinstance(error, SafeModelError) for error in callback_errors)

    observed = "\n".join(
        [_error_trace_projection(public_error), *map(_error_trace_projection, callback_errors), logs]
    ).lower()
    for forbidden in (
        "sentinel_secret_7f2c",
        "raw-body-marker",
        "authorization",
        RawProviderError.__name__.lower(),
    ):
        assert forbidden not in observed


def _model_bindings(runnable: Runnable[Any, Any]) -> list[RunnableBinding[Any, Any]]:
    if isinstance(runnable, RunnableBinding):
        if isinstance(runnable.bound, BaseChatModel):
            return [runnable]
        return []
    if isinstance(runnable, RunnableSequence):
        bindings = _model_bindings(runnable.first)
        for step in runnable.middle:
            bindings.extend(_model_bindings(step))
        bindings.extend(_model_bindings(runnable.last))
        return bindings
    if isinstance(runnable, RunnableParallel):
        return [binding for step in runnable.steps__.values() for binding in _model_bindings(step)]
    return []


def test_sanitizing_model_hides_provider_exception_from_public_error_and_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    model = SanitizingChatModel(
        delegate=RaisingChatModel(message="SENTINEL_SECRET_7f2c"),
        provider="openai",
        role="grader",
    )

    with caplog.at_level(logging.ERROR), pytest.raises(SafeModelError) as error:
        model.invoke("grade this")

    assert str(error.value) == (
        "Grader model call failed safely (provider=openai, error_type=RuntimeError). "
        "Check the Live Model server configuration and provider compatibility."
    )
    assert "SENTINEL_SECRET_7f2c" not in str(error.value)
    assert "SENTINEL_SECRET_7f2c" not in caplog.text


@pytest.mark.asyncio
async def test_sanitizing_model_preserves_async_invocation_and_sanitizes_errors() -> None:
    model = SanitizingChatModel(
        delegate=RaisingChatModel(message="SENTINEL_SECRET_7f2c"),
        provider="anthropic",
        role="worker",
    )

    with pytest.raises(SafeModelError, match="Worker model call failed safely") as error:
        await model.ainvoke("write code")

    assert "SENTINEL_SECRET_7f2c" not in str(error.value)


def test_bound_tools_callback_observes_only_the_sanitized_sync_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    observer = RecordingTraceHandler()
    model = SanitizingChatModel(
        delegate=ProviderBindingModel(message="unused"),
        provider="google",
        role="grader",
    )

    with caplog.at_level(logging.ERROR), pytest.raises(SafeModelError) as error:
        model.bind_tools([GradePayload]).invoke(
            "grade this",
            config={"callbacks": [observer]},
        )

    assert len(observer.llm_errors) == 1
    _assert_provider_failure_is_sanitized_everywhere(
        error.value,
        [*observer.llm_errors, *observer.chain_errors],
        caplog.text,
    )


@pytest.mark.asyncio
async def test_structured_output_trace_observes_only_the_sanitized_async_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    observer = AsyncRecordingTraceHandler()
    model = SanitizingChatModel(
        delegate=ProviderBindingModel(message="unused"),
        provider="anthropic",
        role="grader",
    )

    with caplog.at_level(logging.ERROR), pytest.raises(SafeModelError) as error:
        await model.with_structured_output(GradePayload).ainvoke(
            "grade this",
            config={"callbacks": [observer]},
        )

    assert len(observer.llm_errors) == 1
    _assert_provider_failure_is_sanitized_everywhere(
        error.value,
        [*observer.llm_errors, *observer.chain_errors],
        caplog.text,
    )


@pytest.mark.parametrize("provider", ["openai", "anthropic", "google"])
def test_supported_provider_tool_bindings_keep_formatted_schemas_inside_safe_model(
    provider: str,
) -> None:
    model = build_live_models(
        LiveModelConfig(
            provider=provider,  # type: ignore[arg-type]
            api_key="test-key",
            api_base=None,
            worker_model="worker-model",
            grader_model="grader-model",
        )
    ).grader
    assert isinstance(model, SanitizingChatModel)

    raw = model.delegate.bind_tools([GradePayload])
    safe = model.bind_tools([GradePayload])

    assert isinstance(raw, RunnableBinding)
    assert isinstance(safe, RunnableBinding)
    assert type(safe) is type(raw)
    assert safe.bound is model
    assert safe.kwargs == raw.kwargs
    assert safe.config == raw.config
    assert safe.config_factories == raw.config_factories
    assert safe.custom_input_type is raw.custom_input_type
    assert safe.custom_output_type is raw.custom_output_type
    assert all(node.data is not model.delegate for node in safe.get_graph().nodes.values())


@pytest.mark.parametrize(
    ("provider", "structured_kwargs"),
    [
        ("openai", {}),
        ("openai", {"method": "function_calling", "strict": True}),
        ("anthropic", {}),
        ("anthropic", {"method": "json_schema"}),
        ("google", {}),
        ("google", {"method": "function_calling"}),
    ],
)
@pytest.mark.parametrize("include_raw", [False, True])
def test_supported_provider_structured_output_keeps_native_runnable_graph(
    provider: str,
    structured_kwargs: dict[str, object],
    include_raw: bool,
) -> None:
    model = build_live_models(
        LiveModelConfig(
            provider=provider,  # type: ignore[arg-type]
            api_key="test-key",
            api_base=None,
            worker_model="worker-model",
            grader_model="grader-model",
        )
    ).grader
    assert isinstance(model, SanitizingChatModel)

    raw = model.delegate.with_structured_output(
        GradePayload,
        include_raw=include_raw,
        **structured_kwargs,
    )
    safe = model.with_structured_output(
        GradePayload,
        include_raw=include_raw,
        **structured_kwargs,
    )
    raw_bindings = _model_bindings(raw)
    safe_bindings = _model_bindings(safe)

    assert type(safe) is type(raw)
    assert len(raw_bindings) == len(safe_bindings) == 1
    assert type(safe_bindings[0]) is type(raw_bindings[0])
    assert safe_bindings[0].bound is model
    assert safe_bindings[0].kwargs == raw_bindings[0].kwargs
    assert safe_bindings[0].config == raw_bindings[0].config
    assert safe_bindings[0].config_factories == raw_bindings[0].config_factories
    assert safe_bindings[0].custom_input_type is raw_bindings[0].custom_input_type
    assert safe_bindings[0].custom_output_type is raw_bindings[0].custom_output_type
    assert all(node.data is not model.delegate for node in safe.get_graph().nodes.values())
    if isinstance(raw, RunnableSequence) and isinstance(safe, RunnableSequence):
        assert type(safe.last) is type(raw.last)


def test_structured_output_success_preserves_provider_tool_schema_and_parser() -> None:
    delegate = WorkingProviderBindingModel(message="unused")
    model = SanitizingChatModel(delegate=delegate, provider="openai", role="grader")

    result = model.with_structured_output(GradePayload).invoke("grade this")

    assert result == GradePayload(verdict="satisfied")
    assert isinstance(delegate._seen_tools[0], list)
    assert delegate._seen_tools[0][0]["function"]["name"] == "GradePayload"  # type: ignore[index]


@pytest.mark.asyncio
async def test_bound_tools_preserves_sync_and_async_provider_streaming() -> None:
    model = SanitizingChatModel(
        delegate=StreamingProviderBindingModel(message="unused"),
        provider="google",
        role="worker",
    )
    bound = model.bind_tools([GradePayload])

    sync_content = "".join(str(chunk.content) for chunk in bound.stream("write code"))
    async_content = "".join([str(chunk.content) async for chunk in bound.astream("write code")])

    assert sync_content == "sync-stream"
    assert async_content == "async-stream"


@pytest.mark.asyncio
async def test_structured_output_does_not_convert_cancellation_into_model_failure() -> None:
    delegate = BlockingProviderBindingModel(message="unused")
    model = SanitizingChatModel(
        delegate=delegate,
        provider="anthropic",
        role="grader",
    )
    task = asyncio.create_task(model.with_structured_output(GradePayload).ainvoke("grade this"))

    await asyncio.wait_for(delegate._started.wait(), timeout=1)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert delegate._finished.is_set()


def test_successful_model_result_is_not_changed_by_the_sanitizing_boundary() -> None:
    class WorkingChatModel(RaisingChatModel):
        def _generate(
            self,
            messages: list[BaseMessage],
            stop: list[str] | None = None,
            **kwargs: object,
        ) -> ChatResult:
            del messages, stop, kwargs
            return ChatResult(generations=[ChatGeneration(message=AIMessage("safe result"))])

    model = SanitizingChatModel(
        delegate=WorkingChatModel(message="unused"),
        provider="openai",
        role="worker",
    )

    assert model.invoke("write code").content == "safe result"
