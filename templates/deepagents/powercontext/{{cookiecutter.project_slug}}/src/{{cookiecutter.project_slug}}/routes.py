"""Custom SSE route that streams the recalled context and the answer.

The route still drives the documented Deep Agents v3 run stream, but it only
forwards the PowerContext recall events and the agents' messages. The protocol
projections (raw events, state snapshots, sub-agent and tool lifecycles) are
consumed and discarded so a run does not ship megabytes of protocol data to the
browser.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .agent import stream_graph as graph
from .event_adapter import error_event, message_event, powercontext_event
from .powercontext_middleware import (
    recall_options,
    reset_event_sink,
    reset_recall_query,
    set_event_sink,
    set_recall_query,
)
from .project_memory import router as memory_router

app = FastAPI(title="{{ cookiecutter.project_name }} Event Streaming")
# Register the memory router's concrete routes directly instead of calling
# ``app.include_router``. AgentSeek API merges a custom app by copying
# ``app.router.routes`` and skipping entries without a concrete path, while recent
# FastAPI versions defer ``include_router`` behind a lazy ``_IncludedRouter`` whose
# path is ``None``. The lazy entry would be dropped and every /custom/memory route
# would return 404 under the AgentSeek API runtime.
app.router.routes.extend(memory_router.routes)


class StreamRequest(BaseModel):
    messages: list[dict[str, Any]] = Field(min_length=1)
    thread_id: str = Field(min_length=1, pattern=r"\S")
    recall_enabled: bool = True
    max_bytes: int | None = Field(default=None, ge=512, le=32768)


async def _resolve(value: Any) -> Any:
    while callable(value):
        value = value()
    if inspect.isawaitable(value):
        return await _resolve(await value)
    if hasattr(value, "__aiter__"):
        return [item async for item in value]
    return value


async def _text(value: Any) -> str:
    resolved = await _resolve(value)
    if isinstance(resolved, list):
        return "".join(str(item) for item in resolved)
    return str(resolved or "")


async def _consume_messages(
    run: Any, queue: asyncio.Queue[dict[str, Any] | None], *, source: str, path: list[str]
) -> None:
    async for message in run.messages:
        await queue.put(message_event(source=source, path=path, text=await _text(message.text)))


def _request_query(messages: list[dict[str, Any]]) -> str:
    """Return the run's original user question, used to scope every recall."""
    for message in reversed(messages):
        if str(message.get("role", "")).lower() == "user":
            content = message.get("content", "")
            return content if isinstance(content, str) else str(content)
    return ""


async def _produce_events(request: StreamRequest, queue: asyncio.Queue[dict[str, Any] | None]) -> None:
    try:

        async def publish_context(status: dict[str, Any]) -> None:
            await queue.put(powercontext_event(**status))

        event_token = set_event_sink(publish_context)
        recall_token = recall_options.set((request.recall_enabled, request.max_bytes))
        query_token = set_recall_query(_request_query(request.messages))
        config = {"configurable": {"thread_id": request.thread_id}}
        run = await graph.astream_events({"messages": request.messages}, config=config, version="v3")
        # Draining the message projection drives the run to completion and lets
        # the PowerContext middleware publish its recall events through the sink.
        await _consume_messages(run, queue, source="coordinator", path=[])
    except Exception as exc:
        await queue.put(error_event(message=f"Event stream failed: {exc}"))
    finally:
        if "event_token" in locals():
            reset_event_sink(event_token)
        if "recall_token" in locals():
            recall_options.reset(recall_token)
        if "query_token" in locals():
            reset_recall_query(query_token)
        await queue.put(None)


async def _event_stream(request: StreamRequest) -> AsyncIterator[str]:
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    producer = asyncio.create_task(_produce_events(request, queue))
    try:
        while True:
            event = await queue.get()
            if event is None:
                break
            yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
    finally:
        if not producer.done():
            producer.cancel()
        await asyncio.gather(producer, return_exceptions=True)


@app.get("/custom/health")
def custom_health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/custom/stream")
async def custom_stream(request: StreamRequest) -> StreamingResponse:
    return StreamingResponse(_event_stream(request), media_type="text/event-stream")
