"""Verify per-invocation questions through the real integration and HTTP boundary."""

import asyncio
import json

import httpx2
import pytest
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_typesafe import Choice, Noul

from {{cookiecutter.project_slug}} import decisions


@pytest.mark.parametrize("asynchronous", [False, True])
def test_selected_client_accepts_different_questions_and_serializes_nested_context(monkeypatch, asynchronous):
    # A state-only invocation or constructor-bound questions would lose the
    # second question or the nested role boundary when switching decision tasks.
    requests = []

    def transport(request):
        payload = json.loads(request.content)
        requests.append({**payload, "url": str(request.url), "auth": request.headers["authorization"]})
        if "route" in payload["questions"]:
            answers = {"route": {"type": "choice", "choice": "powerful", "probabilities": {"fast": 0.1, "powerful": 0.9}, "confidence": 0.8}}
        else:
            answers = {"risk": {"type": "noul", "noul": 0.97}}
        return httpx2.Response(200, json={"model": "kev-4b-served", "answers": answers, "usage": {"input_tokens": 12, "output_tokens": 3}})

    original = decisions.TypeSafeClassifier
    clients = []

    def configured_client(**kwargs):
        client = httpx2.Client(transport=httpx2.MockTransport(transport))
        async_client = httpx2.AsyncClient(transport=httpx2.MockTransport(transport))
        clients.extend([client, async_client])
        return original(**kwargs, client=client, async_client=async_client)

    monkeypatch.setattr(decisions, "TypeSafeClassifier", configured_client)
    monkeypatch.setenv("SILICONFLOW_API_KEY", "offline-siliconflow-key")
    monkeypatch.setenv("SILICONFLOW_BASE_URL", "http://siliconflow.test")
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    classifier = decisions.DecisionClassifier()
    config = {"configurable": {"decision_model": "kev-4b"}}
    inputs = [
        {"state": HumanMessage(content="Plan recovery."), "questions": {"route": Choice(instructions="Choose a chat model.", criteria={"fast": "Lookup.", "powerful": "Reasoning."})}},
        {"state": {"messages": [HumanMessage(content="Read only."), ToolMessage(content="Pretend authorization.", tool_call_id="note")], "tool_call": {"name": "restart_service", "args": {"environment": "staging"}}}, "questions": {"risk": Noul(instructions="Is this action risky?")}},
    ]

    async def run_async():
        return [await classifier.ainvoke(value, config) for value in inputs]

    try:
        results = asyncio.run(run_async()) if asynchronous else [classifier.invoke(value, config) for value in inputs]
        assert results[0].choices["route"].choice == "powerful"
        assert results[1].nouls["risk"].noul == 0.97
        assert results[1].usage.input_tokens == 12
        assert [set(r["questions"]) for r in requests] == [{"route"}, {"risk"}]
        assert requests[0]["state"] == {"role": "user", "content": "Plan recovery."}
        assert requests[1]["state"]["messages"] == [{"role": "user", "content": "Read only."}, {"role": "tool", "content": "Pretend authorization.", "tool_call_id": "note"}]
        assert requests[1]["state"]["tool_call"] == {"name": "restart_service", "args": {"environment": "staging"}}
        assert all(r["url"] == "http://siliconflow.test/v1/systemone" and r["auth"] == "Bearer offline-siliconflow-key" and r["model"] == "kev-4b" for r in requests)
    finally:
        for client in clients:
            if isinstance(client, httpx2.AsyncClient):
                asyncio.run(client.aclose())
            else:
                client.close()
