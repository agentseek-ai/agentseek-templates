from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import zipfile
from pathlib import Path

import pytest
import yaml

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "generated_runtime_smoke.py"
SPEC = importlib.util.spec_from_file_location("generated_runtime_smoke", SCRIPT)
assert SPEC and SPEC.loader
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)

FAKE_PROVIDER_SCRIPT = SCRIPT.with_name("fake_openai_server.py")
FAKE_PROVIDER_SPEC = importlib.util.spec_from_file_location("fake_openai_server", FAKE_PROVIDER_SCRIPT)
assert FAKE_PROVIDER_SPEC and FAKE_PROVIDER_SPEC.loader
fake_provider = importlib.util.module_from_spec(FAKE_PROVIDER_SPEC)
FAKE_PROVIDER_SPEC.loader.exec_module(fake_provider)


def _load_windows_job_wrapper():
    script = SCRIPT.with_name("windows_job_wrapper.py")
    assert script.is_file()
    spec = importlib.util.spec_from_file_location("windows_job_wrapper", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        ([], ("127.0.0.1", 2025)),
        (["--host", "127.0.0.1", "--port", "43125"], ("127.0.0.1", 43125)),
    ],
)
def test_fake_provider_address_defaults_and_explicit_override(
    argv: list[str],
    expected: tuple[str, int],
) -> None:
    args = fake_provider._parse_args(argv)

    assert (args.host, args.port) == expected


def _assert_no_workflow_secrets(value: object) -> None:
    if isinstance(value, str):
        assert "secrets." not in value
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _assert_no_workflow_secrets(key)
            _assert_no_workflow_secrets(item)
        return
    if isinstance(value, list):
        for item in value:
            _assert_no_workflow_secrets(item)


class _Process:
    pid = 1234

    def __init__(self, *, returncode: int | None = None) -> None:
        self.returncode = returncode
        self.kill_calls = 0
        self.poll_calls = 0
        self.wait_calls = 0
        self.wait_timeouts: list[float] = []

    def poll(self) -> int | None:
        self.poll_calls += 1
        return self.returncode

    def wait(self, *, timeout: float) -> int:
        self.wait_calls += 1
        self.wait_timeouts.append(timeout)
        self.returncode = 0
        return 0

    def kill(self) -> None:
        self.kill_calls += 1
        self.returncode = -9


def test_terminate_ignores_process_group_race(monkeypatch: pytest.MonkeyPatch) -> None:
    process = _Process()

    def missing_process_group(pid: int, sig: int) -> None:
        assert pid == process.pid
        assert sig == smoke.signal.SIGTERM
        raise ProcessLookupError

    monkeypatch.setattr(smoke.os, "name", "posix")
    monkeypatch.setattr(smoke.os, "killpg", missing_process_group)

    smoke._terminate(process)

    assert process.wait_calls == 1


def test_terminate_signals_owned_group_when_leader_already_exited(monkeypatch: pytest.MonkeyPatch) -> None:
    process = _Process(returncode=0)
    signals: list[int] = []

    def kill_group(pid: int, sig: int) -> None:
        assert pid == process.pid
        signals.append(sig)
        if sig == 0:
            raise ProcessLookupError

    monkeypatch.setattr(smoke.os, "name", "posix")
    monkeypatch.setattr(smoke.os, "killpg", kill_group)

    smoke._terminate(process)

    assert signals == [smoke.signal.SIGTERM, 0]
    assert process.wait_calls == 0


