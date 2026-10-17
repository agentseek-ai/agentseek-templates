from __future__ import annotations

import asyncio
import hashlib
from contextlib import contextmanager
import json
import os
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from pydantic import PrivateAttr

from {{ cookiecutter.project_slug }}.agent import build_agent, create_model, live_events, seed_input
from {{ cookiecutter.project_slug }}.context import MemoryStore, Settings
from {{ cookiecutter.project_slug }}.discovery import discover_models
from {{ cookiecutter.project_slug }}.server import create_app


class ScriptedModel(BaseChatModel):
    responses: list[AIMessage]
    _position: int = PrivateAttr(default=0)

    @property
    def _llm_type(self):
        return "scripted-offline-test"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        message = self.responses[self._position]
        self._position += 1
        return ChatResult(generations=[ChatGeneration(message=message)])


def call(name, args, identifier):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": identifier}])


@tool
async def fake_search(query: str) -> str:
    """Return synthetic labeled evidence without network access."""
    return "Synthetic evidence. Source: https://docs.langchain.com/oss/python/deepagents/overview"


def packets(response):
    return [json.loads(line) for line in response.text.splitlines() if line]


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_real_harness_loads_skill_delegates_search_and_preserves_sources(provider):
    model = ScriptedModel(responses=[
        call("read_file", {"file_path": "/skills/research-brief/SKILL.md"}, "skill"),
        call("task", {"subagent_type": "researcher", "description": "Find one source"}, "delegate"),
        call("querit_search", {"query": "memory"}, "search"), AIMessage(content="A synthetic source."),
        call("write_file", {"file_path": "/reports/brief.md", "content": "Test brief."}, "write"),
        AIMessage(content="Final brief."),
    ])

    async def collect():
        return [item async for item in live_events(Settings(provider=provider, api_key="test", querit_key="test"),
            "user-model", "Research", "en", "Approved", "Full source. " * 100, model=model, search_tool=fake_search)]
    result = asyncio.run(collect())[-1]["result"]
    assert result["answer"] == "Final brief."
    assert result["files"]["/reports/brief.md"] == "Test brief."
    assert result["files"]["/sources/user-material.md"] == "Full source. " * 100
    assert result["files"]["/memories/AGENTS.md"] == "Approved"
    assert result["metrics"]["search_calls"] == 1
    assert result["metrics"]["provider_calls"] == 6
    assert result["status"] == "complete"
    assert "mode" not in result


@pytest.mark.parametrize(("provider", "reason"), [("openai", {"finish_reason": "length"}),
                                                   ("anthropic", {"stop_reason": "max_tokens"})])
def test_truncated_empty_final_keeps_partial_files_without_old_draft_fallback(provider, reason):
    model = ScriptedModel(responses=[
        AIMessage(content="Old draft.", tool_calls=[{"name": "write_file", "args": {
            "file_path": "/reports/partial.md", "content": "Partial."}, "id": "partial"}]),
        AIMessage(content="", response_metadata=reason,
                  usage_metadata={"input_tokens": 10, "output_tokens": 3, "total_tokens": 13}),
    ])

    async def collect():
        return [item async for item in live_events(Settings(provider=provider, api_key="test", querit_key="test"),
            "selected", "test", "en", "Approved", model=model, search_tool=fake_search)]
    result = asyncio.run(collect())[-1]["result"]
    assert result["answer"] == ""
    assert result["status"] == "incomplete"
    assert result["warning"] == "output_token_limit"
    assert result["files"]["/reports/partial.md"] == "Partial."
    assert result["metrics"]["tokens"]["total_tokens"] == 13


def test_approved_memory_cannot_be_changed_by_graph():
    model = ScriptedModel(responses=[call("edit_file", {"file_path": "/memories/AGENTS.md",
        "old_string": "Approved", "new_string": "Injected"}, "tamper"), AIMessage(content="Done.")])
    graph, _ = build_agent(Settings(api_key="test", querit_key="test"), "selected", model=model, search_tool=fake_search)
    state = graph.invoke(seed_input("Hello", "en", "Approved"))
    assert state["files"]["/memories/AGENTS.md"]["content"] == "Approved"


def test_native_compaction_keeps_original_history():
    model = ScriptedModel(responses=[AIMessage(content="Historical summary."), AIMessage(content="Fresh answer.")])
    graph, _ = build_agent(Settings(api_key="test", querit_key="test"), "selected", model=model, search_tool=fake_search)
    inputs = seed_input("Continue", "en", "Approved")
    original = "Original historical evidence. " * 200
    inputs["messages"] = [{"role": "user" if i % 2 == 0 else "assistant", "content": original} for i in range(18)]
    inputs["messages"].append({"role": "user", "content": "Continue."})
    state = graph.invoke(inputs)
    assert model._position == 2
    assert state["messages"][-1].content == "Fresh answer."
    assert any(original in data["content"] for path, data in state["files"].items()
               if path.startswith("/conversation_history/"))


