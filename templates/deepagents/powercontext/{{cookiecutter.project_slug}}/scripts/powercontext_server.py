"""Own the PowerContext Server for one project run.

This script is a managed ``agentseek dev`` process, so the Server follows the
same lifecycle as the API and the frontend:

* a ready Server at ``POWERCONTEXT_URL`` is reused and never restarted;
* otherwise a local Server is started as this process's own child, so the
  AgentSeek runtime stops it together with every other project process;
* ``POWERCONTEXT_AUTOSTART=false`` keeps the Server fully external and turns
  this process into an idle placeholder.

Rule: this process never exits on its own. The AgentSeek runtime stops the
whole project as soon as any managed process finishes, and PowerContext is
documented as fail-open, so an unusable Server must never stop the API and the
frontend. Every failure path reports the reason and then idles.

Direct invocations also read ``.env`` so ``POWERCONTEXT_URL`` and
``POWERCONTEXT_AUTOSTART`` behave the same as under ``agentseek dev``. Exported
variables win over the file, and blank values are ignored.
"""

from __future__ import annotations

import contextlib
import errno
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import NamedTuple
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVER_PACKAGE = "powercontext[cli,server,seekdb]==1.0.0"
SERVER_READY_TIMEOUT = 60.0
HEALTH_TIMEOUT = 1.5
IDLE_INTERVAL = 5.0
SHUTDOWN_TIMEOUT = 10.0
TRUE_VALUES = {"1", "true", "yes", "on"}


class Probe(NamedTuple):
    """One readiness check. Probing never raises; the caller decides what to do."""

    state: str
    detail: str = ""


def _load_env_file(path: Path) -> None:
    """Apply ``.env`` defaults for direct invocations; the real environment wins."""
    with contextlib.suppress(OSError):
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :].lstrip()
            key, separator, value = line.partition("=")
            key = key.strip()
            if not separator or not key or key in os.environ:
                continue
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            if value:
                os.environ[key] = value


def _server_url() -> tuple[str, str, int]:
    raw_url = os.environ.get("POWERCONTEXT_URL", "http://127.0.0.1:8000").strip().rstrip("/")
    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"Invalid POWERCONTEXT_URL: {raw_url!r}")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    health_url = f"{raw_url}/health/ready"
    return raw_url, health_url, port


def _is_local_host(hostname: str) -> bool:
    return hostname in {"localhost", "127.0.0.1", "::1"}


def _autostart_enabled() -> bool:
    return os.environ.get("POWERCONTEXT_AUTOSTART", "true").strip().lower() in TRUE_VALUES


def _server_log_path() -> Path:
    return Path(os.environ.get("POWERCONTEXT_SERVER_LOG", str(PROJECT_ROOT / ".powercontext-server.log")))


def _probe(health_url: str) -> Probe:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(health_url, timeout=HEALTH_TIMEOUT) as response:
            if 200 <= response.status < 300:
                return Probe("ready")
            return Probe("blocked", f"PowerContext Server responded with HTTP {response.status} at {health_url}.")
    except urllib.error.HTTPError as error:
        if error.code in {502, 503, 504}:
            return Probe("starting", f"PowerContext Server is starting at {health_url} (HTTP {error.code}).")
        return Probe("blocked", f"PowerContext Server responded with HTTP {error.code} at {health_url}.")
    except urllib.error.URLError as error:
        reason = error.reason
        if isinstance(reason, OSError) and reason.errno in {
            errno.ECONNREFUSED,
            errno.ECONNRESET,
            errno.EHOSTUNREACH,
            errno.ENETUNREACH,
        }:
            return Probe("unavailable")
        return Probe("blocked", f"Could not check PowerContext Server at {health_url}: {reason}.")
    except TimeoutError:
        return Probe("unavailable", f"PowerContext Server health check timed out at {health_url}.")


@contextlib.contextmanager
def _startup_lock():
    lock_path = Path.home() / ".agentseek" / "powercontext-server-start.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock_file:
        if os.name == "posix":
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "posix":
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _start_local_server(raw_url: str, port: int) -> tuple[subprocess.Popen[bytes], Path]:
    """Start the Server inside this process group so it stops with the project."""
    parsed = urlparse(raw_url)
    log_path = _server_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("ab")
    command = [
        "uv",
        "tool",
        "run",
        "--python",
        "3.12",
        "--from",
        SERVER_PACKAGE,
        "--with",
        "pymysql>=1.1.3,<1.2",
        "powercontext",
        "server",
        "run",
        "--host",
        parsed.hostname or "127.0.0.1",
        "--port",
        str(port),
        "--env-file",
        ".env",
    ]
    # No new session: the managed parent must be able to terminate this child.
    popen_kwargs: dict[str, object] = {
        "cwd": PROJECT_ROOT,
        "stdin": subprocess.DEVNULL,
        "stdout": log_file,
        "stderr": subprocess.STDOUT,
    }
    try:
        return subprocess.Popen(command, **popen_kwargs), log_path
    except OSError:
        log_file.close()
        raise