def test_posix_group_check_treats_permission_denied_as_no_owned_members(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = _Process(returncode=0)

    def deny_group_check(_pid: int, sig: int) -> None:
        assert sig == 0
        raise PermissionError

    monkeypatch.setattr(smoke.os, "killpg", deny_group_check)

    assert smoke._wait_for_posix_group_exit(process, 1) is True
    assert process.poll_calls == 1


def test_posix_group_check_retries_permission_denied_until_leader_is_reaped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = _Process()

    def poll_until_reaped() -> int | None:
        process.poll_calls += 1
        if process.poll_calls == 1:
            return None
        process.returncode = 0
        return 0

    def deny_group_check(_pid: int, _sig: int) -> None:
        raise PermissionError

    process.poll = poll_until_reaped  # type: ignore[method-assign]
    monkeypatch.setattr(smoke.os, "killpg", deny_group_check)

    assert smoke._wait_for_posix_group_exit(process, 1) is True
    assert process.poll_calls == 2


def test_posix_group_check_reaps_zombie_leader_before_testing_descendants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = _Process()
    reaped = False

    def reap_leader() -> int:
        nonlocal reaped
        process.poll_calls += 1
        process.returncode = 0
        reaped = True
        return 0

    def check_group(_pid: int, sig: int) -> None:
        assert sig == 0
        if reaped:
            raise ProcessLookupError

    process.poll = reap_leader  # type: ignore[method-assign]
    monkeypatch.setattr(smoke.os, "killpg", check_group)

    assert smoke._wait_for_posix_group_exit(process, 1) is True
    assert process.poll_calls == 1


def test_terminate_allows_launcher_to_clean_nested_process_groups(monkeypatch: pytest.MonkeyPatch) -> None:
    process = _Process()
    wait_timeouts: list[float] = []
    monkeypatch.setattr(smoke.os, "name", "posix")
    monkeypatch.setattr(smoke.os, "killpg", lambda *_args: None)
    monkeypatch.setattr(
        smoke,
        "_wait_for_posix_group_exit",
        lambda _pid, timeout: wait_timeouts.append(timeout) or True,
        raising=False,
    )

    smoke._terminate(process)

    assert wait_timeouts[0] >= 30


def test_terminate_force_kills_entire_posix_group_after_grace(monkeypatch: pytest.MonkeyPatch) -> None:
    process = _Process()
    signals: list[tuple[int, int]] = []
    wait_timeouts: list[float] = []
    monkeypatch.setattr(smoke.os, "name", "posix")
    monkeypatch.setattr(smoke.os, "killpg", lambda pid, sig: signals.append((pid, sig)))
    monkeypatch.setattr(
        smoke,
        "_wait_for_posix_group_exit",
        lambda _pid, timeout: wait_timeouts.append(timeout) or len(wait_timeouts) == 2,
        raising=False,
    )

    smoke._terminate(process)

    assert signals == [
        (process.pid, smoke.signal.SIGTERM),
        (process.pid, smoke.signal.SIGKILL),
    ]
    assert wait_timeouts[0] >= 30
    assert wait_timeouts[1] <= 10
    assert process.kill_calls == 0


def test_windows_cleanup_uses_absolute_system_taskkill_with_minimal_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    system_root = tmp_path / "Windows"
    taskkill = system_root / "System32" / "taskkill.exe"
    taskkill.parent.mkdir(parents=True)
    taskkill.touch()
    process = _Process()
    recorded: dict[str, object] = {}

    def run(command: list[str], **kwargs: object) -> smoke.subprocess.CompletedProcess[bytes]:
        recorded.update(command=command, **kwargs)
        return smoke.subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(smoke.subprocess, "run", run)
    monkeypatch.setattr(
        smoke.runtime_proof,
        "resolve_executable",
        lambda _name: pytest.fail("cleanup must not search ambient PATH"),
    )

    smoke._terminate_windows_process(
        process,
        {
            "SystemRoot": str(system_root),
            "PATH": str(tmp_path / "hostile-bin"),
            "SMOKE_SECRET": "must-not-propagate",
        },
    )

    assert recorded["command"] == [str(taskkill.resolve()), "/PID", str(process.pid), "/T", "/F"]
    assert recorded["env"] == {"SystemRoot": str(system_root)}
    assert recorded["timeout"] == smoke.WINDOWS_TASKKILL_TIMEOUT_SECONDS
    assert recorded["check"] is False


def test_windows_cleanup_reaps_leader_when_taskkill_validation_fails(tmp_path: Path) -> None:
    system_root = tmp_path / "Windows"
    system_root.mkdir()
    process = _Process()

    with pytest.raises(RuntimeError, match=smoke.WINDOWS_TREE_CLEANUP_ERROR):
        smoke._terminate_windows_process(process, {"SystemRoot": str(system_root)})

    assert process.kill_calls == 1
    assert process.wait_calls == 1


def test_windows_cleanup_fails_closed_when_leader_already_exited(tmp_path: Path) -> None:
    system_root = tmp_path / "Windows"
    taskkill = system_root / "System32" / "taskkill.exe"
    taskkill.parent.mkdir(parents=True)
    taskkill.touch()
    process = _Process(returncode=1)

    with pytest.raises(RuntimeError, match=smoke.WINDOWS_TREE_CLEANUP_ERROR):
        smoke._terminate_windows_process(process, {"SystemRoot": str(system_root)})


def test_windows_cleanup_accepts_exited_owned_wrapper_with_empty_job_marker(
    tmp_path: Path,
) -> None:
    process = _Process(returncode=0)
    nonce = "8fdd06df7fc44f4cb34cc976943bf9437793a196830005dc9858d438b9ea67cb"
    marker = tmp_path / "owned-tree-empty.json"
    marker.write_text(
        json.dumps(
            {
                "nonce": nonce,
                "owner_pid": process.pid,
                "schema_version": 1,
                "status": "empty",
            }
        ),
        encoding="utf-8",
    )
    process._agentseek_windows_empty_tree_marker = str(marker)  # type: ignore[attr-defined]
    process._agentseek_windows_empty_tree_nonce = nonce  # type: ignore[attr-defined]

    smoke._terminate_windows_process(process, {})

    assert process.poll_calls == 1
    assert process.kill_calls == 0
    assert process.wait_calls == 0


def test_windows_cleanup_accepts_nonce_bound_marker_from_child_interpreter(
    tmp_path: Path,
) -> None:
    process = _Process(returncode=0)
    nonce = "8fdd06df7fc44f4cb34cc976943bf9437793a196830005dc9858d438b9ea67cb"
    marker = tmp_path / "owned-tree-empty.json"
    marker.write_text(
        json.dumps(
            {
                "nonce": nonce,
                "owner_pid": process.pid + 1,
                "schema_version": 1,
                "status": "empty",
            }
        ),
        encoding="utf-8",
    )
    process._agentseek_windows_empty_tree_marker = str(marker)  # type: ignore[attr-defined]
    process._agentseek_windows_empty_tree_nonce = nonce  # type: ignore[attr-defined]

    smoke._terminate_windows_process(process, {})


def test_windows_cleanup_rejects_forged_marker_without_parent_nonce(
    tmp_path: Path,
) -> None:
    process = _Process(returncode=0)
    marker_nonce = "a" * 64
    parent_nonce = "b" * 64
    marker = tmp_path / "owned-tree-empty.json"
    marker.write_text(
        json.dumps(
            {
                "nonce": marker_nonce,
                "owner_pid": process.pid,
                "schema_version": 1,
                "status": "empty",
            }
        ),
        encoding="utf-8",
    )
    process._agentseek_windows_empty_tree_marker = str(marker)  # type: ignore[attr-defined]
    process._agentseek_windows_empty_tree_nonce = parent_nonce  # type: ignore[attr-defined]

    with pytest.raises(RuntimeError, match=smoke.WINDOWS_TREE_CLEANUP_ERROR):
        smoke._terminate_windows_process(process, {})


def test_windows_cleanup_rejects_matching_noncryptographic_marker_nonce(
    tmp_path: Path,
) -> None:
    process = _Process(returncode=0)
    nonce = "forged"
    marker = tmp_path / "owned-tree-empty.json"
    marker.write_text(
        json.dumps(
            {
                "nonce": nonce,
                "owner_pid": process.pid,
                "schema_version": 1,
                "status": "empty",
            }
        ),
        encoding="utf-8",
    )
    process._agentseek_windows_empty_tree_marker = str(marker)  # type: ignore[attr-defined]
    process._agentseek_windows_empty_tree_nonce = nonce  # type: ignore[attr-defined]

    with pytest.raises(RuntimeError, match=smoke.WINDOWS_TREE_CLEANUP_ERROR):
        smoke._terminate_windows_process(process, {})


def test_windows_cleanup_requests_owned_wrapper_shutdown_without_taskkill(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    process = _Process()
    nonce = "8fdd06df7fc44f4cb34cc976943bf9437793a196830005dc9858d438b9ea67cb"
    marker = tmp_path / "owned-tree-empty.json"
    process._agentseek_windows_empty_tree_marker = str(marker)  # type: ignore[attr-defined]
    process._agentseek_windows_empty_tree_nonce = nonce  # type: ignore[attr-defined]

    def wait(*, timeout: float) -> int:
        process.wait_timeouts.append(timeout)
        request = smoke._windows_cleanup_request_path(marker)
        assert request.read_bytes() == b"cleanup\n"
        marker.write_text(
            json.dumps(
                {
                    "nonce": nonce,
                    "owner_pid": process.pid,
                    "schema_version": 1,
                    "status": "empty",
                }
            ),
            encoding="utf-8",
        )
        process.returncode = 0
        return 0

    process.wait = wait  # type: ignore[method-assign]
    process.send_signal = lambda _signum: pytest.fail("cleanup must not depend on console signals")  # type: ignore[attr-defined]
    monkeypatch.setattr(
        smoke.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("owned wrappers must not use taskkill"),
    )

    smoke._terminate_windows_process(process, {})

    assert process.kill_calls == 0
    assert process.wait_timeouts == [smoke.LAUNCHER_SHUTDOWN_TIMEOUT_SECONDS]


def test_windows_cleanup_fails_closed_when_owned_wrapper_cannot_confirm_shutdown(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    process = _Process()
    process._agentseek_windows_empty_tree_marker = str(tmp_path / "missing.json")  # type: ignore[attr-defined]
    process._agentseek_windows_empty_tree_nonce = "a" * 64  # type: ignore[attr-defined]
    wrapper_log = tmp_path / "wrapper.log"
    wrapper_log.write_text("wrapper-stage=job-finalization secret-value\n", encoding="utf-8")
    process._agentseek_log_path = str(wrapper_log)  # type: ignore[attr-defined]
    process._agentseek_environment = {"API_KEY": "secret-value"}  # type: ignore[attr-defined]
    process.args = ["fixed-command"]  # type: ignore[attr-defined]

    def wait(*, timeout: float) -> int:
        process.wait_timeouts.append(timeout)
        if timeout == smoke.LAUNCHER_SHUTDOWN_TIMEOUT_SECONDS:
            raise subprocess.TimeoutExpired("wrapper", timeout)
        process.returncode = -9
        return -9

    process.wait = wait  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match=smoke.WINDOWS_TREE_CLEANUP_ERROR) as captured:
        smoke._terminate_windows_process(process, {})

    assert process.kill_calls == 1
    assert process.wait_timeouts == [
        smoke.LAUNCHER_SHUTDOWN_TIMEOUT_SECONDS,
        smoke.FORCE_SHUTDOWN_TIMEOUT_SECONDS,
    ]
    assert captured.value.__notes__ == [
        "Windows cleanup diagnostic: request-pending, wrapper-timeout, marker-missing.",
        "Windows wrapper log tail (redacted):\nwrapper-stage=job-finalization <redacted>\n",
    ]
    assert "secret-value" not in "\n".join(captured.value.__notes__)


def test_windows_cleanup_reports_value_free_invalid_marker_reason(
    tmp_path: Path,
) -> None:
    process = _Process()
    nonce = "8fdd06df7fc44f4cb34cc976943bf9437793a196830005dc9858d438b9ea67cb"
    marker = tmp_path / "owned-tree-empty.json"
    process._agentseek_windows_empty_tree_marker = str(marker)  # type: ignore[attr-defined]
    process._agentseek_windows_empty_tree_nonce = nonce  # type: ignore[attr-defined]
    process.args = ["fixed-command"]  # type: ignore[attr-defined]

    def wait(*, timeout: float) -> int:
        assert timeout == smoke.LAUNCHER_SHUTDOWN_TIMEOUT_SECONDS
        smoke._windows_cleanup_request_path(marker).unlink()
        marker.write_text(
            json.dumps(
                {
                    "nonce": nonce,
                    "owner_pid": 0,
                    "schema_version": 1,
                    "status": "empty",
                }
            ),
            encoding="utf-8",
        )
        process.returncode = 0
        return 0

    process.wait = wait  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match=smoke.WINDOWS_TREE_CLEANUP_ERROR) as captured:
        smoke._terminate_windows_process(process, {})

    assert captured.value.__notes__[0] == (
        "Windows cleanup diagnostic: request-consumed, wrapper-exit-zero, marker-owner-invalid."
    )
    assert nonce not in "\n".join(captured.value.__notes__)


def test_windows_job_wrapper_request_interrupts_wait_and_empties_job(
    tmp_path: Path,
) -> None:
    wrapper = _load_windows_job_wrapper()
    marker = tmp_path / "owned-tree-empty.json"
    request = wrapper._cleanup_request_path(marker)
    request.write_bytes(b"cleanup\n")
    child_exited = threading.Event()
    events: list[object] = []

    class Child:
        def wait(self) -> int:
            events.append("wait")
            assert child_exited.wait(timeout=1)
            return 1

        def close_remaining_tree(self, *, timeout: float) -> None:
            events.append(("unexpected-close-remaining-tree", timeout))

        def ensure_closed(self, *, timeout: float) -> None:
            events.append(("ensure-closed", timeout))

        def terminate_and_reap(self, *, timeout: float) -> None:
            events.append(("terminate-and-reap", timeout))
            child_exited.set()

        def close(self) -> None:
            events.append("close")

    class Supervisor:
        @staticmethod
        def start(command: list[str], *, env: dict[str, str], cwd: str):
            del command, env, cwd
            return Child()

    exit_code = wrapper.run_owned_command(
        ["child"],
        marker=marker,
        nonce_stream=io.BytesIO(("a" * 64 + "\n").encode()),
        environment={},
        cwd=r"C:\runtime",
        supervisor_type=Supervisor,
        owner_pid=4321,
    )

    assert exit_code == 0
    assert events == [
        "wait",
        ("terminate-and-reap", wrapper.JOB_CLEANUP_TIMEOUT_SECONDS),
        ("ensure-closed", wrapper.JOB_CLEANUP_TIMEOUT_SECONDS),
        "close",
    ]
    assert not request.exists()


def test_windows_job_wrapper_marks_empty_tree_after_nonzero_child_exit(
    tmp_path: Path,
) -> None:
    wrapper = _load_windows_job_wrapper()
    marker = tmp_path / "owned-tree-empty.json"
    nonce = "8fdd06df7fc44f4cb34cc976943bf9437793a196830005dc9858d438b9ea67cb"
    nonce_stream = io.BytesIO(f"{nonce}\n".encode())
    events: list[object] = []

    class Child:
        def wait(self) -> int:
            events.append("wait")
            return 17

        def close_remaining_tree(self, *, timeout: float) -> None:
            events.append(("close-remaining-tree", timeout))

        def ensure_closed(self, *, timeout: float) -> None:
            events.append(("ensure-closed", timeout))

        def terminate_and_reap(self, *, timeout: float) -> None:
            events.append(("terminate-and-reap", timeout))

        def close(self) -> None:
            events.append("close")

    class Supervisor:
        @staticmethod
        def start(command: list[str], *, env: dict[str, str], cwd: str):
            assert nonce_stream.read(1) == b""
            events.append(("start", command, env, cwd))
            return Child()

    exit_code = wrapper.run_owned_command(
        [r"C:\runtime\child.exe", "--serve"],
        marker=marker,
        nonce_stream=nonce_stream,
        environment={"SAFE": "1"},
        cwd=r"C:\runtime",
        supervisor_type=Supervisor,
        owner_pid=4321,
    )

    assert exit_code == 17
    assert events == [
        (
            "start",
            [r"C:\runtime\child.exe", "--serve"],
            {"SAFE": "1"},
            r"C:\runtime",
        ),
        "wait",
        ("close-remaining-tree", wrapper.JOB_CLEANUP_TIMEOUT_SECONDS),
        ("ensure-closed", wrapper.JOB_CLEANUP_TIMEOUT_SECONDS),
        "close",
    ]
    assert json.loads(marker.read_text(encoding="utf-8")) == {
        "nonce": nonce,
        "owner_pid": 4321,
        "schema_version": 1,
        "status": "empty",
    }
    if os.name != "nt":
        assert marker.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "failure_stage",
    ["close_remaining_tree", "ensure_closed", "close"],
)
def test_windows_job_wrapper_withholds_marker_when_job_emptiness_is_unknown(
    tmp_path: Path,
    failure_stage: str,
) -> None:
    wrapper = _load_windows_job_wrapper()
    marker = tmp_path / "owned-tree-empty.json"

    class Child:
        def wait(self) -> int:
            return 0

        def close_remaining_tree(self, *, timeout: float) -> None:
            if failure_stage == "close_remaining_tree":
                raise RuntimeError(f"close_remaining_tree failed after {timeout}")

        def ensure_closed(self, *, timeout: float) -> None:
            if failure_stage == "ensure_closed":
                raise RuntimeError(f"ensure_closed failed after {timeout}")

        def terminate_and_reap(self, *, timeout: float) -> None:
            del timeout

        def close(self) -> None:
            if failure_stage == "close":
                raise RuntimeError("close failed")

    class Supervisor:
        @staticmethod
        def start(command: list[str], *, env: dict[str, str], cwd: str):
            del command, env, cwd
            return Child()

    with pytest.raises(RuntimeError, match=failure_stage):
        wrapper.run_owned_command(
            ["child"],
            marker=marker,
            nonce_stream=io.BytesIO(b"8fdd06df7fc44f4cb34cc976943bf9437793a196830005dc9858d438b9ea67cb\n"),
            environment={},
            cwd=r"C:\runtime",
            supervisor_type=Supervisor,
            owner_pid=4321,
        )

    assert not marker.exists()


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"a" * 63 + b"\n",
        b"a" * 64,
        b"A" * 64 + b"\n",
        b"g" * 64 + b"\n",
        b"a" * 32 + b"\n" + b"a" * 32 + b"\n",
        b"a" * 64 + b"\nextra",
    ],
    ids=[
        "missing",
        "short",
        "no-newline",
        "uppercase",
        "non-hex",
        "embedded-newline",
        "extra",
    ],
)
def test_windows_job_wrapper_rejects_invalid_nonce_input_before_child_spawn(
    tmp_path: Path,
    payload: bytes,
) -> None:
    wrapper = _load_windows_job_wrapper()
    marker = tmp_path / "owned-tree-empty.json"

    class Supervisor:
        @staticmethod
        def start(command: list[str], *, env: dict[str, str], cwd: str):
            del command, env, cwd
            pytest.fail("invalid nonce input must be rejected before child spawn")

    with pytest.raises(RuntimeError, match="nonce input"):
        wrapper.run_owned_command(
            ["child"],
            marker=marker,
            nonce_stream=io.BytesIO(payload),
            environment={},
            cwd=r"C:\runtime",
            supervisor_type=Supervisor,
            owner_pid=4321,
        )

    assert not marker.exists()