def test_native_large_tool_result_remains_retrievable():
    original = "Synthetic long evidence. " * 10000

    @tool
    async def long_search(query: str) -> str:
        """Return synthetic long evidence, no HTTP."""
        return original

    model = ScriptedModel(responses=[call("querit_search", {"query": "test"}, "large"), AIMessage(content="Done.")])

    async def collect():
        return [item async for item in live_events(Settings(api_key="test", querit_key="test"), "selected",
            "test", "en", "", model=model, search_tool=long_search)]
    result = asyncio.run(collect())[-1]["result"]
    assert any(original in text for path, text in result["files"].items() if path.startswith("/large_tool_results/"))


@pytest.mark.parametrize(("provider", "effort", "expected"), [("openai", "low", "low"),
    ("openai", "", None), ("anthropic", "high", None)])
def test_protocol_adapter_explicit_model_and_optional_reasoning(provider, effort, expected, monkeypatch):
    seen = {}

    def adapter(**kwargs):
        seen.update(kwargs)
        return object()

    monkeypatch.setattr("langchain_openai.ChatOpenAI" if provider == "openai" else
                        "langchain_anthropic.ChatAnthropic", adapter)
    settings = Settings.from_env({"AGENTSEEK_MODEL_PROVIDER": provider,
        "OPENAI_API_KEY": "openai-test", "ANTHROPIC_API_KEY": "anthropic-test", "QUERIT_API_KEY": "search-test"})
    create_model(settings, "exact-user-model", effort)
    assert seen["model"] == "exact-user-model"
    assert seen["api_key"] == f"{provider}-test"
    assert seen["max_tokens"] == 3000
    assert seen.get("reasoning_effort") == expected
    if expected is None:
        assert "reasoning_effort" not in seen
    assert ("use_responses_api" in seen) == (provider == "openai")


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_model_discovery_uses_selected_real_sdk_interface_without_invented_ids(provider, monkeypatch):
    seen = {}

    class Client:
        def __init__(self, **kwargs):
            seen.update(kwargs)
            self.models = self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def list(self):
            return SimpleNamespace(data=[SimpleNamespace(id="actual-b"), SimpleNamespace(id="actual-a")],
                                   has_next_page=lambda: False)

    monkeypatch.setattr("openai.AsyncOpenAI" if provider == "openai" else "anthropic.AsyncAnthropic", Client)
    result = asyncio.run(discover_models(Settings(provider=provider, api_key="selected-key",
        base_url="https://inference.example/v1", models_base_url="https://catalog.example/v1")))
    assert result == {"models": ["actual-a", "actual-b"], "complete": True}
    assert seen["base_url"] == "https://catalog.example/v1"
    assert seen["timeout"] == 15
    assert seen["max_retries"] == 0
    assert seen["api_key"] == "selected-key"


def test_discovery_failure_is_honest_and_manual_entry_remains_available(tmp_path):
    async def unsupported(settings):
        raise RuntimeError("private provider response with secret headers")
    client = TestClient(create_app(settings=Settings(api_key="secret"), memory_path=tmp_path / "memory.json",
                                  models_loader=unsupported))
    result = client.get("/api/models").json()
    assert result["available"] is False
    assert result["models"] == []
    assert result["manual_allowed"]
    assert "private" not in str(result)
    assert "secret" not in str(result)


def test_compare_freezes_same_inputs_and_memory_separates_options_and_continues_after_error(tmp_path):
    path = tmp_path / "memory.json"
    MemoryStore(path).save("Original approved memory", approved=True)
    observed = []

    async def runner(settings, model_id, prompt, language, memory, material, *, reasoning_effort, metadata):
        observed.append((model_id, prompt, language, memory, material, reasoning_effort, metadata))
        if metadata["side"] == "left":
            MemoryStore(path).save("Changed between sides", approved=True)
            yield {"type": "event", "event": {"kind": "tool", "name": "querit_search", "detail": "started"}}
            raise RuntimeError("private provider error")
        yield {"type": "result", "result": {"status": "complete", "answer": "Right result", "files": {}}}

    client = TestClient(create_app(settings=Settings(api_key="model", querit_key="search"), memory_path=path,
                                  run_events=runner))
    response = client.post("/api/compare", json={"execution": "live", "language": "en", "prompt": "Same task",
        "material": "Same source", "left": {"model_id": "model-a", "reasoning_effort": "low"},
        "right": {"model_id": "model-b", "reasoning_effort": ""}})
    items = packets(response)
    assert response.status_code == 200
    assert observed[0][1:5] == observed[1][1:5] == ("Same task", "en", "Original approved memory", "Same source")
    assert observed[0][5] == "low" and observed[1][5] == ""
    assert observed[0][6]["compare_id"] == observed[1][6]["compare_id"]
    assert [item["side"] for item in items if item["type"] == "side_start"] == ["left", "right"]
    assert any(item["type"] == "error" and item["side"] == "left" for item in items)
    assert any(item["type"] == "result" and item["side"] == "right" for item in items)
    assert items[0]["shared"]["prompt_sha256"] == hashlib.sha256(b"Same task").hexdigest()
    assert items[0]["shared"]["material_sha256"] == hashlib.sha256(b"Same source").hexdigest()
    assert items[-1]["outcomes"] == {"left": "error", "right": "complete"}
    assert "private provider error" not in response.text


