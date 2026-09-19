"""Translate v3 projection objects into the events the browser shows.

The application only surfaces the recalled PowerContext evidence and the
agents' answer, so this module deliberately exposes just those three event
kinds. The v3 protocol projections (raw, values, sub-agent, tool and output)
are not forwarded to the browser.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _path(value: Any) -> list[str]:
    if value is None:
        return []
    return [str(part) for part in value]


def _value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Mapping):
        return {str(key): _value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_value(item) for item in value]
    return str(value)


def message_event(*, source: str, path: Any, text: Any, final: bool = False) -> dict[str, Any]:
    return {
        "kind": "message",
        "source": source,
        "path": _path(path),
        "text": _value(text),
        "final": final,
    }


def error_event(*, message: Any) -> dict[str, Any]:
    return {"kind": "error", "message": _value(message)}


def powercontext_event(
    *,
    status: str,
    content_bytes: int = 0,
    detail: str | None = None,
    max_bytes: int | None = None,
    scope_id: str | None = None,
    content: str | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {"kind": "powercontext", "status": status, "content_bytes": content_bytes}
    if max_bytes is not None:
        event.update(max_bytes=max_bytes, scope_id=scope_id, content=content)
    if detail:
        event["detail"] = detail
    return event
