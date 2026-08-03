from __future__ import annotations

import contextlib
import json
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Iterator, Sequence
from contextvars import ContextVar
from pathlib import Path
from typing import BinaryIO, cast

from .contracts import MAX_CANDIDATE_CHARS, EvidenceResult, candidate_id, normalize_candidate_source

_CHILD_PATH = Path(__file__).with_name("_candidate_runner.py").resolve()
_PROCESS_FACTORY = subprocess.Popen
_TIMEOUT_SECONDS = 2.0
_REAP_TIMEOUT_SECONDS = 0.5
_MAX_OUTPUT_BYTES = 64 * 1024
_MAX_COMBINED_OUTPUT_BYTES = 64 * 1024
_READ_CHUNK_BYTES = 8 * 1024
_PROCESS_POLL_SECONDS = 0.01
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
_CANCELLATION_EVENT: ContextVar[threading.Event | None] = ContextVar(
    "rubric_candidate_cancellation_event",
    default=None,
)


class CandidateExecutionCancelled(BaseException):
    """Stop one owned candidate process without turning cancellation into Evidence."""


@contextlib.contextmanager
def candidate_cancellation_scope(event: threading.Event) -> Iterator[None]:
    """Bind an async tool's cancellation signal to its worker-thread execution."""
    token = _CANCELLATION_EVENT.set(event)
    try:
        yield
    finally:
        _CANCELLATION_EVENT.reset(token)


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
    cancellation_event: threading.Event | None = None,
) -> tuple[bytes, bytes, bool]:
    if process.stdin is None or process.stdout is None or process.stderr is None:
        raise RuntimeError("child process pipes are required")

    deadline = time.monotonic() + timeout
    stdout = bytearray()
    stderr = bytearray()
    capture_lock = threading.Lock()
    output_limit_reached = threading.Event()
    reader_failed = threading.Event()
    combined_bytes = 0

    def read_pipe(pipe: BinaryIO, captured: bytearray) -> None:
        nonlocal combined_bytes
        try:
            while not output_limit_reached.is_set():
                chunk = pipe.read1(_READ_CHUNK_BYTES)
                if not chunk:
                    return
                with capture_lock:
                    available = min(
                        _MAX_OUTPUT_BYTES - len(captured),
                        _MAX_COMBINED_OUTPUT_BYTES - combined_bytes,
                    )
                    stored = chunk[:available]
                    captured.extend(stored)
                    combined_bytes += len(stored)
                    exceeded = len(chunk) > available
                if exceeded:
                    output_limit_reached.set()
                    return
        except (OSError, ValueError):
            reader_failed.set()

    readers = (
        threading.Thread(target=read_pipe, args=(process.stdout, stdout), name="rubric-stdout-reader"),
        threading.Thread(target=read_pipe, args=(process.stderr, stderr), name="rubric-stderr-reader"),
    )
    for reader in readers:
        reader.start()

    try:
        try:
            process.stdin.write(request)
            process.stdin.close()
        except BrokenPipeError:
            pass
        while process.poll() is None:
            if cancellation_event is not None and cancellation_event.is_set():
                raise CandidateExecutionCancelled
            if output_limit_reached.is_set() or reader_failed.is_set():
                _terminate_and_reap(process)
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(process.args, timeout)
            output_limit_reached.wait(min(_PROCESS_POLL_SECONDS, remaining))
    except BaseException:
        _terminate_and_reap(process)
        raise
    finally:
        for reader in readers:
            reader.join(timeout=_REAP_TIMEOUT_SECONDS)
        if any(reader.is_alive() for reader in readers):
            _close_process_pipes(process)
            for reader in readers:
                reader.join(timeout=_REAP_TIMEOUT_SECONDS)

    if any(reader.is_alive() for reader in readers):
        raise RuntimeError("child output readers did not stop")
    return bytes(stdout), bytes(stderr), output_limit_reached.is_set()


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
    cancellation_event = _CANCELLATION_EVENT.get()
    if cancellation_event is not None and cancellation_event.is_set():
        raise CandidateExecutionCancelled
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
            stdout, stderr, output_truncated = _drain_process(
                process,
                request,
                _TIMEOUT_SECONDS,
                cancellation_event,
            )
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
