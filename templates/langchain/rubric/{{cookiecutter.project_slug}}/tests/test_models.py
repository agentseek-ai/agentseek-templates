from __future__ import annotations

import logging
import os
import subprocess
import sys

import pytest
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from pydantic import PrivateAttr
from rubric_lab.models import (
    LiveConfigurationError,
    LiveModelConfig,
    SafeModelError,
    SanitizingChatModel,
    build_live_models,
    resolve_live_config,
)

LIVE_AND_PROVIDER_VARIABLES = (
    "RUBRIC_PROVIDER",
    "RUBRIC_API_KEY",
    "RUBRIC_API_BASE",
    "RUBRIC_WORKER_MODEL",
    "RUBRIC_GRADER_MODEL",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
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
    config = resolve_live_config(
        {
            "RUBRIC_PROVIDER": alias,
            "RUBRIC_API_KEY": "shared-secret",
            "RUBRIC_WORKER_MODEL": f"{alias}:worker-model",
            "RUBRIC_GRADER_MODEL": f"{alias}:grader-model",
        }
    )

    assert config.provider == provider
    assert config.worker_model == "worker-model"
    assert config.grader_model == "grader-model"
    assert config.api_key == "shared-secret"


@pytest.mark.parametrize("model_variable", ["RUBRIC_WORKER_MODEL", "RUBRIC_GRADER_MODEL"])
def test_live_configuration_rejects_provider_prefixed_model_conflicts(
    model_variable: str,
) -> None:
    environ = {
        "RUBRIC_PROVIDER": "openai",
        "RUBRIC_API_KEY": "SENTINEL_SECRET_7f2c",
        "RUBRIC_WORKER_MODEL": "openai:worker-model",
        "RUBRIC_GRADER_MODEL": "openai:grader-model",
    }
    environ[model_variable] = "anthropic:wrong-provider-model"

    with pytest.raises(LiveConfigurationError, match="provider prefix") as error:
        resolve_live_config(environ)

    assert "SENTINEL_SECRET_7f2c" not in str(error.value)


def test_live_configuration_preserves_separate_model_ids_and_one_shared_credential() -> None:
    config = resolve_live_config(
        {
            "RUBRIC_PROVIDER": "openai",
            "RUBRIC_API_KEY": "shared-secret",
            "RUBRIC_API_BASE": "https://models.example.test/v1",
            "RUBRIC_WORKER_MODEL": "openai:worker-model",
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

    assert error.value.missing == ("RUBRIC_API_KEY",)
    assert "sk-" not in str(error.value)
    assert "RUBRIC_API_KEY" in str(error.value)


def test_invalid_live_configuration_does_not_echo_unknown_values() -> None:
    with pytest.raises(LiveConfigurationError) as error:
        resolve_live_config(
            {
                "RUBRIC_PROVIDER": "SENTINEL_SECRET_7f2c",
                "RUBRIC_API_KEY": "sk-SENTINEL_SECRET_7f2c",
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
        **kwargs: object,
    ) -> ChatResult:
        del messages, stop, kwargs
        self._calls += 1
        raise RuntimeError(self.message)


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


def test_bound_and_structured_model_paths_keep_the_sanitizing_boundary() -> None:
    class BindingModel(RaisingChatModel):
        def bind_tools(self, tools: object, **kwargs: object):
            del tools, kwargs
            return self

        def with_structured_output(self, schema: object, **kwargs: object):
            del schema, kwargs
            return self

    model = SanitizingChatModel(
        delegate=BindingModel(message="SENTINEL_SECRET_7f2c"),
        provider="google",
        role="grader",
    )

    for runnable in (model.bind_tools([]), model.with_structured_output(dict)):
        with pytest.raises(SafeModelError) as error:
            runnable.invoke("grade this")
        assert "SENTINEL_SECRET_7f2c" not in str(error.value)


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