@pytest.mark.parametrize("taskkill_result", [1, subprocess.TimeoutExpired("taskkill", 1)])
def test_windows_cleanup_fails_closed_when_taskkill_cannot_prove_tree_exit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    taskkill_result: int | subprocess.TimeoutExpired,
) -> None:
    system_root = tmp_path / "Windows"
    taskkill = system_root / "System32" / "taskkill.exe"
    taskkill.parent.mkdir(parents=True)
    taskkill.touch()
    process = _Process()

    def run(command: list[str], **_kwargs: object) -> smoke.subprocess.CompletedProcess[bytes]:
        if isinstance(taskkill_result, BaseException):
            raise taskkill_result
        return smoke.subprocess.CompletedProcess(command, taskkill_result)

    monkeypatch.setattr(smoke.subprocess, "run", run)

    with pytest.raises(RuntimeError, match=smoke.WINDOWS_TREE_CLEANUP_ERROR):
        smoke._terminate_windows_process(process, {"SystemRoot": str(system_root)})

    assert process.kill_calls == 1
    assert process.wait_calls == 1


def test_process_cleanup_attempts_provider_after_lifecycle_error(monkeypatch: pytest.MonkeyPatch) -> None:
    lifecycle = _Process()
    provider = _Process()
    attempted: list[_Process] = []

    def terminate(process: _Process, **_kwargs: object) -> None:
        attempted.append(process)
        if process is lifecycle:
            raise RuntimeError("lifecycle cleanup failed")

    monkeypatch.setattr(smoke, "_terminate", terminate)

    with pytest.raises(RuntimeError, match="lifecycle cleanup failed"):
        smoke._terminate_processes(lifecycle, provider)

    assert attempted == [lifecycle, provider]


