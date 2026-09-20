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

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, *args, **kwargs):
        self.calls += 1
        return super()._generate(*args, **kwargs)


@pytest.fixture(autouse=True)
def offline_environment(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "offline-test-key")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    # A missing mock must fail locally, never fall through to a live service.
    monkeypatch.setenv("TYPESAFE_BASE_URL", "http://127.0.0.1:1")


def setup_harness(monkeypatch, *, probability=0.01, fail=None, choice="fast", parallel=False):
    requests = []
    tool_calls = [{"name": "read_service_status", "args": {}, "id": "read-1", "type": "tool_call"}]
    if parallel:
        tool_calls.append(
            {"name": "delete_backups", "args": {}, "id": "delete-1", "type": "tool_call"}
        )
    models = {
        name: ScriptedModel(
            responses=[AIMessage(content="", tool_calls=tool_calls), AIMessage(content=name)]
        )
        for name in ("fast", "powerful")
    }

    def transport(request):
        payload = json.loads(request.content)
        requests.append(payload)
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
            risk = probability
            if parallel:
                risk = 0.99 if payload["state"]["tool_call"]["name"] == "delete_backups" else 0.01
            answer = {"type": "noul", "noul": risk}
        return httpx2.Response(200, json={"model": "jev-fixture", "answers": {question: answer}})

    original = agent.make_middleware

    def make_middleware(models):
        middleware = original(models)
        for item in middleware:
            if hasattr(item, "classifier"):
                item.classifier.client.close()
                item.classifier.client = httpx2.Client(transport=httpx2.MockTransport(transport))
                item.classifier.async_client = httpx2.AsyncClient(
                    transport=httpx2.MockTransport(transport)
                )
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
        assert audit["risk_probability"] is None  # upstream does not expose allowed scores


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
    assert len(requests) == 3


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
