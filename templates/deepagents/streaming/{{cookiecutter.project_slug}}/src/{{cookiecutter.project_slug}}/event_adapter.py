"""Translate documented v3 projection objects into UI-safe event records."""

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


def subagent_event(*, phase: str, name: Any, path: Any, status: Any) -> dict[str, Any]:
    return {
        "kind": "subagent",
        "phase": phase,
        "name": str(name),
        "path": _path(path),
        "status": str(status),
    }


def tool_event(
    *,
    phase: str,
    source: str,
    path: Any,
    name: Any,
    input_value: Any = None,
    delta: Any = None,
    output: Any = None,
    error: Any = None,
) -> dict[str, Any]:
    return {
        "kind": "tool_call",
        "phase": phase,
        "source": source,
        "path": _path(path),
        "tool_name": str(name),
        "input": _value(input_value),
        "delta": _value(delta),
        "output": _value(output),
        "error": _value(error),
    }


def values_event(*, snapshot: Any) -> dict[str, Any]:
    return {"kind": "values", "snapshot": _value(snapshot)}


def output_event(*, output: Any = None, phase: str | None = None, error: Any = None) -> dict[str, Any]:
    event: dict[str, Any] = {"kind": "output", "output": _value(output)}
    if phase is not None:
        event["phase"] = phase
    if error is not None:
        event["error"] = _value(error)
    return event


def error_event(*, message: Any) -> dict[str, Any]:
    return {"kind": "error", "message": _value(message)}


def raw_event(*, sequence: Any, method: Any, namespace: Any, data: Any) -> dict[str, Any]:
    return {
        "kind": "raw",
        "sequence": sequence,
        "method": str(method),
        "namespace": _path(namespace),
        "data": _value(data),
    }
