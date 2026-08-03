from __future__ import annotations

import contextlib
import copy
import inspect
import json
import sys
from collections.abc import Callable
from typing import Any

SAFE_BUILTINS = {
    "enumerate": enumerate,
    "len": len,
    "list": list,
    "range": range,
}

CASES = (
    ("basic", [1, 2, 2, 3, 1], [2, 1]),
    ("empty", [], []),
    ("no_duplicates", [1, 2, 3], []),
    ("unhashable", [[1], [1], 2], [[1]]),
    ("repeated_three_times", [1, 1, 1], [1]),
)

_MAX_INPUT_BYTES = 16 * 1024
_MAX_CAPTURE_CHARS = 64 * 1024
_MAX_SUMMARY_ITEMS = 8
_MAX_SUMMARY_DEPTH = 3


class _BoundedTextSink:
    def __init__(self) -> None:
        self.characters = 0
        self.truncated = False

    def write(self, value: str) -> int:
        remaining = _MAX_CAPTURE_CHARS - self.characters
        if len(value) > remaining:
            self.characters = _MAX_CAPTURE_CHARS
            self.truncated = True
        else:
            self.characters += len(value)
        return len(value)

    def flush(self) -> None:
        return None


def _profile_failure(code: str, *, output_truncated: bool = False) -> dict[str, object]:
    return {
        "ok": False,
        "behavior_failures": [],
        "profile_failures": [code],
        "output_truncated": output_truncated,
    }


def _read_request() -> dict[str, object] | None:
    raw = sys.stdin.buffer.read(_MAX_INPUT_BYTES + 1)
    if len(raw) > _MAX_INPUT_BYTES:
        return None
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or set(value) != {"source"}:
        return None
    return value


def _load_candidate(source: str, sink: _BoundedTextSink) -> tuple[Callable[[list[Any]], object] | None, str | None]:
    namespace: dict[str, object] = {"__builtins__": dict(SAFE_BUILTINS)}
    try:
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            exec(compile(source, "<candidate>", "exec"), namespace, namespace)
    except BaseException:
        return None, "candidate_load"

    candidate = namespace.get("find_duplicates")
    if not callable(candidate):
        return None, "candidate_missing"
    try:
        parameters = tuple(inspect.signature(candidate).parameters.values())
    except (TypeError, ValueError):
        return None, "candidate_signature"
    if (
        len(parameters) != 1
        or parameters[0].name != "values"
        or parameters[0].kind not in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ):
        return None, "candidate_signature"
    return candidate, None


def _summarize(value: object, *, depth: int = 0) -> tuple[str, bool]:
    if value is None or isinstance(value, bool):
        return repr(value), False
    if isinstance(value, int):
        bit_length = value.bit_length()
        if bit_length > 256:
            return f"<int bits={bit_length}>", True
        return repr(value), False
    if isinstance(value, float):
        return repr(value), False
    if isinstance(value, str):
        return f"<str len={len(value)}>", len(value) > 256
    if isinstance(value, list):
        if depth >= _MAX_SUMMARY_DEPTH:
            return "<list>", bool(value)
        parts: list[str] = []
        truncated = len(value) > _MAX_SUMMARY_ITEMS
        for item in value[:_MAX_SUMMARY_ITEMS]:
            summary, item_truncated = _summarize(item, depth=depth + 1)
            parts.append(summary)
            truncated = truncated or item_truncated
        suffix = ", ..." if len(value) > _MAX_SUMMARY_ITEMS else ""
        return f"[{', '.join(parts)}{suffix}]", truncated
    return "<unsupported>", True


def _run_cases(candidate: Callable[[list[Any]], object], sink: _BoundedTextSink) -> dict[str, object]:
    behavior_failures: list[str] = []
    output_truncated = False
    for name, case_input, expected in CASES:
        values = copy.deepcopy(case_input)
        snapshot = copy.deepcopy(values)
        snapshot_bytes = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        try:
            with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                actual = candidate(values)
            try:
                matches = actual == expected
            except BaseException:
                matches = False
            if matches is not True:
                expected_summary, expected_truncated = _summarize(expected)
                actual_summary, actual_truncated = _summarize(actual)
                output_truncated = output_truncated or expected_truncated or actual_truncated
                behavior_failures.append(f"{name}: expected {expected_summary}; got {actual_summary}")
        except BaseException:
            behavior_failures.append(f"{name}: execution failed")

        try:
            current_bytes = json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            unchanged = values == snapshot and current_bytes == snapshot_bytes
        except BaseException:
            unchanged = False
        if not unchanged:
            behavior_failures.append(f"{name}: input mutated")

    output_truncated = output_truncated or sink.truncated
    return {
        "ok": not behavior_failures,
        "behavior_failures": behavior_failures,
        "profile_failures": [],
        "output_truncated": output_truncated,
    }


def main() -> None:
    request = _read_request()
    if request is None or not isinstance(request.get("source"), str):
        result = _profile_failure("child_input")
    else:
        sink = _BoundedTextSink()
        candidate, failure = _load_candidate(request["source"], sink)
        if failure is not None or candidate is None:
            result = _profile_failure(failure or "candidate_load", output_truncated=sink.truncated)
        else:
            result = _run_cases(candidate, sink)
    sys.stdout.write(json.dumps(result, ensure_ascii=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
