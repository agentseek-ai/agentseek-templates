"""Ensure the configured PowerContext Server is ready without blocking deployment."""

from __future__ import annotations

import contextlib
import errno
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVER_PACKAGE = "powercontext[cli,server,seekdb]==1.0.0"
SERVER_READY_TIMEOUT = 60.0
HEALTH_TIMEOUT = 1.5


def _server_url() -> tuple[str, str, int]:
    raw_url = os.environ.get("POWERCONTEXT_URL", "http://127.0.0.1:8000").strip().rstrip("/")
    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SystemExit(f"Invalid POWERCONTEXT_URL: {raw_url!r}")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    health_url = f"{raw_url}/health/ready"
    return raw_url, health_url, port


def _is_local_host(hostname: str) -> bool:
    return hostname in {"localhost", "127.0.0.1", "::1"}


def _probe(health_url: str) -> str:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(health_url, timeout=HEALTH_TIMEOUT) as response:
            return "ready" if 200 <= response.status < 300 else "unready"
    except urllib.error.HTTPError as error:
        if error.code in {502, 503, 504}:
            return "starting"
        raise RuntimeError(
            f"PowerContext Server responded with HTTP {error.code} at {health_url}; "
            "refusing to start another service on the same endpoint"
        ) from error
    except urllib.error.URLError as error:
        reason = error.reason
        if isinstance(reason, OSError) and reason.errno in {
            errno.ECONNREFUSED,
            errno.ECONNRESET,
            errno.EHOSTUNREACH,
            errno.ENETUNREACH,
        }:
            return "unavailable"
        raise RuntimeError(f"Could not check PowerContext Server at {health_url}: {reason}") from error
    except TimeoutError as error:
        raise RuntimeError(f"PowerContext Server health check timed out at {health_url}") from error


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


def _start_local_server(raw_url: str, port: int) -> subprocess.Popen[bytes]:
    parsed = urlparse(raw_url)
    log_path = Path(os.environ.get("POWERCONTEXT_SERVER_LOG", PROJECT_ROOT / ".powercontext-server.log"))
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
    popen_kwargs: dict[str, object] = {
        "cwd": PROJECT_ROOT,
        "stdin": subprocess.DEVNULL,
        "stdout": log_file,
        "stderr": subprocess.STDOUT,
    }
    if os.name == "posix":
        popen_kwargs["start_new_session"] = True
    else:
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        return subprocess.Popen(command, **popen_kwargs)
    except OSError:
        log_file.close()
        raise


def _wait_until_ready(health_url: str, process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + SERVER_READY_TIMEOUT
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"PowerContext Server exited with code {process.returncode}; "
                "see .powercontext-server.log"
            )
        try:
            if _probe(health_url) == "ready":
                return
        except RuntimeError:
            raise
        time.sleep(0.5)
    raise RuntimeError(f"PowerContext Server did not become ready at {health_url}")


def main() -> int:
    raw_url, health_url, port = _server_url()
    parsed = urlparse(raw_url)
    state = _probe(health_url)
    if state == "ready":
        print(f"Reusing PowerContext Server at {raw_url}")
        return 0
    if not _is_local_host(parsed.hostname or ""):
        raise SystemExit(
            f"PowerContext Server is not ready at {raw_url}. "
            "Remote POWERCONTEXT_URL values must be started externally."
        )

    with _startup_lock():
        state = _probe(health_url)
        if state == "ready":
            print(f"Reusing PowerContext Server at {raw_url}")
            return 0
        if state == "starting":
            raise SystemExit(f"PowerContext Server is already starting at {raw_url}; wait and retry")
        print(f"Starting PowerContext Server at {raw_url}")
        process = _start_local_server(raw_url, port)
        _wait_until_ready(health_url, process)
        print(f"PowerContext Server is ready at {raw_url} (PID {process.pid})")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as error:
        print(f"PowerContext startup failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