def test_runtime_startup_error_remains_primary_when_exited_windows_leader_cleanup_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    system_root = tmp_path / "Windows"
    taskkill = system_root / "System32" / "taskkill.exe"
    taskkill.parent.mkdir(parents=True)
    taskkill.touch()
    environment = {"SystemRoot": str(system_root)}
    process = _Process(returncode=1)

    def terminate(process_to_stop: _Process, **kwargs: object) -> None:
        smoke._terminate_windows_process(
            process_to_stop,
            kwargs["cleanup_environment"],  # type: ignore[arg-type]
        )

    monkeypatch.setattr(smoke, "_terminate", terminate)
    startup_error = RuntimeError("runtime startup failed")

    with pytest.raises(RuntimeError) as exc_info, smoke._managed_runtime_processes(environment) as resources:
        resources.lifecycle = process
        raise startup_error

    assert exc_info.value is startup_error
    assert startup_error.args == ("runtime startup failed",)
    assert str(startup_error) == "runtime startup failed"
    assert traceback.extract_tb(startup_error.__traceback__)[-1].name == (
        "test_runtime_startup_error_remains_primary_when_exited_windows_leader_cleanup_fails"
    )
    assert startup_error.__notes__ == [smoke.SECONDARY_CLEANUP_NOTE]


def test_exited_windows_leader_cleanup_failure_blocks_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    system_root = tmp_path / "Windows"
    taskkill = system_root / "System32" / "taskkill.exe"
    taskkill.parent.mkdir(parents=True)
    taskkill.touch()
    environment = {"SystemRoot": str(system_root)}
    process = _Process(returncode=1)

    def terminate(process_to_stop: _Process, **kwargs: object) -> None:
        smoke._terminate_windows_process(
            process_to_stop,
            kwargs["cleanup_environment"],  # type: ignore[arg-type]
        )

    monkeypatch.setattr(smoke, "_terminate", terminate)

    with (
        pytest.raises(RuntimeError, match=smoke.WINDOWS_TREE_CLEANUP_ERROR),
        smoke._managed_runtime_processes(environment) as resources,
    ):
        resources.lifecycle = process


def test_runtime_error_is_not_masked_by_stream_close_failure() -> None:
    class FailingStream:
        def close(self) -> None:
            raise RuntimeError("stream close failed")

    startup_error = RuntimeError("runtime startup failed")

    with pytest.raises(RuntimeError) as exc_info, smoke._managed_runtime_processes({}) as resources:
        resources.lifecycle_stream = FailingStream()
        raise startup_error

    assert exc_info.value is startup_error
    assert str(startup_error) == "runtime startup failed"
    assert traceback.extract_tb(startup_error.__traceback__)[-1].name == (
        "test_runtime_error_is_not_masked_by_stream_close_failure"
    )
    assert startup_error.__notes__ == [smoke.SECONDARY_CLEANUP_NOTE]


def test_read_log_redacts_process_environment_and_argv(tmp_path: Path) -> None:
    proxy = "https://alice:real-secret@proxy.example:8443"
    log_path = tmp_path / "runtime.log"
    script = """
import os
import sys

print("noise" * 3000)
print(os.environ["HTTPS_PROXY"])
print("alice")
print("real-secret")
print(f"prefix{os.environ['SHORT_SECRET']}suffix")
print(sys.argv[1])
"""
    process, stream = smoke._start_process(
        [sys.executable, "-c", script, "argv-secret"],
        cwd=tmp_path,
        env={**os.environ, "HTTPS_PROXY": proxy, "SHORT_SECRET": "abc"},
        log_path=log_path,
    )
    try:
        assert process.wait(timeout=5) == 0
    finally:
        stream.close()

    diagnostic = smoke._read_log(process)

    assert "<redacted>" in diagnostic
    for secret in (proxy, "alice", "real-secret", "abc", "argv-secret"):
        assert secret not in diagnostic
    assert len(diagnostic) <= smoke.COMMAND_OUTPUT_TAIL_BYTES


def test_windows_start_process_uses_private_job_wrapper_without_child_nonce_leak(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    supervisor_python = tmp_path / "child" / "Scripts" / "python.exe"
    supervisor_python.parent.mkdir(parents=True)
    supervisor_python.touch()
    log_path = tmp_path / "run" / "logs" / "runtime.log"
    log_path.parent.mkdir(parents=True)
    nonce = "8fdd06df7fc44f4cb34cc976943bf9437793a196830005dc9858d438b9ea67cb"
    marker_id = "c5a84da0de9e4561af4c489cad802d63"
    marker = log_path.with_name(f".{log_path.name}.{marker_id}.tree-empty.json")
    child_command = [r"C:\runtime\agentseek.exe", "dev", "--skip-check"]
    child_environment = {"SAFE": "1"}
    recorded: dict[str, object] = {}
    nonce_writes: list[object] = []

    class SecretSource:
        @staticmethod
        def token_hex(size: int) -> str:
            if size == 16:
                return marker_id
            if size == 32:
                return nonce
            raise AssertionError(f"unexpected token size: {size}")

    class NoncePipe:
        def write(self, payload: bytes) -> int:
            nonce_writes.append(("write", payload))
            return len(payload)

        def flush(self) -> None:
            nonce_writes.append("flush")

        def close(self) -> None:
            nonce_writes.append("close")

    class Process:
        pid = 4321

        def __init__(self, args: list[str]) -> None:
            self.args = args
            self.stdin = NoncePipe()

    def popen(command: list[str], **kwargs: object) -> Process:
        assert not marker.exists()
        recorded.update(command=command, **kwargs)
        return Process(command)

    monkeypatch.setattr(smoke, "secrets", SecretSource, raising=False)
    monkeypatch.setattr(smoke.os, "name", "nt")
    monkeypatch.setattr(smoke.subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200, raising=False)
    monkeypatch.setattr(smoke.subprocess, "Popen", popen)

    process, stream = smoke._start_process(
        child_command,
        cwd=tmp_path,
        env=child_environment,
        log_path=log_path,
        windows_supervisor_python=supervisor_python,
    )
    stream.close()
    log_path.write_text(f"nonce={nonce}\nmarker={marker}\n", encoding="utf-8")

    assert recorded["command"] == [
        str(supervisor_python.absolute()),
        str(smoke.WINDOWS_JOB_WRAPPER),
        str(marker),
        *child_command,
    ]
    assert recorded["env"] == child_environment
    assert recorded["stdin"] == smoke.subprocess.PIPE
    assert recorded["creationflags"] == 0x200
    assert recorded["start_new_session"] is False
    assert nonce_writes == [("write", f"{nonce}\n".encode()), "flush", "close"]
    assert nonce not in recorded["command"]  # type: ignore[operator]
    assert nonce not in str(marker)
    assert nonce not in child_environment.values()
    assert marker.parent == log_path.parent
    assert not marker.exists()
    assert process._agentseek_windows_empty_tree_marker == str(marker)  # type: ignore[attr-defined]
    assert process._agentseek_windows_empty_tree_nonce == nonce  # type: ignore[attr-defined]
    assert process._agentseek_diagnostic_environment == {  # type: ignore[attr-defined]
        "AGENTSEEK_WINDOWS_JOB_MARKER": str(marker),
        "AGENTSEEK_WINDOWS_JOB_NONCE": nonce,
    }
    monkeypatch.setattr(smoke.os, "name", "posix")
    diagnostic = smoke._read_log(process)  # type: ignore[arg-type]
    assert "<redacted>" in diagnostic
    assert nonce not in diagnostic
    assert str(marker) not in diagnostic


@pytest.mark.parametrize("failure_stage", ["write", "flush", "close"])
def test_windows_start_process_rolls_back_nonce_handoff_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure_stage: str,
) -> None:
    supervisor_python = tmp_path / "child" / "Scripts" / "python.exe"
    supervisor_python.parent.mkdir(parents=True)
    supervisor_python.touch()
    log_path = tmp_path / "run" / "logs" / "runtime.log"
    log_path.parent.mkdir(parents=True)
    nonce = "8fdd06df7fc44f4cb34cc976943bf9437793a196830005dc9858d438b9ea67cb"
    marker_id = "c5a84da0de9e4561af4c489cad802d63"
    recorded: dict[str, object] = {}

    class SecretSource:
        @staticmethod
        def token_hex(size: int) -> str:
            return marker_id if size == 16 else nonce

    class NoncePipe:
        def __init__(self) -> None:
            self.close_calls = 0

        def write(self, payload: bytes) -> int:
            if failure_stage == "write":
                raise OSError("nonce write failed")
            return len(payload)

        def flush(self) -> None:
            if failure_stage == "flush":
                raise OSError("nonce flush failed")

        def close(self) -> None:
            self.close_calls += 1
            if failure_stage == "close":
                raise OSError("nonce close failed")

    class Process:
        pid = 4321

        def __init__(self, args: list[str]) -> None:
            self.args = args
            self.stdin = NoncePipe()
            self.kill_calls = 0
            self.wait_timeouts: list[float] = []

        def kill(self) -> None:
            self.kill_calls += 1

        def wait(self, *, timeout: float) -> int:
            self.wait_timeouts.append(timeout)
            return -9

    process: Process | None = None

    def popen(command: list[str], **kwargs: object) -> Process:
        nonlocal process
        recorded.update(command=command, **kwargs)
        process = Process(command)
        return process

    monkeypatch.setattr(smoke, "secrets", SecretSource, raising=False)
    monkeypatch.setattr(smoke.os, "name", "nt")
    monkeypatch.setattr(smoke.subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200, raising=False)
    monkeypatch.setattr(smoke.subprocess, "Popen", popen)

    with pytest.raises(RuntimeError, match="nonce handoff failed"):
        smoke._start_process(
            [r"C:\runtime\agentseek.exe", "dev", "--skip-check"],
            cwd=tmp_path,
            env={"SAFE": "1"},
            log_path=log_path,
            windows_supervisor_python=supervisor_python,
        )

    monkeypatch.setattr(smoke.os, "name", "posix")
    assert process is not None
    assert process.kill_calls == 1
    assert process.wait_timeouts == [smoke.FORCE_SHUTDOWN_TIMEOUT_SECONDS]
    assert process.stdin.close_calls >= 1
    assert not hasattr(process, "_agentseek_windows_empty_tree_nonce")
    assert not hasattr(process, "_agentseek_windows_empty_tree_marker")
    assert recorded["stdout"].closed is True  # type: ignore[union-attr]
    assert nonce not in recorded["command"]  # type: ignore[operator]
    assert recorded["env"] == {"SAFE": "1"}
    assert not log_path.with_name(f".{log_path.name}.{marker_id}.tree-empty.json").exists()


