"""Exercise real OpenAI parsing and v3 tool execution using recorded delta shapes."""

from __future__ import annotations

import json

import httpx
import pytest
from {{ cookiecutter.project_slug }} import agent, routes
from langchain.agents import create_agent


@pytest.mark.anyio
@pytest.mark.parametrize("continuation_name", ["", None])
async def test_v3_executes_tool_when_gateway_omits_continuation_name(monkeypatch, continuation_name):
    tool_results = []

    def provider(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        results = [message["content"] for message in payload["messages"] if message["role"] == "tool"]
        tool_results.extend(results)
        if results:
            deltas = [({"content": "Checklist reviewed."}, None), ({}, "stop")]
        else:
            deltas = [
                (
                    {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "check-1",
                                "type": "function",
                                "function": {"name": "release_checklist", "arguments": ""},
                            }
                        ]
                    },
                    None,
                ),
                (
                    {
                        "tool_calls": [
                            {
                                "index": 0,
                                "function": {"name": continuation_name, "arguments": '{"topic":"Project Phoenix"}'},
                            }
                        ]
                    },
                    None,
                ),
                ({}, "tool_calls"),
            ]
        events = [
            {
                "id": "completion-1",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": "gateway-test",
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            }
            for delta, finish in deltas
        ]
        body = "".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n"
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, text=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as client:
        model = type(agent.model)(
            model="gateway-test", api_key="offline-key", base_url="https://gateway.test/v1", http_async_client=client
        )
        monkeypatch.setattr(routes, "graph", create_agent(model=model, tools=[agent.release_checklist]))
        request = routes.StreamRequest(
            thread_id="gateway-regression",
            messages=[{"role": "user", "content": "Review Project Phoenix."}],
            recall_enabled=False,
        )
        events = [json.loads(item.removeprefix("data: ")) async for item in routes._event_stream(request)]

    assert len(tool_results) == 1
    assert tool_results[0].startswith("Release planning checklist for Project Phoenix:")
    assert "This generic checklist does not establish any project-specific decision." in tool_results[0]
    assert any(event.get("text") == "Checklist reviewed." for event in events)
    assert not any(event["kind"] == "error" for event in events)