def _log_tail(log_path: Path, limit: int = 12) -> str:
    with contextlib.suppress(OSError):
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        if lines:
            return "\n".join(lines[-limit:])
    return ""


def _wait_until_ready(health_url: str, process: subprocess.Popen[bytes], log_path: Path) -> None:
    deadline = time.monotonic() + SERVER_READY_TIMEOUT
    while time.monotonic() < deadline:
        if process.poll() is not None:
            detail = _log_tail(log_path)
            raise RuntimeError(
                f"PowerContext Server exited with code {process.returncode}; see {log_path}"
                + (f"\n{detail}" if detail else "")
            )
        if _probe(health_url).state == "ready":
            return
        time.sleep(0.5)
    raise RuntimeError(f"PowerContext Server did not become ready at {health_url}; see {log_path}")


def _terminate(process: subprocess.Popen[bytes]) -> None:
    with contextlib.suppress(OSError):
        process.terminate()
    try:
        process.wait(timeout=SHUTDOWN_TIMEOUT)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(OSError):
            process.kill()


def _install_child_shutdown(process: subprocess.Popen[bytes]) -> None:
    """Stop the owned Server even when only this process is signalled."""

    def _shutdown(signum: int, frame: object) -> None:
        del signum, frame
        _terminate(process)
        raise SystemExit(0)

    for name in ("SIGTERM", "SIGINT", "SIGBREAK"):
        signum = getattr(signal, name, None)
        if signum is not None:
            signal.signal(signum, _shutdown)


def _idle() -> int:
    """Stay alive without owning a Server, so ``agentseek dev`` keeps running."""
    while True:
        try:
            time.sleep(IDLE_INTERVAL)
        except KeyboardInterrupt:
            return 0


def _ensure_local_server(raw_url: str, port: int, health_url: str) -> tuple[subprocess.Popen[bytes] | None, str]:
    """Return the owned Server process and a note, or ``None`` when none was started."""
    with _startup_lock():
        probe = _probe(health_url)
        if probe.state == "ready":
            return None, f"Reusing PowerContext Server at {raw_url}"
        if probe.state == "starting":
            return None, f"PowerContext Server is already starting at {raw_url}; not starting another."
        if probe.state == "blocked":
            return None, f"{probe.detail} Not starting another Server there."
        print(f"Starting PowerContext Server at {raw_url}", flush=True)
        try:
            process, log_path = _start_local_server(raw_url, port)
        except OSError as error:
            return None, f"PowerContext startup failed: {error}; keeping the project running without it."
        _install_child_shutdown(process)
        try:
            _wait_until_ready(health_url, process, log_path)
        except (OSError, RuntimeError) as error:
            _terminate(process)
            return None, f"PowerContext startup failed: {error}; keeping the project running without it."
        return process, ""


def main() -> int:
    _load_env_file(PROJECT_ROOT / ".env")
    try:
        raw_url, health_url, port = _server_url()
    except ValueError as error:
        print(f"{error}; keeping the project running without PowerContext.", file=sys.stderr, flush=True)
        return _idle()
    if not _autostart_enabled():
        print(
            f"POWERCONTEXT_AUTOSTART is disabled; expecting an external PowerContext Server at {raw_url}",
            flush=True,
        )
        return _idle()

    probe = _probe(health_url)
    if probe.state == "ready":
        print(f"Reusing PowerContext Server at {raw_url}", flush=True)
        return _idle()
    if not _is_local_host(urlparse(raw_url).hostname or ""):
        print(
            f"PowerContext Server is not ready at {raw_url}; "
            "a remote POWERCONTEXT_URL must be started externally.",
            file=sys.stderr,
            flush=True,
        )
        return _idle()
    if probe.state != "unavailable":
        print(f"{probe.detail} Not starting another Server there.", file=sys.stderr, flush=True)
        return _idle()

    process, note = _ensure_local_server(raw_url, port, health_url)
    if process is None:
        print(note, file=sys.stderr, flush=True)
        return _idle()
    print(
        f"PowerContext Server is ready at {raw_url} (PID {process.pid}); it stops with this project",
        flush=True,
    )
    returncode = process.wait()
    print(
        f"PowerContext Server exited with code {returncode}; keeping the project running without it.",
        file=sys.stderr,
        flush=True,
    )
    return _idle()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:  # noqa: BLE001 - a sidecar must never stop the project it serves
        print(f"PowerContext startup failed: {error}; keeping the project running without it.", file=sys.stderr)
        raise SystemExit(_idle()) from error
