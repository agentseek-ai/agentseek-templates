"""Fail-open PowerContext recall middleware for DeepAgents."""

from __future__ import annotations

import os
from contextvars import ContextVar
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.messages import SystemMessage
from powercontext.client import PowerContextClient
from powercontext.http import PrepareContextRequest

_event_sink: ContextVar[Callable[[dict[str, Any]], Awaitable[None]] | None] = ContextVar(
    "powercontext_event_sink", default=None
)


def set_event_sink(sink: Callable[[dict[str, Any]], Awaitable[None]]):
    return _event_sink.set(sink)


def reset_event_sink(token: object) -> None:
    _event_sink.reset(token)  # type: ignore[arg-type]


def _text(message: Any) -> str:
    content = getattr(message, "content", message)
    return content if isinstance(content, str) else str(content)


async def prepare_context(request: ModelRequest) -> tuple[str | None, dict[str, Any]]:
    query = _text(request.messages[-1]) if request.messages else ""
    if not query.strip():
        status = {"status": "skipped", "content_bytes": 0}
        await _publish(status)
        return None, status
    try:
        async with PowerContextClient(os.getenv("POWERCONTEXT_URL", "http://127.0.0.1:8000")) as client:
            result = await client.prepare_context(
                PrepareContextRequest(
                    scope_id=os.getenv("POWERCONTEXT_SCOPE_ID", "project:deepagents"),
                    query=query,
                    max_bytes=int(os.getenv("POWERCONTEXT_MAX_BYTES", "8000")),
                )
            )
        status = str(getattr(result, "status", "empty"))
        content = getattr(result, "content", None)
        context_status = {
            "status": status,
            "content_bytes": int(getattr(result, "content_bytes", 0)),
        }
        await _publish(context_status)
        return content if status == "ready" else None, context_status
    except Exception as exc:  # PowerContext must never block the agent.
        status = {"status": "unavailable", "content_bytes": 0, "detail": str(exc)}
        await _publish(status)
        return None, status


async def _publish(status: dict[str, Any]) -> None:
    sink = _event_sink.get()
    if sink is not None:
        await sink(status)


def _with_context(request: ModelRequest, content: str | None) -> ModelRequest:
    if not content:
        return request
    blocks = list(request.system_message.content_blocks)
    blocks.append({"type": "text", "text": content})
    return request.override(system_message=SystemMessage(content=blocks))


class PowerContextMiddleware(AgentMiddleware):
    """Inject one bounded, cited PreparedContext before each async model call."""

    def wrap_model_call(self, request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]) -> ModelResponse:
        return handler(request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        content, _ = await prepare_context(request)
        return await handler(_with_context(request, content))


powercontext_middleware = PowerContextMiddleware()
