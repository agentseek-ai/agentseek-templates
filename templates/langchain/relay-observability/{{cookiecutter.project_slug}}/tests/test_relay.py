from __future__ import annotations

import sys
from unittest.mock import Mock
from types import SimpleNamespace

import {{ cookiecutter.project_slug }}.relay as relay
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


def test_shutdown_flushes_public_subscribers_api_only(monkeypatch) -> None:
    flush = Mock()
    subscribers = SimpleNamespace(flush=flush)
    old_api = Mock(side_effect=AssertionError("legacy flush_subscribers API was called"))
    fake_nemo_relay = SimpleNamespace(subscribers=subscribers, flush_subscribers=old_api)
    monkeypatch.setitem(sys.modules, "nemo_relay", fake_nemo_relay)
    monkeypatch.setattr(relay, "_INITIALIZED", True)

    relay.shutdown_relay()

    flush.assert_called_once_with()
    old_api.assert_not_called()


def test_shutdown_does_not_import_or_flush_when_uninitialized(monkeypatch) -> None:
    monkeypatch.setattr(relay, "_INITIALIZED", False)
    monkeypatch.delitem(sys.modules, "nemo_relay", raising=False)

    relay.shutdown_relay()
