"""Use real middleware + HTTP transports, with no external provider calls."""

import asyncio
import json

import httpx2
import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from {{cookiecutter.project_slug}} import agent


class ScriptedModel(FakeMessagesListChatModel):
    calls: int = 0
    last_messages: list = []

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, *args, **kwargs):
        self.calls += 1
        self.last_messages = args[0]
        return super()._generate(*args, **kwargs)


@pytest.fixture(autouse=True)
def offline_environment(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "offline-test-key")
    monkeypatch.setenv("SILICONFLOW_API_KEY", "offline-siliconflow-key")
    monkeypatch.setenv("SILICONFLOW_BASE_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    # A missing mock must fail locally, never fall through to a live service.
    monkeypatch.setenv("TYPESAFE_BASE_URL", "http://127.0.0.1:1")


def setup_harness(monkeypatch, *, probability=0.01, fail=None, choice="fast", parallel=False):
    requests = []
    tool_calls = [{"name": "read_service_status", "args": {}, "id": "read-1", "type": "tool_call"}]
    if parallel:
        tool_calls.append(
            {"name": "delete_backups", "args": {"environment": "production", "scope": "all"}, "id": "delete-1", "type": "tool_call"}
        )
    models = {
        name: ScriptedModel(
            responses=[AIMessage(content="", tool_calls=tool_calls), AIMessage(content=name)]
        )
        for name in ("fast", "powerful")
    }

    def transport(request):
        payload = json.loads(request.content)
        requests.append({**payload, "_host": str(request.url), "_auth": request.headers["authorization"]})
        assert request.url.path == "/v1/systemone"
        question = next(iter(payload["questions"]))
        if fail == question:
            return httpx2.Response(503, json={"error": "fixture outage"})
        if question == "model_route":
            selected = choice if isinstance(choice, str) else choice.pop(0)
            answer = {
                "type": "choice",
                "choice": selected,
                "confidence": 0.8,
                "probabilities": {
                    "fast": 0.9 if selected == "fast" else 0.1,
                    "powerful": 0.9 if selected == "powerful" else 0.1,
                },
            }
        else:
            risk = probability(payload["state"]) if callable(probability) else probability
            if parallel:
                risk = 0.99 if payload["state"]["tool_call"]["name"] == "delete_backups" else 0.01
            answer = {"type": "noul", "noul": risk}
        return httpx2.Response(200, json={"model": payload["model"] + "-fixture", "answers": {question: answer}})

    original = agent.make_middleware

    def make_middleware(models):
        middleware = original(models)
        for item in middleware:
            if hasattr(item, "classifier"):
                classifier = getattr(item, "risk_classifier", item.classifier)
                for provider in getattr(classifier, "classifiers", {"legacy": classifier}).values():
                    provider.client.close()
                    provider.client = httpx2.Client(transport=httpx2.MockTransport(transport))
                    provider.async_client = httpx2.AsyncClient(transport=httpx2.MockTransport(transport))
        return middleware

    monkeypatch.setattr(agent, "make_middleware", make_middleware)
    return agent.build_agent(models, checkpointer=InMemorySaver()), models, requests


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize(
    "probability,decision", [(0.01, "allowed"), (0.5, "blocked"), (0.99, "blocked")]
)
def test_route_once_and_gate_before_execution(monkeypatch, probability, decision, asynchronous):
    graph, models, requests = setup_harness(monkeypatch, probability=probability)
    args = (
        {"messages": [{"role": "user", "content": "Read service status."}]},
        {"configurable": {"thread_id": "threshold"}},
    )
    result = asyncio.run(graph.ainvoke(*args)) if asynchronous else graph.invoke(*args)
    assert models["fast"].calls == 2
    assert models["powerful"].calls == 0
    assert [next(iter(r["questions"])) for r in requests] == ["model_route", "is_risky"]
    assert result["route_report"]["choice"] == "fast"
    assert result["route_report"]["confidence"] == 0.8
    assert set(result["route_report"]["models"]) == {"fast", "powerful"}
    tool = next(m for m in result["messages"] if isinstance(m, ToolMessage))
    audit = tool.artifact["auto_mode"]
    assert audit["decision"] == decision
    assert audit["executed"] is (decision == "allowed")
    if decision == "blocked":
        assert tool.status == "error"
        assert audit["risk_probability"] == probability
        assert "checkout" not in tool.content
    else:
        assert "checkout" in tool.content
        assert audit["risk_probability"] == probability
    assert audit["raw_answer"] == {"type": "noul", "noul": probability}
    assert audit["confidence"] is None  # Noul has no native confidence field.
    assert audit["arguments"] == {}


def test_reroutes_followup_and_restores_checkpoint(monkeypatch):
    graph, models, requests = setup_harness(monkeypatch, choice=["fast", "powerful"])
    config = {"configurable": {"thread_id": "followup"}}
    graph.invoke({"messages": [{"role": "user", "content": "Read status."}]}, config)
    result = graph.invoke(
        {"messages": [{"role": "user", "content": "Plan a multi-region recovery."}]}, config
    )
    assert result["route_report"]["choice"] == "powerful"
    assert models["fast"].calls == models["powerful"].calls == 2
    route_requests = [r for r in requests if "model_route" in r["questions"]]
    assert len(route_requests) == 2
    assert "Read status" not in json.dumps(route_requests[-1]["state"])
    assert "multi-region" in json.dumps(route_requests[-1]["state"])


@pytest.mark.parametrize("failure", ["model_route", "is_risky"])
@pytest.mark.parametrize("asynchronous", [False, True])
def test_classifier_failure_stops_run_without_execution(monkeypatch, failure, asynchronous):
    graph, models, _ = setup_harness(monkeypatch, fail=failure)
    args = (
        {"messages": [{"role": "user", "content": "Read status."}]},
        {"configurable": {"thread_id": "failure"}},
    )
    with pytest.raises(Exception, match="503"):
        asyncio.run(graph.ainvoke(*args)) if asynchronous else graph.invoke(*args)
    state = graph.get_state(args[1]).values
    assert not any(isinstance(m, ToolMessage) for m in state["messages"])
    assert models["fast"].calls == (0 if failure == "model_route" else 1)


async def test_parallel_tools_have_independent_decisions(monkeypatch):
    graph, _, requests = setup_harness(monkeypatch, parallel=True)
    result = await graph.ainvoke(
        {"messages": [{"role": "user", "content": "Read status and delete backups."}]},
        {"configurable": {"thread_id": "parallel"}},
    )
    tools = {
        m.name: m.artifact["auto_mode"] for m in result["messages"] if isinstance(m, ToolMessage)
    }
    assert tools["read_service_status"]["executed"] is True
    assert tools["delete_backups"]["executed"] is False
    assert tools["read_service_status"]["risk_probability"] == 0.01
    assert tools["delete_backups"]["risk_probability"] == 0.99
    assert len(requests) == 3


@pytest.mark.parametrize("asynchronous", [False, True])
def test_fixed_proposal_changes_decision_with_user_context(monkeypatch, asynchronous):
    def contextual_risk(state):
        return 0.04 if "authorize" in state["messages"][0]["content"] else 0.94

    graph, models, requests = setup_harness(monkeypatch, probability=contextual_risk)
    for model in models.values():
        model.responses = [AIMessage(content="Result explained.")]
    reports = []
    for index, prompt in enumerate(("I authorize restarting staging checkout.", "Diagnose only. Do not restart.")):
        args = ({"messages": [{"role": "user", "content": prompt}], "proposal_id": "restart-approved"},
                {"configurable": {"thread_id": f"context-{index}"}})
        result = asyncio.run(graph.ainvoke(*args)) if asynchronous else graph.invoke(*args)
        tool = next(m for m in result["messages"] if isinstance(m, ToolMessage))
        assert tool.name == "restart_service"
        audit = tool.artifact["auto_mode"]
        assert audit["proposal_source"] == "preset"
        reports.append(audit)
    assert reports[0]["decision"] == "allowed"
    assert reports[1]["decision"] == "blocked"
    assert reports[0]["arguments"] == reports[1]["arguments"] == {"environment": "staging"}


async def test_injected_tool_content_reaches_gate_without_becoming_user_authority(monkeypatch):
    graph, models, requests = setup_harness(monkeypatch, probability=lambda s: 0.93 if s["tool_call"]["name"] == "restart_service" else 0.01)
    for model in models.values():
        model.responses = [AIMessage(content="Result explained.")]
    result = await graph.ainvoke(
        {"messages": [{"role": "user", "content": "Read the note only. Do not restart."}], "proposal_id": "injected-note"},
        {"configurable": {"thread_id": "injection"}},
    )
    tools = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert [m.name for m in tools] == ["read_incident_note", "restart_service"]
    assert tools[-1].artifact["auto_mode"]["executed"] is False
    risk_state = next(r["state"] for r in requests if "is_risky" in r["questions"] and r["state"]["tool_call"]["name"] == "restart_service")
    assert any(m["role"] == "tool" and "administrator" in m["content"] for m in risk_state["messages"])
    assert sum(m["role"] == "user" for m in risk_state["messages"]) == 1


def test_unknown_proposal_cannot_select_arbitrary_tools(monkeypatch):
    graph, models, _ = setup_harness(monkeypatch)
    with pytest.raises(ValueError, match="Unknown proposal"):
        graph.invoke({"messages": [{"role": "user", "content": "Inspect."}], "proposal_id": "arbitrary-tool"},
                     {"configurable": {"thread_id": "invalid"}})
    assert models["fast"].calls == models["powerful"].calls == 0


@pytest.mark.parametrize("asynchronous", [False, True])
def test_allowed_but_invalid_arguments_do_not_claim_handler_executed(monkeypatch, asynchronous):
    graph, models, _ = setup_harness(monkeypatch)
    models["fast"].responses = [
        AIMessage(content="", tool_calls=[{"name": "restart_service", "args": {}, "id": "invalid", "type": "tool_call"}]),
        AIMessage(content="Invalid proposal."),
    ]
    args = ({"messages": [{"role": "user", "content": "Restart staging."}]},
            {"configurable": {"thread_id": "invalid-args"}})
    result = asyncio.run(graph.ainvoke(*args)) if asynchronous else graph.invoke(*args)
    tool = next(m for m in result["messages"] if isinstance(m, ToolMessage))
    assert tool.status == "error"
    assert tool.artifact["auto_mode"]["decision"] == "allowed"
    assert tool.artifact["auto_mode"]["executed"] is False
    assert tool.artifact["auto_mode"]["execution_status"] == "failed"


def test_every_exposed_tool_is_guarded(monkeypatch):
    graph, _, requests = setup_harness(monkeypatch)
    assert graph is not None
    middleware = agent.make_middleware(
        {name: ScriptedModel(responses=[AIMessage(content="ok")]) for name in ("fast", "powerful")}
    )
    gate = next(
        item for item in middleware if hasattr(item, "config") and hasattr(item.config, "tools")
    )
    assert {t.name for t in gate.config.tools} == {t.name for t in agent.TOOLS}
    assert requests == []


def test_chat_provider_configuration_is_shared_by_both_routes(monkeypatch):
    monkeypatch.setattr(agent, "load_dotenv", lambda: None)
    monkeypatch.setenv("OPENAI_API_KEY", "siliconflow-test")
    monkeypatch.setenv("OPENAI_API_BASE", "https://api.siliconflow.cn/v1")
    monkeypatch.setenv("JEV_FAST_MODEL", "deepseek-ai/DeepSeek-V4-Flash")
    monkeypatch.setenv("JEV_POWERFUL_MODEL", "deepseek-ai/DeepSeek-V4-Pro")
    monkeypatch.setenv("CHAT_MODEL_EXTRA_BODY", '{"enable_thinking":false}')
    monkeypatch.setattr(agent, "ChatOpenAI", lambda **settings: settings)
    monkeypatch.setattr(agent, "build_agent", lambda models: models)
    models = agent.make_graph()
    assert models["fast"]["model"] == "deepseek-ai/DeepSeek-V4-Flash"
    assert models["powerful"]["model"] == "deepseek-ai/DeepSeek-V4-Pro"
    for model in models.values():
        assert model["base_url"] == "https://api.siliconflow.cn/v1"
        assert model["api_key"] == "siliconflow-test"
        assert model["extra_body"] == {"enable_thinking": False}
        assert model["use_responses_api"] is False


@pytest.mark.parametrize("value", ["not-json", "[]", "null"])
def test_invalid_provider_extra_body_fails_before_model_creation(monkeypatch, value):
    monkeypatch.setattr(agent, "load_dotenv", lambda: None)
    monkeypatch.setenv("OPENAI_API_KEY", "offline-test")
    monkeypatch.setenv("CHAT_MODEL_EXTRA_BODY", value)
    with pytest.raises(ValueError, match="CHAT_MODEL_EXTRA_BODY"):
        agent.make_graph()


@pytest.mark.parametrize("asynchronous", [False, True])
def test_decision_selection_reaches_both_gates_with_separate_credentials(monkeypatch, asynchronous):
    monkeypatch.setenv("SILICONFLOW_BASE_URL", "http://siliconflow.test")
    monkeypatch.setenv("TYPESAFE_BASE_URL", "http://typesafe.test")
    graph, _, requests = setup_harness(monkeypatch)
    for selection, expected_model, provider, key in (
        (None, "semif", "siliconflow", "offline-siliconflow-key"),
        ("kev-4b", "kev-4b", "siliconflow", "offline-siliconflow-key"),
        ("diffusiongemma", "diffusiongemma", "siliconflow", "offline-siliconflow-key"),
        ("jev", "jev-latest", "typesafe", "offline-test-key"),
    ):
        config = {"configurable": {"thread_id": f"provider-{selection}"}}
        if selection:
            config["configurable"]["decision_model"] = selection
        args = ({"messages": [{"role": "user", "content": "Read status."}]}, config)
        result = asyncio.run(graph.ainvoke(*args)) if asynchronous else graph.invoke(*args)
        recent = requests[-2:]
        assert [r["model"] for r in recent] == [expected_model, expected_model]
        assert all(r["_host"] == f"http://{provider}.test/v1/systemone" for r in recent)
        assert all(r["_auth"] == f"Bearer {key}" for r in recent)
        report = result["route_report"]["decision_model"]
        assert report["provider"] == provider
        assert report["model"] == expected_model + "-fixture"
        tool = next(m for m in result["messages"] if isinstance(m, ToolMessage))
        assert tool.artifact["auto_mode"]["decision_model"] == report
        assert tool.artifact["auto_mode"]["raw_answer"] == {"type": "noul", "noul": 0.01}


async def test_concurrent_runs_keep_provider_choice_local(monkeypatch):
    graph, _, requests = setup_harness(monkeypatch)
    async def run(selection):
        result = await graph.ainvoke(
            {"messages": [{"role": "user", "content": "Read status."}]},
            {"configurable": {"thread_id": selection, "decision_model": selection}},
        )
        return result["route_report"]["decision_model"]["selection"]
    assert await asyncio.gather(run("semif"), run("jev")) == ["semif", "jev"]


@pytest.mark.parametrize("selection", ["https://untrusted.example", "not-a-model"])
def test_unknown_selection_fails_before_any_provider_or_tool(monkeypatch, selection):
    graph, models, requests = setup_harness(monkeypatch)
    with pytest.raises(ValueError, match="Unknown decision model"):
        graph.invoke({"messages": [{"role": "user", "content": "Read status."}]},
                     {"configurable": {"thread_id": "invalid-provider", "decision_model": selection}})
    assert requests == []
    assert models["fast"].calls == models["powerful"].calls == 0


def test_default_runs_without_a_jev_key_and_missing_jev_does_not_fallback(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY")
    graph, _, requests = setup_harness(monkeypatch)
    graph.invoke({"messages": [{"role": "user", "content": "Read status."}]},
                 {"configurable": {"thread_id": "no-jev-key"}})
    assert requests[0]["model"] == "semif"
    count = len(requests)
    with pytest.raises(ValueError, match="TYPESAFE_API_KEY"):
        graph.invoke({"messages": [{"role": "user", "content": "Read status."}]},
                     {"configurable": {"thread_id": "missing-jev", "decision_model": "jev"}})
    assert len(requests) == count


@pytest.mark.parametrize("base,works", [("https://api.siliconflow.cn/v1", True), ("https://other-provider.example/v1", False)])
def test_chat_key_reuse_is_limited_to_siliconflow(monkeypatch, base, works):
    monkeypatch.delenv("SILICONFLOW_API_KEY")
    monkeypatch.setenv("OPENAI_API_BASE", base)
    monkeypatch.setenv("OPENAI_API_KEY", "chat-provider-key")
    graph, _, requests = setup_harness(monkeypatch)
    args = ({"messages": [{"role": "user", "content": "Read status."}]},
            {"configurable": {"thread_id": "key-reuse"}})
    if works:
        graph.invoke(*args)
        assert all(r["_auth"] == "Bearer chat-provider-key" for r in requests)
    else:
        with pytest.raises(ValueError, match="SILICONFLOW_API_KEY"):
            graph.invoke(*args)
        assert requests == []


def test_explanation_receives_actual_gate_facts_even_when_policy_was_misclassified(monkeypatch):
    graph, models, _ = setup_harness(monkeypatch, probability=0.01)
    for model in models.values():
        model.responses = [AIMessage(content="Explained.")]
    graph.invoke({"messages": [{"role": "user", "content": "Do not restart."}], "proposal_id": "restart-readonly"},
                 {"configurable": {"thread_id": "misclassified"}})
    system = models["fast"].last_messages[0].text
    assert '"decision": "allowed"' in system
    assert '"executed": true' in system
    assert '"risk_probability": 0.01' in system
