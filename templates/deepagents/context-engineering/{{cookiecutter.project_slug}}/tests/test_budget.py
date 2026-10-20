from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from {{ cookiecutter.project_slug }} import agent
from {{ cookiecutter.project_slug }}.context import CONTEXT_POLICY, Settings
from {{ cookiecutter.project_slug }}.server import create_app


@pytest.mark.parametrize("value", [None, "", "  "])
def test_unconfigured_output_budget_keeps_existing_model_default(value):
    env = {} if value is None else {"CONTEXT_LAB_MAX_OUTPUT_TOKENS": value}
    settings = Settings.from_env(env)
    assert settings.max_output_tokens == 3000
    assert settings.context_policy["max_output_tokens"] == 3000


@pytest.mark.parametrize(("value", "expected"), [("128", 128), (" 6000 ", 6000), ("32768", 32768)])
def test_output_budget_is_parsed_and_exposed_in_effective_policy(value, expected):
    settings = Settings.from_env({"CONTEXT_LAB_MAX_OUTPUT_TOKENS": value})
    assert settings.max_output_tokens == expected
    assert settings.context_policy["max_output_tokens"] == expected


@pytest.mark.parametrize("value", ["0", "127", "32769", "-5", "3.5", "true", "unlimited"])
def test_invalid_output_budget_is_rejected_before_model_access(value):
    with pytest.raises(ValueError, match="CONTEXT_LAB_MAX_OUTPUT_TOKENS"):
        Settings.from_env({"CONTEXT_LAB_MAX_OUTPUT_TOKENS": value})


@pytest.mark.parametrize(("name", "field", "default"), [
    ("CONTEXT_LAB_RECURSION_LIMIT", "recursion_limit", 32),
    ("CONTEXT_LAB_RUN_TIMEOUT_SECONDS", "run_timeout_seconds", 180),
])
@pytest.mark.parametrize("value", [None, "", "  "])
def test_unconfigured_run_limits_keep_existing_defaults(name, field, default, value):
    settings = Settings.from_env({} if value is None else {name: value})
    assert getattr(settings, field) == default
    assert settings.context_policy[field] == default


@pytest.mark.parametrize(("name", "field", "value", "expected"), [
    ("CONTEXT_LAB_RECURSION_LIMIT", "recursion_limit", "8", 8),
    ("CONTEXT_LAB_RECURSION_LIMIT", "recursion_limit", " 64 ", 64),
    ("CONTEXT_LAB_RECURSION_LIMIT", "recursion_limit", "256", 256),
    ("CONTEXT_LAB_RUN_TIMEOUT_SECONDS", "run_timeout_seconds", "30", 30),
    ("CONTEXT_LAB_RUN_TIMEOUT_SECONDS", "run_timeout_seconds", " 300 ", 300),
    ("CONTEXT_LAB_RUN_TIMEOUT_SECONDS", "run_timeout_seconds", "1800", 1800),
])
def test_run_limits_are_parsed_and_exposed_in_effective_policy(name, field, value, expected):
    settings = Settings.from_env({name: value})
    assert getattr(settings, field) == expected
    assert settings.context_policy[field] == expected


@pytest.mark.parametrize(("name", "value"), [
    ("CONTEXT_LAB_RECURSION_LIMIT", "0"), ("CONTEXT_LAB_RECURSION_LIMIT", "7"),
    ("CONTEXT_LAB_RECURSION_LIMIT", "257"), ("CONTEXT_LAB_RECURSION_LIMIT", "3.5"),
    ("CONTEXT_LAB_RECURSION_LIMIT", "true"), ("CONTEXT_LAB_RUN_TIMEOUT_SECONDS", "0"),
    ("CONTEXT_LAB_RUN_TIMEOUT_SECONDS", "29"), ("CONTEXT_LAB_RUN_TIMEOUT_SECONDS", "1801"),
    ("CONTEXT_LAB_RUN_TIMEOUT_SECONDS", "3.5"), ("CONTEXT_LAB_RUN_TIMEOUT_SECONDS", "true"),
])
def test_invalid_run_limits_are_rejected_before_model_access(name, value):
    with pytest.raises(ValueError, match=name):
        Settings.from_env({name: value})


def test_effective_policy_is_a_fresh_copy_and_does_not_change_other_settings():
    settings = Settings.from_env({"CONTEXT_LAB_MAX_OUTPUT_TOKENS": "6000"})
    policy = settings.context_policy
    policy["max_output_tokens"] = 128
    policy["search_max_queries"] = 999
    assert settings.context_policy["max_output_tokens"] == 6000
    assert settings.context_policy["search_max_queries"] == 4
    assert Settings().context_policy["max_output_tokens"] == 3000
    assert CONTEXT_POLICY["max_output_tokens"] == 3000


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_protocol_adapter_uses_the_configured_output_budget_without_network(provider):
    settings = Settings(provider=provider, api_key="model-test", querit_key="search-test", max_output_tokens=6000)
    model = agent.create_model(settings, "selected-model")
    assert model.max_tokens == 6000


def test_live_result_reports_the_same_effective_output_budget(monkeypatch):
    captured = {}
    real_timeout = asyncio.timeout

    def timeout(seconds):
        captured["timeout"] = seconds
        return real_timeout(seconds)

    class Graph:
        async def astream_events(self, inputs, *, config, version):
            captured["config"] = config
            yield {"event": "on_chain_end", "parent_ids": [], "data": {
                "output": {"messages": [AIMessage(content="Done.")], "files": {}}}}

    monkeypatch.setattr(agent, "build_agent", lambda *args, **kwargs: (Graph(), {"count": 0}))
    monkeypatch.setattr(agent.asyncio, "timeout", timeout)
    settings = Settings(api_key="model-test", querit_key="search-test", max_output_tokens=6000,
                        recursion_limit=64, run_timeout_seconds=300)

    async def collect():
        return [item async for item in agent.live_events(settings, "selected-model", "Test", "en", "")]

    result = asyncio.run(collect())[-1]["result"]
    assert result["context_policy"]["max_output_tokens"] == 6000
    assert result["context_policy"]["recursion_limit"] == 64
    assert result["context_policy"]["run_timeout_seconds"] == 300
    assert captured["config"]["recursion_limit"] == 64
    assert captured["timeout"] == 300
    result["context_policy"]["max_output_tokens"] = 128
    assert settings.context_policy["max_output_tokens"] == 6000


def test_config_and_both_fixture_sides_share_the_configured_output_budget(tmp_path):
    settings = Settings(max_output_tokens=6000, recursion_limit=64, run_timeout_seconds=300)
    client = TestClient(create_app(settings=settings, memory_path=tmp_path / "memory.json"))
    assert client.get("/api/config").json()["context_policy"]["max_output_tokens"] == 6000
    response = client.post("/api/compare", json={
        "prompt": "Same task", "left": {"model_id": "a"}, "right": {"model_id": "b"}})
    assert response.status_code == 200
    packets = [json.loads(line) for line in response.text.splitlines() if line]
    assert packets[0]["shared"]["context_policy"]["max_output_tokens"] == 6000
    results = [packet for packet in packets if packet["type"] == "result"]
    assert {packet["side"] for packet in results} == {"left", "right"}
    assert all(packet["result"]["context_policy"]["max_output_tokens"] == 6000 for packet in results)
    assert all(packet["result"]["context_policy"]["recursion_limit"] == 64 for packet in results)
    assert all(packet["result"]["context_policy"]["run_timeout_seconds"] == 300 for packet in results)
