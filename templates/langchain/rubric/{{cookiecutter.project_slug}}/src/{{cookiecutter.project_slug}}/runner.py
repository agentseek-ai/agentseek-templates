from __future__ import annotations

import contextlib
import json
import os
import selectors
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from .contracts import MAX_CANDIDATE_CHARS, EvidenceResult, candidate_id, normalize_candidate_source

_CHILD_PATH = Path(__file__).with_name("_candidate_runner.py").resolve()
_PROCESS_FACTORY = subprocess.Popen
_TIMEOUT_SECONDS = 2.0
_REAP_TIMEOUT_SECONDS = 0.5
_MAX_OUTPUT_BYTES = 64 * 1024
_READ_CHUNK_BYTES = 8 * 1024
_CHILD_ENV = {
    "PYTHONIOENCODING": "utf-8",
    "RUBRIC_CHILD_PROFILE": "restricted-v1",
}
_CHILD_PROFILE_FAILURES = frozenset(
    {
        "candidate_load",
        "candidate_missing",
        "candidate_signature",
        "child_input",
    }
)
_CASE_NAMES = frozenset({"basic", "empty", "no_duplicates", "unhashable", "repeated_three_times"})


def _result(
    candidate_identifier: str,
    started_at: float,
    *,
    behavior_failures: Sequence[str] = (),
    profile_failures: Sequence[str] = (),
    timed_out: bool = False,
    output_truncated: bool = False,
) -> EvidenceResult:
    behavior = list(behavior_failures)
    profile = list(profile_failures)
    return {
        "candidate_id": candidate_identifier,
        "ok": not behavior and not profile and not timed_out,
        "behavior_failures": behavior,
        "profile_failures": profile,
        "duration_ms": max(0, int((time.monotonic() - started_at) * 1000)),
        "timed_out": timed_out,
        "output_truncated": output_truncated,
    }


def _terminate_and_reap(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=_REAP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=_REAP_TIMEOUT_SECONDS)


def _close_process_pipes(process: subprocess.Popen[bytes]) -> None:
    for pipe in (process.stdin, process.stdout, process.stderr):
        if pipe is not None:
            with contextlib.suppress(OSError):
                pipe.close()


def _drain_process(
    process: subprocess.Popen[bytes],
    request: bytes,
    timeout: float,
) -> tuple[bytes, bytes, bool]:
    if process.stdin is None or process.stdout is None or process.stderr is None:
        raise RuntimeError("child process pipes are required")

    deadline = time.monotonic() + timeout
    try:
        process.stdin.write(request)
        process.stdin.close()
    except BrokenPipeError:
        pass

    stdout = bytearray()
    stderr = bytearray()
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, stdout)
    selector.register(process.stderr, selectors.EVENT_READ, stderr)
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(process.args, timeout)
            events = selector.select(remaining)
            if not events:
                raise subprocess.TimeoutExpired(process.args, timeout)
            for key, _ in events:
                chunk = os.read(key.fd, _READ_CHUNK_BYTES)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                captured = key.data
                available = _MAX_OUTPUT_BYTES - len(captured)
                captured.extend(chunk[:available])
                if len(chunk) > available:
                    return bytes(stdout), bytes(stderr), True

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(process.args, timeout)
        process.wait(timeout=remaining)
        return bytes(stdout), bytes(stderr), False
    finally:
        selector.close()


def _parse_child_result(payload: bytes) -> tuple[list[str], list[str], bool] | None:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or set(value) != {
        "ok",
        "behavior_failures",
        "profile_failures",
        "output_truncated",
    }:
        return None
    behavior = value["behavior_failures"]
    profile = value["profile_failures"]
    if (
        not isinstance(value["ok"], bool)
        or not isinstance(value["output_truncated"], bool)
        or not isinstance(behavior, list)
        or not isinstance(profile, list)
        or any(not isinstance(item, str) or len(item) > 512 for item in behavior)
        or any(not isinstance(item, str) for item in profile)
        or any(item.split(":", maxsplit=1)[0] not in _CASE_NAMES for item in behavior)
        or any(item not in _CHILD_PROFILE_FAILURES for item in profile)
        or bool(value["ok"]) != (not behavior and not profile)
    ):
        return None
    return cast(list[str], behavior), cast(list[str], profile), value["output_truncated"]


def execute_candidate(source: str) -> EvidenceResult:
    """Run the fixed evidence suite in a bounded, restricted child process.

    The child profile reduces accidental capabilities; it is not an operating-system sandbox.
    """
    started_at = time.monotonic()
    normalized = normalize_candidate_source(source)
    identifier = candidate_id(normalized)
    if len(normalized) > MAX_CANDIDATE_CHARS:
        return _result(identifier, started_at, profile_failures=("candidate_too_long",))

    request = json.dumps({"source": normalized}, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    with tempfile.TemporaryDirectory(prefix="rubric-evidence-") as working_directory:
        process = _PROCESS_FACTORY(
            [sys.executable, "-I", str(_CHILD_PATH)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=working_directory,
            env=dict(_CHILD_ENV),
            shell=False,
            start_new_session=False,
        )
        try:
            stdout, stderr, output_truncated = _drain_process(process, request, _TIMEOUT_SECONDS)
            if output_truncated:
                _terminate_and_reap(process)
                return _result(
                    identifier,
                    started_at,
                    profile_failures=("child_protocol",),
                    output_truncated=True,
                )
        except subprocess.TimeoutExpired:
            _terminate_and_reap(process)
            return _result(
                identifier,
                started_at,
                profile_failures=("candidate_timeout",),
                timed_out=True,
            )
        except BaseException:
            _terminate_and_reap(process)
            raise
        finally:
            _close_process_pipes(process)

    if process.returncode != 0:
        return _result(
            identifier,
            started_at,
            profile_failures=("child_exit",),
            output_truncated=output_truncated,
        )

    parsed = _parse_child_result(stdout)
    if parsed is None:
        return _result(
            identifier,
            started_at,
            profile_failures=("child_protocol",),
            output_truncated=output_truncated,
        )
    behavior_failures, profile_failures, child_truncated = parsed
    return _result(
        identifier,
        started_at,
        behavior_failures=behavior_failures,
        profile_failures=profile_failures,
        output_truncated=output_truncated or child_truncated,
    )
