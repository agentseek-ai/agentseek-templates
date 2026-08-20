"""Custom SSE route for the documented Deep Agents v3 projections."""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import AsyncIterator, Iterable, Mapping
from typing import Any

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .agent import stream_graph as graph
from .event_adapter import (
    error_event,
    message_event,
    output_event,
    raw_event,
    subagent_event,
    tool_event,
    values_event,
)

app = FastAPI(title="{{ cookiecutter.project_name }} Event Streaming")


class StreamRequest(BaseModel):
    messages: list[dict[str, Any]] = Field(min_length=1)
    thread_id: str | None = None


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


async def _iterate(value: Any) -> AsyncIterator[Any]:
    if hasattr(value, "__aiter__"):
        async for item in value:
            yield item
    else:
        for item in value if isinstance(value, Iterable) and not isinstance(value, (str, bytes)) else [value]:
            yield item


async def _consume_messages(run: Any, queue: asyncio.Queue[dict[str, Any] | None], *, source: str, path: list[str]) -> None:
    async for message in run.messages:
        await queue.put(message_event(source=source, path=path, text=await _text(message.text)))


async def _consume_tools(run: Any, queue: asyncio.Queue[dict[str, Any] | None], *, source: str, path: list[str]) -> None:
    async for call in run.tool_calls:
        name = await _resolve(call.tool_name)
        input_value = await _resolve(call.input)
        await queue.put(tool_event(phase="started", source=source, path=path, name=name, input_value=input_value))
        async for delta in _iterate(call.output_deltas):
            await queue.put(tool_event(phase="delta", source=source, path=path, name=name, delta=await _resolve(delta)))
        completed = await _resolve(call.completed)
        error = await _resolve(call.error)
        output = await _resolve(call.output)
        phase = "failed" if error is not None else "completed" if completed else "in_progress"
        await queue.put(
            tool_event(
                phase=phase,
                source=source,
                path=path,
                name=name,
                output=output,
                error=error,
            )
        )


async def _consume_subagent(run: Any, queue: asyncio.Queue[dict[str, Any] | None]) -> None:
    name = await _resolve(run.name)
    path = [str(part) for part in await _resolve(run.path)]
    status = await _resolve(run.status)
    await queue.put(subagent_event(phase="started", name=name, path=path, status=status))
    nested_tasks: list[asyncio.Task[None]] = []

    async def consume_nested() -> None:
        async for nested in run.subagents:
            nested_tasks.append(asyncio.create_task(_consume_subagent(nested, queue)))
        if nested_tasks:
            await asyncio.gather(*nested_tasks)

    try:
        await asyncio.gather(
            _consume_messages(run, queue, source="subagent", path=path),
            _consume_tools(run, queue, source="subagent", path=path),
            consume_nested(),
        )
        final_status = await _resolve(run.status)
        await queue.put(subagent_event(phase="completed", name=name, path=path, status=final_status))
    except Exception as exc:
        await queue.put(subagent_event(phase="failed", name=name, path=path, status=f"failed: {exc}"))


async def _produce_events(request: StreamRequest, queue: asyncio.Queue[dict[str, Any] | None]) -> None:
    try:
        config = {"configurable": {"thread_id": request.thread_id}} if request.thread_id else None
        run = await graph.astream_events({"messages": request.messages}, config=config, version="v3")
        subagent_tasks: list[asyncio.Task[None]] = []

        async def consume_subagents() -> None:
            async for subagent in run.subagents:
                subagent_tasks.append(asyncio.create_task(_consume_subagent(subagent, queue)))
            if subagent_tasks:
                await asyncio.gather(*subagent_tasks)

        async def consume_raw() -> None:
            async for event in run:
                if not isinstance(event, Mapping):
                    continue
                params = event.get("params") or {}
                if not isinstance(params, Mapping):
                    continue
                await queue.put(
                    raw_event(
                        sequence=event.get("seq"),
                        method=event.get("method", "unknown"),
                        namespace=params.get("namespace", []),
                        data=params.get("data"),
                    )
                )

        async def consume_values() -> None:
            async for snapshot in run.values:
                await queue.put(values_event(snapshot=snapshot))

        async def consume_output() -> None:
            try:
                final_output = await _resolve(run.output)
            except Exception as exc:
                await queue.put(output_event(phase="failed", error=str(exc)))
            else:
                await queue.put(output_event(output=final_output, phase="completed"))

        await asyncio.gather(
            _consume_messages(run, queue, source="coordinator", path=[]),
            _consume_tools(run, queue, source="coordinator", path=[]),
            consume_subagents(),
            consume_values(),
            consume_raw(),
            consume_output(),
        )
    except Exception as exc:
        await queue.put(error_event(message=f"Event stream failed: {exc}"))
    finally:
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
