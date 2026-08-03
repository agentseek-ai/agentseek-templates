from __future__ import annotations

from {{ cookiecutter.project_slug }}.relay import _observability_config, relay_config_builder, relay_middleware
from {{ cookiecutter.project_slug }}.settings import ProjectSettings


def test_relay_disabled_registers_no_middleware() -> None:
    settings = ProjectSettings(RELAY_ENABLED=False)
    assert relay_middleware(settings) == []


def test_relay_config_is_request_scoped() -> None:
    class Context:
        session_id = "session-1"
        workspace = "."

    config = relay_config_builder(Context())
    assert len(config["callbacks"]) == 1
    assert config["callbacks"][0].run_inline is True


def test_atof_only_disables_phoenix_export() -> None:
    config = _observability_config(ProjectSettings(RELAY_PHOENIX_ENABLED=False))
    rendered = config.to_dict()
    observability = rendered["components"][0]["config"]
    assert observability["atof"]["enabled"] is True
    assert observability.get("openinference") is None


def test_phoenix_export_keeps_atof_enabled_by_default() -> None:
    config = _observability_config(ProjectSettings())
    rendered = config.to_dict()["components"][0]["config"]
    assert rendered["atof"]["enabled"] is True
    assert rendered["openinference"]["enabled"] is True