def test_windows_nonce_handoff_error_remains_primary_when_rollback_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    supervisor_python = tmp_path / "child" / "Scripts" / "python.exe"
    supervisor_python.parent.mkdir(parents=True)
    supervisor_python.touch()
    log_path = tmp_path / "run" / "logs" / "runtime.log"
    log_path.parent.mkdir(parents=True)
    nonce = "8fdd06df7fc44f4cb34cc976943bf9437793a196830005dc9858d438b9ea67cb"
    marker_id = "c5a84da0de9e4561af4c489cad802d63"

    class SecretSource:
        @staticmethod
        def token_hex(size: int) -> str:
            return marker_id if size == 16 else nonce

    class NoncePipe:
        def write(self, _payload: bytes) -> int:
            raise OSError("nonce write failed")

        def flush(self) -> None:
            pytest.fail("flush must not follow a failed write")

        def close(self) -> None:
            raise OSError("nonce pipe close failed")

    class Process:
        pid = 4321

        def __init__(self) -> None:
            self.stdin = NoncePipe()
            self.kill_calls = 0
            self.wait_calls = 0

        def kill(self) -> None:
            self.kill_calls += 1
            raise OSError("wrapper kill failed")

        def wait(self, *, timeout: float) -> int:
            assert timeout == smoke.FORCE_SHUTDOWN_TIMEOUT_SECONDS
            self.wait_calls += 1
            raise subprocess.TimeoutExpired("wrapper", timeout)

    process = Process()
    monkeypatch.setattr(smoke, "secrets", SecretSource, raising=False)
    monkeypatch.setattr(smoke.os, "name", "nt")
    monkeypatch.setattr(smoke.subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200, raising=False)
    monkeypatch.setattr(smoke.subprocess, "Popen", lambda *_args, **_kwargs: process)

    with pytest.raises(RuntimeError) as exc_info:
        smoke._start_process(
            [r"C:\runtime\agentseek.exe", "dev", "--skip-check"],
            cwd=tmp_path,
            env={"SAFE": "1"},
            log_path=log_path,
            windows_supervisor_python=supervisor_python,
        )

    error = exc_info.value
    assert error.args == ("Windows Job Object nonce handoff failed",)
    assert str(error) == "Windows Job Object nonce handoff failed"
    assert error.__notes__ == [smoke.SECONDARY_CLEANUP_NOTE]
    assert isinstance(error.__cause__, OSError)
    assert str(error.__cause__) == "nonce write failed"
    assert process.kill_calls == 1
    assert process.wait_calls == 1


