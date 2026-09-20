"""The managed Server launcher must never stop the project it serves.

``agentseek dev`` stops every process as soon as one managed process exits, and
the generated app is documented as fail-open. A PowerContext Server that is
missing, unreachable, or unhealthy therefore has to leave the API and the
frontend running.
"""

from __future__ import annotations

import http.server
import importlib.util
import os
import shutil
import socketserver
import subprocess
import sys
import threading
import time
import types
from collections.abc import Iterator
from pathlib import Path
from typing import IO

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = PROJECT_ROOT / "scripts" / "powercontext_server.py"
OUTPUT_TIMEOUT_SECONDS = 30.0
IDLE_GRACE_SECONDS = 1.0


class _HealthHandler(http.server.BaseHTTPRequestHandler):
    """Answer every request with an unhealthy response."""

    def do_GET(self) -> None:
        self.send_response(500)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        del format, args


@pytest.fixture
def unhealthy_server() -> Iterator[str]:
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", 0), _HealthHandler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_address[1]}"
        finally:
            server.shutdown()
            thread.join(timeout=10)


def _start_launcher(
    environment: dict[str, str],
    log_path: Path,
    *,
    script: Path = LAUNCHER,
    cwd: Path = PROJECT_ROOT,
) -> tuple[subprocess.Popen[bytes], IO[str]]:
    handle = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, str(script)],
        cwd=cwd,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=handle,
        stderr=subprocess.STDOUT,
    )
    return process, handle


def _stop_launcher(process: subprocess.Popen[bytes], handle: IO[str]) -> None:
    process.terminate()
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=20)
    handle.close()


def _wait_for_output(process: subprocess.Popen[bytes], log_path: Path, needle: str) -> str:
    deadline = time.monotonic() + OUTPUT_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        output = log_path.read_text(encoding="utf-8")
        if needle in output:
            return output
        assert process.poll() is None, f"launcher stopped early with {process.returncode}:\n{output}"
        time.sleep(0.1)
    raise AssertionError(f"launcher never reported {needle!r}:\n{log_path.read_text(encoding='utf-8')}")


def _assert_kept_alive(process: subprocess.Popen[bytes], log_path: Path) -> None:
    deadline = time.monotonic() + IDLE_GRACE_SECONDS
    while time.monotonic() < deadline:
        assert process.poll() is None, f"launcher exited with {process.returncode}:\n{log_path.read_text(encoding="utf-8")}"
        time.sleep(0.1)


def _environment(tmp_path: Path, url: str, autostart: str) -> tuple[dict[str, str], Path]:
    server_log = tmp_path / "powercontext-server.log"
    return (
        {
            **os.environ,
            "POWERCONTEXT_URL": url,
            "POWERCONTEXT_AUTOSTART": autostart,
            "POWERCONTEXT_SERVER_LOG": str(server_log),
        },
        server_log,
    )


def test_autostart_disabled_survives_a_failed_health_check(unhealthy_server: str, tmp_path: Path) -> None:
    """An unhealthy external endpoint must not end the managed process."""
    environment, server_log = _environment(tmp_path, unhealthy_server, "false")
    log_path = tmp_path / "launcher.log"
    process, handle = _start_launcher(environment, log_path)
    try:
        output = _wait_for_output(process, log_path, "POWERCONTEXT_AUTOSTART is disabled")
        _assert_kept_alive(process, log_path)
    finally:
        _stop_launcher(process, handle)
    assert unhealthy_server in output
    assert not server_log.exists(), "autostart stayed off, so no Server may be provisioned"


def test_blocked_endpoint_survives_autostart(unhealthy_server: str, tmp_path: Path) -> None:
    """A port answering HTTP 500 is not ours to replace, and not fatal either."""
    environment, server_log = _environment(tmp_path, unhealthy_server, "true")
    log_path = tmp_path / "launcher.log"
    process, handle = _start_launcher(environment, log_path)
    try:
        output = _wait_for_output(process, log_path, "Not starting another Server there.")
        _assert_kept_alive(process, log_path)
    finally:
        _stop_launcher(process, handle)
    assert "HTTP 500" in output
    assert not server_log.exists(), "a blocked endpoint must not be replaced by a second Server"


def test_remote_url_that_is_not_ready_survives(tmp_path: Path) -> None:
    """A remote Server is never started locally, and never fatal either."""
    environment, server_log = _environment(tmp_path, "http://203.0.113.1:8000", "true")
    log_path = tmp_path / "launcher.log"
    process, handle = _start_launcher(environment, log_path)
    try:
        _wait_for_output(process, log_path, "must be started externally")
        _assert_kept_alive(process, log_path)
    finally:
        _stop_launcher(process, handle)
    assert not server_log.exists(), "a remote POWERCONTEXT_URL must never start a local Server"


def _launcher_module() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("powercontext_server", LAUNCHER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_env_file_supplies_defaults_without_overriding_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The documented manual command has to honor .env like ``agentseek dev`` does."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comment\n"
        "POWERCONTEXT_URL=http://127.0.0.1:9001\n"
        "POWERCONTEXT_AUTOSTART=false\n"
        "POWERCONTEXT_TOKEN=\n"
        'export POWERCONTEXT_SCOPE_ID="scope-from-file"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("POWERCONTEXT_URL", "http://127.0.0.1:9002")
    monkeypatch.delenv("POWERCONTEXT_AUTOSTART", raising=False)
    monkeypatch.delenv("POWERCONTEXT_TOKEN", raising=False)
    monkeypatch.delenv("POWERCONTEXT_SCOPE_ID", raising=False)

    _launcher_module()._load_env_file(env_file)

    assert os.environ["POWERCONTEXT_URL"] == "http://127.0.0.1:9002"
    assert os.environ["POWERCONTEXT_AUTOSTART"] == "false"
    assert os.environ["POWERCONTEXT_SCOPE_ID"] == "scope-from-file"
    assert "POWERCONTEXT_TOKEN" not in os.environ, "a blank .env value must stay unset"


def test_manual_command_reads_the_project_env_file(tmp_path: Path) -> None:
    """Run the documented command the way a README reader does: nothing exported."""
    project = tmp_path / "manual-project"
    script = project / "scripts" / "powercontext_server.py"
    script.parent.mkdir(parents=True)
    shutil.copy(LAUNCHER, script)
    dotenv_url = "http://127.0.0.1:64001"
    (project / ".env").write_text(
        f"POWERCONTEXT_URL={dotenv_url}\nPOWERCONTEXT_AUTOSTART=false\n",
        encoding="utf-8",
    )
    environment = {key: value for key, value in os.environ.items() if not key.startswith("POWERCONTEXT")}
    log_path = project / "launcher.log"
    process, handle = _start_launcher(environment, log_path, script=script, cwd=project)
    try:
        output = _wait_for_output(process, log_path, "POWERCONTEXT_AUTOSTART is disabled")
        _assert_kept_alive(process, log_path)
    finally:
        _stop_launcher(process, handle)
    assert dotenv_url in output, "the launcher must use POWERCONTEXT_URL from .env, not the 8000 default"
    assert not (project / ".powercontext-server.log").exists(), "autostart from .env must be honored"