def test_http_fixture_gate_memory_and_same_origin(tmp_path):
    path = tmp_path / "memory.json"
    client = TestClient(create_app(settings=Settings(), memory_path=path))
    payload = {"prompt": "Research", "left": {"model_id": "a"}, "right": {"model_id": "b"}}
    assert client.post("/api/compare", json={**payload, "execution": "live"}).status_code == 400
    items = packets(client.post("/api/compare", json=payload))
    results = [item["result"] for item in items if item["type"] == "result"]
    assert len(results) == 2
    assert all(result["execution"] == "fixture" and result["metrics"]["provider_calls"] == 0 for result in results)
    assert client.put("/api/memory", json={"text": "Preference"}).status_code == 400
    assert client.put("/api/memory", json={"text": "Preference", "approved": True}).status_code == 200
    assert MemoryStore(path).read() == "Preference"
    assert client.put("/api/memory", json={"text": "untrusted", "approved": True},
                      headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/config", headers={"Host": "evil.example"}).status_code == 403
    config = client.get("/api/config").json()
    assert "models" not in config
    assert not config["tracing_enabled"]


def test_unreadable_memory_does_not_keep_comparison_locked(tmp_path):
    path = tmp_path / "memory.json"
    path.write_text("not valid JSON", encoding="utf-8")
    client = TestClient(create_app(settings=Settings(), memory_path=path), raise_server_exceptions=False)
    payload = {"prompt": "Research", "left": {"model_id": "a"}, "right": {"model_id": "b"}}
    assert client.get("/api/config").status_code == 503
    assert client.post("/api/compare", json=payload).status_code == 503
    MemoryStore(path).save("Recovered preference", approved=True)
    response = client.post("/api/compare", json=payload)
    assert response.status_code == 200
    results = [item["result"] for item in packets(response) if item["type"] == "result"]
    assert len(results) == 2
    assert all(result["memory"] == "Recovered preference" for result in results)


def test_querit_uses_settings_key_without_mutating_the_process_environment(monkeypatch):
    from langchain_websearch.querit_search import QueritSearchBackend

    monkeypatch.delenv("QUERIT_API_KEY", raising=False)
    captured = []

    def search(self, query, num_results):
        captured.append((self.api_key, query, num_results))
        return []

    monkeypatch.setattr(QueritSearchBackend, "search", search)
    model = ScriptedModel(responses=[call("querit_search", {"query": "configured search"}, "search"),
                                      AIMessage(content="Done.")])

    async def collect():
        return [item async for item in live_events(Settings(api_key="model-test", querit_key="configured-test"),
            "selected", "Research", "en", "", model=model)]

    result = asyncio.run(collect())[-1]["result"]
    assert captured == [("configured-test", "configured search", 3)]
    assert "QUERIT_API_KEY" not in os.environ
    assert result["metrics"]["search_calls"] == 1


def test_traces_have_compare_metadata_and_explicitly_disabled_default(monkeypatch):
    from {{ cookiecutter.project_slug }} import agent
    captured = {}

    class Graph:
        async def astream_events(self, inputs, *, config, version):
            captured["config"] = config
            yield {"event": "on_chain_end", "parent_ids": [], "data": {"output": {
                "messages": [AIMessage(content="Done.")], "files": inputs["files"]}}}

    @contextmanager
    def tracing_context(**kwargs):
        captured["tracing"] = kwargs
        yield

    monkeypatch.setattr(agent, "build_agent", lambda *args, **kwargs: (Graph(), {"count": 0}))
    monkeypatch.setattr("langsmith.tracing_context", tracing_context)

    async def collect():
        return [item async for item in live_events(Settings(api_key="test", querit_key="test"), "selected",
            "private task", "en", "", metadata={"compare_id": "pair", "side": "left", "model_id": "selected"})]
    asyncio.run(collect())
    assert captured["tracing"]["enabled"] is False
    assert captured["config"]["metadata"] == {"compare_id": "pair", "side": "left", "model_id": "selected"}
    assert "private task" not in str(captured["config"])


def test_setup_preserves_other_provider_and_custom_values_and_adds_tracing_defaults(tmp_path, monkeypatch):
    from dotenv import dotenv_values
    from {{ cookiecutter.project_slug }}.setup import main

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text('OPENAI_API_KEY="keep"\nCUSTOM_SETTING="stay"\n', encoding="utf-8")
    answers = iter(["anthropic", "https://compatible.example"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    monkeypatch.setattr("getpass.getpass", lambda prompt: "fake-test-key")
    main()
    saved = dotenv_values(tmp_path / ".env", interpolate=False)
    assert saved["OPENAI_API_KEY"] == "keep"
    assert saved["CUSTOM_SETTING"] == "stay"
    assert saved["AGENTSEEK_MODEL_PROVIDER"] == "anthropic"
    assert saved["LANGSMITH_TRACING"] == "false"
    assert saved["LANGSMITH_ENDPOINT"] == "https://apac.api.smith.langchain.com"
    assert (tmp_path / ".env").stat().st_mode & 0o077 == 0
