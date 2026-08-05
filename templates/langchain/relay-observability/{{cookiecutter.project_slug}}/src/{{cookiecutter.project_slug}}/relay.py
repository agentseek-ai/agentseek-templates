"""NeMo Relay observability bootstrap for the LangChain agent."""

from __future__ import annotations

import atexit
from pathlib import Path
from typing import Any

from .settings import ProjectSettings

_INITIALIZED = False
_EXPORTERS: list[Any] = []


def _observability_config(settings: ProjectSettings) -> Any:
    """Build the verified Relay 0.6.0 observability configuration."""
    from nemo_relay.observability import AtofConfig, AtofFileSinkConfig, ComponentSpec, ObservabilityConfig, OtlpConfig
    from nemo_relay.plugin import PluginConfig

    sinks = None
    if settings.relay_atof_enabled:
        sinks = [
            AtofFileSinkConfig(
                output_directory=str(Path(settings.relay_atof_output_dir)),
                filename=settings.relay_atof_filename,
                mode="append",
            )
        ]
    openinference = None
    if settings.relay_phoenix_enabled:
        openinference = OtlpConfig(
            enabled=True,
            transport="http_binary",
            endpoint=settings.relay_phoenix_endpoint,
            service_name=settings.relay_service_name,
            resource_attributes={
                "openinference.project.name": settings.relay_project_name,
                "deployment.environment": settings.relay_deployment_environment,
            },
        )
    return PluginConfig(
        components=[
            ComponentSpec(
                config=ObservabilityConfig(
                    atof=AtofConfig(enabled=settings.relay_atof_enabled, sinks=sinks),
                    openinference=openinference,
                )
            )
        ]
    )


def configure_relay(settings: ProjectSettings) -> None:
    """Initialize Relay plugins once, using only explicitly enabled sinks."""
    global _INITIALIZED
    if _INITIALIZED or not settings.relay_enabled:
        return

    from nemo_relay.plugin import initialize
    from nemo_relay.utils import run_sync
    config = _observability_config(settings)
    run_sync(initialize(config))
    _INITIALIZED = True
    atexit.register(shutdown_relay)


def relay_middleware(settings: ProjectSettings) -> list[Any]:
    """Return the verified AgentMiddleware only when Relay is enabled."""
    if not settings.relay_enabled:
        return []
    from nemo_relay.integrations.langchain import NemoRelayMiddleware

    return [NemoRelayMiddleware()]


def relay_config_builder(context: Any) -> dict[str, Any]:
    """Build one request-scoped LangChain callback config for messages_spec."""
    from agentseek_langchain.spec import default_runnable_config
    from nemo_relay.integrations.langchain import NemoRelayCallbackHandler

    config = dict(default_runnable_config(context))
    callbacks = list(config.get("callbacks", []))
    callbacks.append(NemoRelayCallbackHandler())
    config["callbacks"] = callbacks
    return config


def shutdown_relay() -> None:
    """Flush Relay subscribers and close active exporters at process exit."""
    if not _INITIALIZED:
        return
    from nemo_relay import subscribers

    subscribers.flush()
    for exporter in _EXPORTERS:
        exporter.shutdown()
