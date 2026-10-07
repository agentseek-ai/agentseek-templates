"""Exercise real OpenAI parsing and v3 tool execution using recorded delta shapes."""

from __future__ import annotations

import json
import os

import httpx
import pytest
from langchain.agents import create_agent

os.environ.setdefault("OPENAI_API_KEY", "offline-test-key")
os.environ.setdefault("AGENTSEEK_MODEL_PROVIDER", "openai")
os.environ.setdefault("AGENTSEEK_MODEL", "offline-test-model")

from {{ cookiecutter.project_slug }} import agent, routes  # noqa: E402


@pytest.mark.anyio
@pytest.mark.parametrize("continuation_name", ["", None])
async def test_v3_executes_tool_when_gateway_omits_continuation_name(monkeypatch, continuation_name):
    tool_results = []

    def provider(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        results = [message["content"] for message in payload["messages"] if message["role"] == "tool"]
        tool_results.extend(results)
        if results:
            deltas = [({"content": "Topic reviewed."}, None), ({}, "stop")]
        else:
            deltas = [
                (
                    {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "check-1",
                                "type": "function",
                                "function": {"name": "inspect_streaming_topic", "arguments": ""},
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
                                "function": {"name": continuation_name, "arguments": '{"topic":"Event Streaming v3"}'},
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
        monkeypatch.setattr(routes, "graph", create_agent(model=model, tools=[agent.inspect_streaming_topic]))
        request = routes.StreamRequest(
            thread_id="gateway-regression",
            messages=[{"role": "user", "content": "Review Event Streaming v3."}],
        )
        events = [json.loads(item.removeprefix("data: ")) async for item in routes._event_stream(request)]

    assert len(tool_results) == 1
    assert tool_results[0].startswith("Local reference lookup completed for Event Streaming v3.")
    completed = [event for event in events if event["kind"] == "tool_call" and event.get("phase") == "completed"]
    assert any(event.get("tool_name") == "inspect_streaming_topic" and not event.get("error") for event in completed)
    assert any(event["kind"] == "output" and event.get("phase") == "completed" for event in events)
    assert any(event.get("text") == "Topic reviewed." for event in events)
    assert not any(event["kind"] == "error" for event in events)