def test_read_log_reads_only_a_bounded_tail(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    log_path = tmp_path / "large-runtime.log"
    log_path.write_bytes(b"x" * (smoke.COMMAND_OUTPUT_TAIL_BYTES * 4) + b"tail-marker")
    process = _Process(returncode=1)
    process.args = ["/external/tool"]
    process._agentseek_environment = {}
    process._agentseek_log_path = str(log_path)
    read_sizes: list[int] = []
    original_open = smoke.Path.open

    class TrackingStream:
        def __init__(self, stream: object) -> None:
            self.stream = stream

        def __enter__(self) -> TrackingStream:
            self.stream.__enter__()  # type: ignore[attr-defined]
            return self

        def __exit__(self, *args: object) -> object:
            return self.stream.__exit__(*args)  # type: ignore[attr-defined]

        def __getattr__(self, name: str) -> object:
            return getattr(self.stream, name)

        def read(self, size: int = -1) -> object:
            read_sizes.append(size)
            return self.stream.read(size)  # type: ignore[attr-defined]

    def tracked_open(path: Path, *args: object, **kwargs: object) -> TrackingStream:
        return TrackingStream(original_open(path, *args, **kwargs))

    monkeypatch.setattr(smoke.Path, "open", tracked_open)

    diagnostic = smoke._read_log(process)

    assert diagnostic.endswith("tail-marker")
    assert read_sizes == [smoke.COMMAND_OUTPUT_TAIL_BYTES]


@pytest.mark.skipif(os.name == "nt", reason="POSIX process-group ownership regression")
def test_run_checked_timeout_reaps_owned_tree_and_reports_value_free_tail(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()
    child_pid_path = run_root / "child.pid"
    secret = "synthetic-provider-secret"
    script = """
import os
import subprocess
import sys
import time
from pathlib import Path

child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
Path(sys.argv[1]).write_text(str(child.pid), encoding="utf-8")
print(os.environ["SMOKE_SECRET"] * 20000, flush=True)
time.sleep(60)
"""
    started = time.monotonic()

    with pytest.raises(RuntimeError, match="timed out") as exc_info:
        smoke._run_checked(
            [sys.executable, "-c", script, str(child_pid_path)],
            cwd=run_root,
            env={**os.environ, "SMOKE_SECRET": secret},
            label="bounded command regression",
            run_root=run_root,
            timeout=0.25,
        )

    assert time.monotonic() - started < 10
    assert secret not in str(exc_info.value)
    assert "output tail:" in str(exc_info.value)
    assert len(str(exc_info.value)) <= smoke.COMMAND_OUTPUT_TAIL_BYTES + 256
    child_pid = int(child_pid_path.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        with contextlib.suppress(ProcessLookupError):
            os.kill(child_pid, smoke.signal.SIGKILL)
        pytest.fail("timed-out command descendant remained alive")

    logs = list((run_root / "command-logs").glob("*.log"))
    assert len(logs) == 1
    assert logs[0].stat().st_mode & 0o777 == 0o600
    assert logs[0].stat().st_size <= smoke.COMMAND_OUTPUT_TAIL_BYTES


def test_run_checked_caps_both_logs_and_redacts_short_sensitive_values(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()
    secret = "abc"
    script = """
import os
import sys

print("o" * 20000)
print("e" * 20000, file=sys.stderr)
print(f"prefix{os.environ['SHORT_SECRET']}suffix", file=sys.stderr)
raise SystemExit(3)
"""

    with pytest.raises(RuntimeError, match="failed with status 3") as exc_info:
        smoke._run_checked(
            [sys.executable, "-c", script],
            cwd=run_root,
            env={**os.environ, "SHORT_SECRET": secret},
            label="bounded redaction regression",
            run_root=run_root,
            timeout=5,
        )

    assert secret not in str(exc_info.value)
    logs = list((run_root / "command-logs").glob("*"))
    assert len(logs) == 2
    assert all(path.stat().st_size <= smoke.COMMAND_OUTPUT_TAIL_BYTES for path in logs)
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in logs)


@pytest.mark.skipif(os.name == "nt", reason="POSIX inherited-pipe regression")
def test_run_checked_fails_closed_without_blocking_on_detached_inherited_pipe(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()
    child_pid_path = run_root / "detached.pid"
    script = """
import subprocess
import sys
from pathlib import Path

child = subprocess.Popen(
    [sys.executable, "-c", "import time; time.sleep(7)"],
    start_new_session=True,
)
Path(sys.argv[1]).write_text(str(child.pid), encoding="utf-8")
"""
    started = time.monotonic()

    try:
        with pytest.raises(RuntimeError, match="command cleanup could not be verified"):
            smoke._run_checked(
                [sys.executable, "-c", script, str(child_pid_path)],
                cwd=run_root,
                env=os.environ,
                label="detached inherited pipe regression",
                run_root=run_root,
                timeout=2,
            )
        assert time.monotonic() - started < 6.5
    finally:
        if child_pid_path.is_file():
            child_pid = int(child_pid_path.read_text(encoding="utf-8"))
            with contextlib.suppress(ProcessLookupError):
                os.kill(child_pid, smoke.signal.SIGKILL)


@pytest.mark.parametrize(
    ("template", "required_name"),
    [
        ("deepagents/mcp", "AGENTSEEK_MODEL_API_KEY"),
        ("deepagents/research", "TAVILY_API_KEY"),
        ("langchain/cli-remote", "BUB_API_KEY"),
        ("langchain/agentic-rag-hybrid", "SILICONFLOW_API_KEY"),
    ],
)
def test_smoke_profiles_supply_synthetic_readiness_values(template: str, required_name: str) -> None:
    value = smoke.PROFILES[template].environment[required_name]
    assert value.startswith("smoke-")


def test_default_catalog_create_has_no_source_override(tmp_path: Path) -> None:
    command = smoke.build_create_command(
        Path("/external/launcher/bin/agentseek"),
        template="langchain/markdown-messages",
        output_root=tmp_path,
        catalog_mode="default",
    )
    assert command == [
        "/external/launcher/bin/agentseek",
        "create",
        "langchain/markdown-messages",
        "--no-input",
        "--output-dir",
        str(tmp_path),
    ]


def test_default_catalog_port_context_uses_packaged_locked_template(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "run"
    cache_root = run_root / "cookiecutter-cache"
    prepared = cache_root / "catalog" / "templates" / "langchain" / "cli-remote"
    prepared.mkdir(parents=True)
    (prepared / "cookiecutter.json").write_text('{"langgraph_port": "2024"}\n', encoding="utf-8")
    recorded: dict[str, object] = {}

    def run_checked(
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        label: str,
        run_root: Path,
        timeout: float,
    ) -> smoke.subprocess.CompletedProcess[str]:
        recorded.update(command=command, cwd=cwd, env=env, label=label, run_root=run_root, timeout=timeout)
        return smoke.subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"template": str(prepared)}),
            stderr="",
        )

    monkeypatch.setattr(smoke, "_run_checked", run_checked)
    source_checkout = tmp_path / "missing-source-checkout"
    launcher_python = Path("/external/launcher/bin/python")
    launcher_env = {"HOME": str(run_root / "home")}

    result = smoke._port_template_root(
        "default",
        template="langchain/cli-remote",
        source_template_root=source_checkout,
        launcher_python=launcher_python,
        launcher_environment=launcher_env,
        run_root=run_root,
    )

    assert result == prepared.resolve()
    assert recorded == {
        "command": [
            str(launcher_python),
            "-c",
            smoke.DEFAULT_CATALOG_TEMPLATE_SCRIPT,
            "langchain/cli-remote",
            str(cache_root),
        ],
        "cwd": run_root,
        "env": launcher_env,
        "label": "prepare packaged default catalog template",
        "run_root": run_root,
        "timeout": smoke.CATALOG_PREPARE_TIMEOUT_SECONDS,
    }


def test_contract_probe_asserts_shell_value() -> None:
    assert smoke.assert_contract_probe({"output": {"sentinel": "from-shell"}}) == "from-shell"
    with pytest.raises(RuntimeError, match="from-shell"):
        smoke.assert_contract_probe({"output": {"sentinel": "from-dotenv"}})


def test_contract_probe_manifest_preserves_graphs_and_extracts_sentinel(tmp_path: Path) -> None:
    generated = tmp_path / "generated"
    package = generated / "src" / "probe_project"
    package.mkdir(parents=True)
    (generated / "pyproject.toml").write_text(
        '[project]\nname = "probe-project"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    original_graphs = {
        "agent": "./src/probe_project/agent.py:graph",
        "another": "./src/probe_project/another.py:graph",
    }
    (generated / "langgraph.json").write_text(
        json.dumps({"graphs": original_graphs}),
        encoding="utf-8",
    )

    smoke._install_contract_probe(generated, "agent")

    manifest = json.loads((generated / "langgraph.json").read_text(encoding="utf-8"))
    assert {name: manifest["graphs"][name] for name in original_graphs} == original_graphs
    module = "./src/probe_project/_release_contract_probe.py"
    assert manifest["graphs"]["release_contract_probe"] == {
        "graph": f"{module}:graph",
        "prepare_input": f"{module}:prepare_input",
        "extract_output": f"{module}:extract_output",
    }
    probe_source = (package / "_release_contract_probe.py").read_text(encoding="utf-8")
    assert "def prepare_input(" in probe_source
    assert "def extract_output(" in probe_source


def test_profiles_name_a_real_graph_and_minimal_input() -> None:
    assert smoke.PROFILES["deepagents/mcp"].graph_id == "mcp"
    assert smoke.PROFILES["langchain/cli-remote"].graph_id == "agent"
    assert smoke.PROFILES["langchain/rubric"].graph_id == "rubric-demo"
    assert smoke.PROFILES["langchain/rubric"].run_input == {"request": {}}


def test_frontend_install_uses_resolved_windows_executable(tmp_path: Path) -> None:
    generated = tmp_path / "generated"
    (generated / "frontend").mkdir(parents=True)
    (generated / "frontend" / "package.json").write_text("{}\n", encoding="utf-8")
    npm = Path(r"C:\hostedtoolcache\node\npm.CMD")
    assert smoke.build_frontend_install_command(generated, npm) == [
        str(npm),
        "install",
    ]


def test_generated_frontend_install_runs_from_detected_frontend_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "run"
    generated = run_root / "rendered" / "mcp_deepagent"
    frontend = generated / "frontend"
    frontend.mkdir(parents=True)
    (frontend / "package.json").write_text("{}\n", encoding="utf-8")
    artifact_path = run_root / "artifacts" / "agentseek_api-0.2.3-py3-none-any.whl"
    artifact_path.parent.mkdir()
    artifact_path.write_bytes(b"wheel")
    artifact = smoke.WheelArtifact(
        name="agentseek-api",
        version="0.2.3",
        filename=artifact_path.name,
        path=artifact_path,
        sha256="a" * 64,
        url="https://files.pythonhosted.org/agentseek_api-0.2.3-py3-none-any.whl",
    )
    npm = Path(r"C:\hostedtoolcache\node\npm.CMD")
    toolchain = smoke.Toolchain(
        uv=Path(r"C:\hostedtoolcache\uv.exe"),
        git=Path(r"C:\Program Files\Git\bin\git.exe"),
        node=Path(r"C:\hostedtoolcache\node\node.exe"),
        npm=npm,
        sh=None,
    )
    calls: list[dict[str, object]] = []

    def run_checked(command: list[str], **kwargs: object) -> smoke.subprocess.CompletedProcess[str]:
        calls.append({"command": command, **kwargs})
        if kwargs["label"] == "deepagents/mcp: install generated frontend":
            (frontend / "node_modules").mkdir()
        return smoke.subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(smoke, "_run_checked", run_checked)

    smoke._install_generated_project(
        generated,
        artifact,
        toolchain,
        {},
        "deepagents/mcp",
        run_root,
    )

    assert calls[1]["command"] == [str(npm), "install"]
    assert calls[1]["cwd"] == frontend


def test_frontend_install_is_absent_for_cli_remote(tmp_path: Path) -> None:
    generated = tmp_path / "generated"
    generated.mkdir()
    assert smoke.build_frontend_install_command(generated, Path("/usr/bin/npm")) is None


@pytest.mark.parametrize(
    "outer_python",
    [
        "/opt/hostedtoolcache/Python/3.12.13/x64/bin/python",
        r"C:\hostedtoolcache\windows\Python\3.12.10\x64\python.exe",
    ],
)
def test_generated_sync_uses_the_exact_outer_python(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    outer_python: str,
) -> None:
    run_root = tmp_path / "run"
    generated = run_root / "rendered" / "project"
    generated.mkdir(parents=True)
    artifact_path = run_root / "artifacts" / "agentseek_api-0.2.3-py3-none-any.whl"
    artifact_path.parent.mkdir()
    artifact_path.write_bytes(b"wheel")
    artifact = smoke.WheelArtifact(
        name="agentseek-api",
        version="0.2.3",
        filename=artifact_path.name,
        path=artifact_path,
        sha256="a" * 64,
        url="https://files.pythonhosted.org/agentseek_api-0.2.3-py3-none-any.whl",
    )
    toolchain = smoke.Toolchain(
        uv=Path("/toolchain/uv"),
        git=Path("/toolchain/git"),
        node=Path("/toolchain/node"),
        npm=Path("/toolchain/npm"),
        sh=None,
    )
    calls: list[dict[str, object]] = []

    def run_checked(command: list[str], **kwargs: object) -> smoke.subprocess.CompletedProcess[str]:
        calls.append({"command": command, **kwargs})
        return smoke.subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(smoke.sys, "executable", outer_python)
    monkeypatch.setattr(smoke, "_run_checked", run_checked)

    smoke._install_generated_project(
        generated,
        artifact,
        toolchain,
        {},
        "langchain/cli-remote",
        run_root,
    )

    assert calls == [
        {
            "command": [
                str(toolchain.uv),
                "sync",
                "--python",
                outer_python,
                "--no-cache",
                "--no-config",
                "--default-index",
                smoke.PYPI_INDEX,
                "--find-links",
                str(artifact_path.parent.resolve()),
            ],
            "cwd": generated,
            "env": {},
            "label": "langchain/cli-remote: install generated Python environment",
            "run_root": run_root,
            "timeout": smoke.DEPENDENCY_INSTALL_TIMEOUT_SECONDS,
        }
    ]


def test_windows_runtime_uses_sqlite_without_embedded_seekdb(tmp_path: Path) -> None:
    environment = smoke.build_runtime_environment("win32", "AMD64", tmp_path, "sqlite")
    assert environment["SEEKDB_EMBED"] == "false"
    assert environment["METADATA_DB_BACKEND"] == "sqlite"
    assert environment["METADATA_DB_URL"].startswith("sqlite+aiosqlite:///")
    assert "SEEKDB_EMBED_DIR" not in environment


def test_agentic_rag_uses_the_preexisting_embedded_database_for_eager_import(tmp_path: Path) -> None:
    embed_dir = (tmp_path / "sdb").resolve()
    environment = smoke._child_environment(
        {},
        smoke.PROFILES["langchain/agentic-rag"],
        tmp_path,
        provider_port=43125,
        backend_port=2024,
        runtime_environment={
            "SEEKDB_EMBED": "true",
            "SEEKDB_EMBED_DIR": str(embed_dir),
        },
    )

    assert environment["SEEKDB_PATH"] == environment["SEEKDB_EMBED_DIR"] == str(embed_dir)
    assert environment["SEEKDB_DB_NAME"] == environment["OCEANBASE_DB_NAME"] == "test"


@pytest.mark.parametrize("template", ["deepagents/mcp", "langchain/agentic-rag-hybrid"])
def test_other_profiles_keep_seekdb_and_api_databases_isolated(
    tmp_path: Path,
    template: str,
) -> None:
    embed_dir = (tmp_path / "sdb").resolve()
    environment = smoke._child_environment(
        {},
        smoke.PROFILES[template],
        tmp_path,
        provider_port=43125,
        backend_port=2024,
        runtime_environment={
            "SEEKDB_EMBED": "true",
            "SEEKDB_EMBED_DIR": str(embed_dir),
        },
    )

    assert environment["SEEKDB_PATH"] == str((tmp_path / "databases" / "rag-seekdb").resolve())
    assert environment["SEEKDB_DB_NAME"].startswith("smoke_seekdb_")
    assert environment["OCEANBASE_DB_NAME"].startswith("smoke_api_")
    assert environment["SEEKDB_DB_NAME"] != environment["OCEANBASE_DB_NAME"]


def test_proof_runtime_record_accepts_distinct_allocated_ports() -> None:
    payload = {
        "runtime": {
            "provider_port": 43125,
            "backend_port": 2024,
            "expected_ports": [2024, 43125, 43126],
        }
    }

    smoke._require_value_free_proof(payload, {})

    assert payload["runtime"] == {
        "provider_port": 43125,
        "backend_port": 2024,
        "expected_ports": [2024, 43125, 43126],
    }


@pytest.mark.parametrize(
    "runtime",
    [
        {},
        {"provider_port": "43125", "backend_port": 2024, "expected_ports": [2024, 43125]},
        {"provider_port": 43125, "backend_port": 0, "expected_ports": [0, 43125]},
        {"provider_port": 43125, "backend_port": 2024, "expected_ports": [2024, 43125, 43125]},
        {"provider_port": 43125, "backend_port": 2024, "expected_ports": [2024, 43126]},
    ],
)
def test_proof_runtime_record_rejects_invalid_port_schema(runtime: dict[str, object]) -> None:
    with pytest.raises(RuntimeError, match="runtime port record"):
        smoke._require_value_free_proof({"runtime": runtime}, {})


def test_linux_runtime_uses_external_embedded_directory() -> None:
    with tempfile.TemporaryDirectory(prefix="as-runtime-") as raw_run_root:
        run_root = Path(raw_run_root)
        environment = smoke.build_runtime_environment("linux", "x86_64", run_root, "embedded")
        assert environment["SEEKDB_EMBED"] == "true"
        embed_dir = Path(environment["SEEKDB_EMBED_DIR"])
        assert embed_dir == (run_root / "sdb").resolve()
        assert len(os.fsencode(embed_dir / "run" / "sql.sock")) <= 107
        assert "METADATA_DB_URL" not in environment


@pytest.mark.parametrize(
    ("platform_name", "machine_name", "socket_limit"),
    [("darwin", "arm64", 103), ("linux", "x86_64", 107)],
)
def test_embedded_runtime_rejects_overlong_socket_path_before_mkdir(
    tmp_path: Path,
    platform_name: str,
    machine_name: str,
    socket_limit: int,
) -> None:
    run_root = tmp_path / ("long-root-" + "x" * 120)
    socket_path = run_root / "sdb" / "run" / "sql.sock"
    assert len(os.fsencode(socket_path)) > socket_limit

    with pytest.raises(RuntimeError, match="^embedded seekdb socket path exceeds platform limit$"):
        smoke.build_runtime_environment(platform_name, machine_name, run_root, "embedded")

    assert not (run_root / "sdb").exists()


def test_auto_runtime_rejects_unsupported_intel_macos(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="unsupported runtime platform"):
        smoke.build_runtime_environment("darwin", "x86_64", tmp_path, "auto")


def test_candidate_wheel_rejects_relative_paths() -> None:
    with pytest.raises(RuntimeError, match="absolute"):
        smoke.validate_candidate_wheel(
            Path("dist/agentseek-0.1.3-py3-none-any.whl"),
            version="0.1.3",
            forbidden_roots=[smoke.ROOT],
        )


def test_profiles_cover_exact_retained_runtime_matrix() -> None:
    assert set(smoke.PROFILES) == {
        "deepagents/content-builder",
        "deepagents/mcp",
        "deepagents/research",
        "langchain/agentic-rag",
        "langchain/agentic-rag-hybrid",
        "langchain/cli-remote",
        "langchain/markdown-messages",
        "langchain/rubric",
    }


def test_runtime_workflow_covers_every_retained_migration() -> None:
    workflow = yaml.safe_load((smoke.ROOT / ".github" / "workflows" / "main.yml").read_text(encoding="utf-8"))
    job = workflow["jobs"]["migrated-local-runtime-matrix"]
    expected_matrix = [
        {
            "template": "deepagents/content-builder",
            "os": "ubuntu-latest",
            "id": "content-builder-linux",
            "database": "embedded",
        },
        {
            "template": "deepagents/mcp",
            "os": "ubuntu-latest",
            "id": "mcp-linux",
            "database": "embedded",
        },
        {
            "template": "deepagents/mcp",
            "os": "windows-latest",
            "id": "mcp-windows",
            "database": "sqlite",
        },
        {
            "template": "deepagents/research",
            "os": "ubuntu-latest",
            "id": "research-linux",
            "database": "embedded",
        },
        {
            "template": "langchain/agentic-rag",
            "os": "ubuntu-latest",
            "id": "agentic-rag-linux",
            "database": "embedded",
        },
        {
            "template": "langchain/agentic-rag-hybrid",
            "os": "ubuntu-latest",
            "id": "agentic-rag-hybrid-linux",
            "database": "embedded",
        },
        {
            "template": "langchain/cli-remote",
            "os": "ubuntu-latest",
            "id": "cli-remote-linux",
            "database": "embedded",
        },
        {
            "template": "langchain/markdown-messages",
            "os": "ubuntu-latest",
            "id": "markdown-messages-linux",
            "database": "embedded",
        },
        {
            "template": "langchain/rubric",
            "os": "ubuntu-latest",
            "id": "rubric-linux",
            "database": "embedded",
        },
    ]
    expected_harness_command = (
        "uv run python scripts/generated_runtime_smoke.py"
        ' --template "${{ matrix.template }}"'
        " --catalog-mode source"
        " --agentseek-version 0.1.2"
        " --agentseek-api-version 0.2.3"
        ' --database-mode "${{ matrix.database }}"'
        ' --output-root "${{ runner.temp }}/r/${{ matrix.id }}"'
        ' --proof-output "${{ runner.temp }}/runtime-proof/${{ matrix.id }}.json"'
    )
    expected_upload = {
        "name": "Upload published-runtime proof",
        "uses": "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02",
        "with": {
            "name": "runtime-proof-${{ matrix.id }}",
            "path": "${{ runner.temp }}/runtime-proof/${{ matrix.id }}.json",
            "if-no-files-found": "error",
        },
    }

    assert set(job) == {"name", "runs-on", "timeout-minutes", "strategy", "steps"}
    assert job["name"] == "${{ matrix.template }} (${{ matrix.os }})"
    assert job["runs-on"] == "${{ matrix.os }}"
    assert job["timeout-minutes"] == 30
    assert job["strategy"] == {
        "fail-fast": False,
        "matrix": {"include": expected_matrix},
    }
    assert job["steps"] == [
        {
            "uses": "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
            "with": {"persist-credentials": False},
        },
        {
            "uses": "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
            "with": {"python-version": "3.12"},
        },
        {
            "uses": "actions/setup-node@820762786026740c76f36085b0efc47a31fe5020",
            "with": {"node-version": "22"},
        },
        {
            "uses": "astral-sh/setup-uv@d0cc045d04ccac9d8b7881df0226f9e82c39688e",
            "with": {"version": "0.9.28", "enable-cache": True},
        },
        {"run": "uv sync --frozen --dev"},
        {
            "name": "Render, install, and exercise the generated lifecycle",
            "run": expected_harness_command,
        },
        expected_upload,
    ]
    assert "if" not in job["steps"][-1]
    _assert_no_workflow_secrets(job)


def test_runtime_workflow_linux_output_paths_fit_embedded_socket_limit() -> None:
    workflow = yaml.safe_load((smoke.ROOT / ".github" / "workflows" / "main.yml").read_text(encoding="utf-8"))
    job = workflow["jobs"]["migrated-local-runtime-matrix"]
    hosted_output_root = Path("/home/runner/work/_temp/r")
    socket_limit = smoke.EMBEDDED_SOCKET_PATH_LIMITS["linux"]

    for case in job["strategy"]["matrix"]["include"]:
        if case["os"] != "ubuntu-latest":
            continue
        socket_path = hosted_output_root / case["id"] / "template-runtime-12345678" / "sdb/run/sql.sock"
        path_length = len(os.fsencode(socket_path))
        assert path_length <= socket_limit, f"{case['id']}: {path_length} > {socket_limit} bytes"


def test_candidate_wheel_requires_matching_distribution_metadata(tmp_path: Path) -> None:
    wheel = tmp_path / "agentseek-0.1.3-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            "agentseek-0.1.3.dist-info/METADATA",
            "Metadata-Version: 2.4\nName: agentseek\nVersion: 0.1.2\n",
        )

    with pytest.raises(RuntimeError, match="metadata"):
        smoke.validate_candidate_wheel(wheel, version="0.1.3", forbidden_roots=[smoke.ROOT])


def test_candidate_wheel_stages_validated_bytes_before_source_mutation(tmp_path: Path) -> None:
    source = tmp_path / "external" / "agentseek-0.1.3-py3-none-any.whl"
    source.parent.mkdir()
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr(
            "agentseek-0.1.3.dist-info/METADATA",
            "Metadata-Version: 2.4\nName: agentseek\nVersion: 0.1.3\n",
        )
        archive.writestr("agentseek/__init__.py", '__version__ = "0.1.3"\n')
    validated_bytes = source.read_bytes()
    expected_digest = hashlib.sha256(validated_bytes).hexdigest()
    artifact_dir = tmp_path / "run" / "artifacts"

    artifact = smoke.validate_candidate_wheel(
        source,
        version="0.1.3",
        forbidden_roots=[smoke.ROOT],
        destination=artifact_dir,
    )
    source.write_bytes(b"mutated after staging")

    assert artifact.path == artifact_dir / source.name
    assert artifact.path.read_bytes() == validated_bytes
    assert artifact.sha256 == expected_digest
    assert artifact.url == source.resolve().as_uri()
    assert not list(artifact_dir.glob(".*.tmp"))


def test_catalog_proof_records_observed_lock_without_render_claim(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    template = "langchain/cli-remote"
    lock = {
        "catalog_repository": "https://github.com/agentseek-ai/agentseek-templates.git",
        "catalog_commit": "a" * 40,
        "catalog_release": "v0.1.0",
        "core_repository": "https://github.com/ob-labs/agentseek.git",
        "core_commit": "b" * 40,
        "core_release": "core-snapshot-v0.1.0",
        "templates": {template: "CLI Remote"},
        "template_digests": {template: "c" * 64},
    }
    completed = smoke.subprocess.CompletedProcess(
        [],
        0,
        stdout=json.dumps({"sha256": "d" * 64, "lock": lock}),
        stderr="",
    )
    monkeypatch.setattr(smoke, "_run_checked", lambda *_args, **_kwargs: completed)
    launcher_root = tmp_path / "run" / "launcher-venv"
    launcher_root.mkdir(parents=True)

    record = smoke._read_catalog_proof(
        launcher_root / "bin" / "python",
        {},
        launcher_root,
        template,
        "default",
    )

    assert record["sha256"] == "d" * 64
    assert record["template_digest"] == "c" * 64
    assert "used_for_render" not in record


def test_generated_lock_validates_uv_flat_index_wheel(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    wheel = artifact_dir / "agentseek_api-0.2.3-py3-none-any.whl"
    wheel.write_bytes(b"verified wheel bytes")
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    artifact = smoke.WheelArtifact(
        name="agentseek-api",
        version="0.2.3",
        filename=wheel.name,
        path=wheel,
        sha256=digest,
        url="https://files.pythonhosted.org/agentseek_api-0.2.3-py3-none-any.whl",
    )
    generated = tmp_path / "rendered" / "project"
    generated.mkdir(parents=True)
    (generated / "uv.lock").write_text(
        """version = 1

[[package]]
name = "agentseek-api"
version = "0.2.3"
source = { registry = "../../artifacts" }
wheels = [
    { path = "agentseek_api-0.2.3-py3-none-any.whl" },
]
""",
        encoding="utf-8",
    )

    assert smoke._validate_api_lock(generated, artifact) == {
        "version": "0.2.3",
        "wheel_filename": wheel.name,
        "wheel_sha256": digest,
    }


def test_release_harness_requires_python_312() -> None:
    smoke.require_release_python(3, 12)
    with pytest.raises(RuntimeError, match="Python 3.12"):
        smoke.require_release_python(3, 13)


def test_release_harness_rejects_previous_api_release_before_download(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(smoke, "require_release_python", lambda *_args: None)
    monkeypatch.setattr(
        smoke.runtime_proof,
        "download_published_wheel",
        lambda *_args, **_kwargs: pytest.fail("artifact download must not start"),
    )

    with pytest.raises(RuntimeError, match=r"agentseek-api==0\.2\.3"):
        smoke.main(
            [
                "--template",
                "langchain/markdown-messages",
                "--catalog-mode",
                "source",
                "--agentseek-version",
                "0.1.2",
                "--agentseek-api-version",
                "0.2.2",
                "--output-root",
                str(tmp_path / "runtime"),
                "--proof-output",
                str(tmp_path / "proof.json"),
            ]
        )
