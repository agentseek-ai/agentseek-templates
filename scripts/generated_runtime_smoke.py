"""Prove a generated template against published AgentSeek release artifacts."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import platform
import re
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Iterator, Mapping, Sequence
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import BinaryIO, Literal, NamedTuple

from cookiecutter.main import cookiecutter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import runtime_proof  # noqa: E402
from scripts.runtime_proof import ImportRecord, WheelArtifact  # noqa: E402
from scripts.template_runtime_versions import AGENTSEEK_API_VERSIONS  # noqa: E402

FAKE_PROVIDER = ROOT / "scripts" / "fake_openai_server.py"
WINDOWS_JOB_WRAPPER = ROOT / "scripts" / "windows_job_wrapper.py"
PYPI_INDEX = "https://pypi.org/simple"
PROBE_GRAPH_ID = "release_contract_probe"
LAUNCHER_SHUTDOWN_TIMEOUT_SECONDS = 45
FORCE_SHUTDOWN_TIMEOUT_SECONDS = 10
WINDOWS_TASKKILL_TIMEOUT_SECONDS = 10
WINDOWS_TREE_CLEANUP_ERROR = "Windows process tree cleanup could not be verified"
WINDOWS_EMPTY_TREE_MARKER_MAX_BYTES = 512
WINDOWS_EMPTY_TREE_NONCE_PATTERN = re.compile(r"[0-9a-f]{64}")
WINDOWS_CLEANUP_REQUEST_PAYLOAD = b"cleanup\n"
SECONDARY_CLEANUP_NOTE = "Secondary cleanup failure: runtime process cleanup could not be verified"
PROCESS_GROUP_POLL_INTERVAL_SECONDS = 0.05
COMMAND_OUTPUT_TAIL_BYTES = 12_000
COMMAND_OUTPUT_DRAIN_TIMEOUT_SECONDS = 5
COMMAND_CLEANUP_GRACE_SECONDS = 5
COMMAND_CLEANUP_FORCE_SECONDS = 5
CATALOG_PREPARE_TIMEOUT_SECONDS = 180
ENVIRONMENT_CREATE_TIMEOUT_SECONDS = 120
DEPENDENCY_INSTALL_TIMEOUT_SECONDS = 900
TEMPLATE_RENDER_TIMEOUT_SECONDS = 300
CATALOG_PROOF_TIMEOUT_SECONDS = 30
EMBEDDED_SOCKET_PATH_LIMITS = {"darwin": 103, "linux": 107}
EMBEDDED_SOCKET_PATH_ERROR = "embedded seekdb socket path exceeds platform limit"
FIXED_BACKEND_TEMPLATES = frozenset(
    {
        "langchain/agentic-rag",
        "langchain/agentic-rag-hybrid",
        "langchain/cli-remote",
    }
)


class SmokeProfile(NamedTuple):
    graph_id: str
    run_input: Mapping[str, object]
    environment: Mapping[str, str]
    uses_preexisting_embedded_database: bool = False


COMMON_PROVIDER_ENV = {
    "AGENTSEEK_MODEL_PROVIDER": "openai",
    "AGENTSEEK_MODEL": "gpt-4o-mini",
    "OPENAI_API_KEY": "smoke-openai-api-key",
}

CHAT_INPUT = {"messages": [{"role": "user", "content": "Reply with the word smoke."}]}

PROFILES = {
    "deepagents/content-builder": SmokeProfile("content_builder", CHAT_INPUT, {}),
    "deepagents/mcp": SmokeProfile(
        "mcp",
        CHAT_INPUT,
        {"AGENTSEEK_MODEL_API_KEY": "smoke-model-api-key"},
    ),
    # PowerContext recall is fail-open, so the smoke run proceeds with
    # ``status: unavailable`` while no PowerContext Server is running.
    "deepagents/powercontext": SmokeProfile("streaming", CHAT_INPUT, {}),
    "deepagents/research": SmokeProfile(
        "research",
        CHAT_INPUT,
        {"TAVILY_API_KEY": "smoke-tavily-key"},
    ),
    "langchain/agentic-rag": SmokeProfile(
        "rag",
        CHAT_INPUT,
        {"SEEKDB_MODE": "embedded"},
        uses_preexisting_embedded_database=True,
    ),
    "langchain/agentic-rag-hybrid": SmokeProfile(
        "hybrid-rag",
        CHAT_INPUT,
        {
            "AGENTSEEK_API_KEY": "smoke-agentseek-api-key",
            "SILICONFLOW_API_KEY": "smoke-siliconflow-api-key",
            "EMBEDDING_API_KEY": "smoke-embedding-api-key",
        },
    ),
    "langchain/cli-remote": SmokeProfile(
        "agent",
        CHAT_INPUT,
        {"BUB_API_KEY": "smoke-bub-api-key"},
    ),
    "langchain/markdown-messages": SmokeProfile("agent", CHAT_INPUT, {}),
    "langchain/rubric": SmokeProfile("rubric-demo", {"request": {}}, {}),
}

PROBE_MODULE = """from __future__ import annotations

import os
from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class ProbeState(TypedDict, total=False):
    message: str
    sentinel: str


def read_environment(state: ProbeState) -> ProbeState:
    del state
    return {"sentinel": os.environ.get("SENTINEL", "__absent__")}


def prepare_input(payload: dict[str, object]) -> ProbeState:
    message = payload.get("message", "")
    return {"message": message if isinstance(message, str) else str(message)}


def extract_output(result: object, payload: dict[str, object]) -> dict[str, str]:
    del payload
    sentinel = result.get("sentinel") if isinstance(result, dict) else None
    return {"sentinel": sentinel if isinstance(sentinel, str) else "__absent__"}


builder = StateGraph(ProbeState)
builder.add_node("read_environment", read_environment)
builder.add_edge(START, "read_environment")
builder.add_edge("read_environment", END)
graph = builder.compile()
"""

CATALOG_LOCK_SCRIPT = """
import hashlib
import importlib.resources
import json

path = importlib.resources.files("agentseek").joinpath("data/catalog-lock.json")
raw = path.read_bytes()
print(json.dumps({"sha256": hashlib.sha256(raw).hexdigest(), "lock": json.loads(raw)}))
"""

DEFAULT_CATALOG_TEMPLATE_SCRIPT = """
import json
import sys
from pathlib import Path

from agentseek.cli.catalog import load_catalog_lock, prepare_locked_template

template = prepare_locked_template(load_catalog_lock(), sys.argv[1], Path(sys.argv[2]))
print(json.dumps({"template": str(template)}))
"""


class Toolchain(NamedTuple):
    uv: Path
    git: Path
    node: Path
    npm: Path
    sh: Path | None


class PortPlan(NamedTuple):
    context: dict[str, str]
    provider_port: int
    backend_port: int
    expected_ports: tuple[int, ...]
    reservations: tuple[socket.socket, ...]

    def release(self) -> None:
        for reservation in self.reservations:
            reservation.close()


class RuntimeProcesses:
    def __init__(self) -> None:
        self.provider: subprocess.Popen[bytes] | None = None
        self.lifecycle: subprocess.Popen[bytes] | None = None
        self.provider_stream: object | None = None
        self.lifecycle_stream: object | None = None


def build_create_command(
    agentseek_executable: Path,
    *,
    template: str,
    output_root: Path,
    catalog_mode: Literal["source", "default"],
) -> list[str]:
    if catalog_mode != "default":
        raise RuntimeError("source catalog rendering does not use agentseek create")
    return [
        str(agentseek_executable),
        "create",
        template,
        "--no-input",
        "--output-dir",
        str(output_root),
    ]


def build_frontend_install_command(generated: Path, npm_executable: Path) -> list[str] | None:
    if not (generated / "frontend" / "package.json").is_file():
        return None
    return [str(npm_executable), "install"]


def build_runtime_environment(
    platform_name: str,
    machine_name: str,
    run_root: Path,
    requested_mode: Literal["auto", "embedded", "sqlite"],
) -> dict[str, str]:
    normalized_machine = machine_name.lower()
    supports_embedded = platform_name == "linux" or (
        platform_name == "darwin" and normalized_machine in {"arm64", "aarch64"}
    )
    supports_sqlite_profile = platform_name == "win32"
    mode = requested_mode
    if mode == "auto":
        if supports_embedded:
            mode = "embedded"
        elif supports_sqlite_profile:
            mode = "sqlite"
        else:
            raise RuntimeError(f"unsupported runtime platform: {platform_name}/{machine_name}")

    if mode == "embedded":
        if not supports_embedded:
            raise RuntimeError(f"embedded runtime is unavailable: {platform_name}/{machine_name}")
        embed_dir = (run_root / "sdb").resolve()
        socket_path = embed_dir / "run" / "sql.sock"
        if len(os.fsencode(socket_path)) > EMBEDDED_SOCKET_PATH_LIMITS[platform_name]:
            raise RuntimeError(EMBEDDED_SOCKET_PATH_ERROR)
        embed_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
        return {"SEEKDB_EMBED": "true", "SEEKDB_EMBED_DIR": str(embed_dir)}

    if mode == "sqlite":
        if not supports_sqlite_profile:
            raise RuntimeError(f"SQLite release profile is Windows-only: {platform_name}/{machine_name}")
        metadata_path = (run_root / "metadata.sqlite3").resolve()
        metadata_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        return {
            "SEEKDB_EMBED": "false",
            "METADATA_DB_BACKEND": "sqlite",
            "METADATA_DB_URL": f"sqlite+aiosqlite:///{metadata_path.as_posix()}",
        }

    raise RuntimeError(f"unsupported database mode: {requested_mode}")


def _normalized_distribution(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _atomic_stage_bytes(path: Path, payload: bytes) -> None:
    descriptor = -1
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary = Path(temporary_name)
        if os.name != "nt":
            os.fchmod(descriptor, 0o600)
        remaining = memoryview(payload)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("candidate wheel staging made no progress")
            remaining = remaining[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path)
    finally:
        if descriptor >= 0:
            with contextlib.suppress(OSError):
                os.close(descriptor)
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def validate_candidate_wheel(
    path: Path,
    *,
    version: str,
    forbidden_roots: Sequence[Path],
    destination: Path | None = None,
) -> WheelArtifact:
    if not path.is_absolute():
        raise RuntimeError(f"candidate wheel path must be absolute: {path}")
    if path.is_symlink():
        raise RuntimeError(f"candidate wheel path must not be a symlink: {path}")
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise RuntimeError(f"candidate wheel does not exist: {path}") from exc
    if not resolved.is_file():
        raise RuntimeError(f"candidate wheel is not a regular file: {resolved}")
    for root in forbidden_roots:
        repository = root.resolve()
        if resolved == repository or resolved.is_relative_to(repository):
            raise RuntimeError(f"candidate wheel must be outside participating repositories: {resolved}")

    stem_parts = resolved.name.removesuffix(".whl").split("-") if resolved.name.endswith(".whl") else []
    if (
        len(stem_parts) != 5
        or _normalized_distribution(stem_parts[0]) != "agentseek"
        or stem_parts[1] != version
        or stem_parts[2:] != ["py3", "none", "any"]
    ):
        raise RuntimeError(f"candidate wheel filename must match agentseek-{version}-py3-none-any.whl: {resolved.name}")

    try:
        payload = resolved.read_bytes()
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            metadata_names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
            if len(metadata_names) != 1:
                raise RuntimeError("candidate wheel metadata must contain exactly one dist-info/METADATA file")
            message = BytesParser(policy=policy.default).parsebytes(archive.read(metadata_names[0]))
    except zipfile.BadZipFile as exc:
        raise RuntimeError(f"candidate wheel is not a valid wheel archive: {resolved}") from exc

    if _normalized_distribution(str(message.get("Name", ""))) != "agentseek" or message.get("Version") != version:
        raise RuntimeError(f"candidate wheel metadata does not match agentseek=={version}")

    install_path = resolved
    if destination is not None:
        destination.mkdir(mode=0o700, parents=True, exist_ok=True)
        staged_root = destination.resolve(strict=True)
        for root in forbidden_roots:
            repository = root.resolve()
            if staged_root == repository or staged_root.is_relative_to(repository):
                raise RuntimeError(f"candidate wheel staging must be outside participating repositories: {staged_root}")
        install_path = staged_root / resolved.name
        _atomic_stage_bytes(install_path, payload)

    return WheelArtifact(
        name="agentseek",
        version=version,
        filename=resolved.name,
        path=install_path,
        sha256=hashlib.sha256(payload).hexdigest(),
        url=resolved.as_uri(),
    )


def assert_contract_probe(result: Mapping[str, object]) -> str:
    output = result.get("output")
    sentinel = output.get("sentinel") if isinstance(output, dict) else None
    if sentinel != "from-shell":
        raise RuntimeError(f"release contract probe expected from-shell, got {sentinel!r}")
    return sentinel


def require_release_python(major: int, minor: int) -> None:
    if (major, minor) != (3, 12):
        raise RuntimeError(
            f"published runtime proof requires Python 3.12, got Python {major}.{minor}; "
            "invoke it with `uv run --python 3.12 python`"
        )


def _outside_repository(path: Path, *, label: str, forbidden_roots: Sequence[Path]) -> Path:
    resolved = path.resolve()
    for root in forbidden_roots:
        repository = root.resolve()
        if resolved == repository or resolved.is_relative_to(repository):
            raise RuntimeError(f"{label} must be outside participating repositories: {resolved}")
    return resolved


def _external_executable(path: Path, forbidden_roots: Sequence[Path]) -> Path:
    if not path.is_absolute():
        raise RuntimeError(f"resolved executable path is not absolute: {path}")
    selected = path.absolute()
    resolved_target = path.resolve()
    if not selected.is_file():
        raise RuntimeError(f"required executable is not a file: {selected}")
    for root in forbidden_roots:
        repository = root.absolute()
        if selected == repository or selected.is_relative_to(repository):
            raise RuntimeError(f"required executable must be outside participating repositories: {selected}")
    _outside_repository(resolved_target, label="required executable target", forbidden_roots=forbidden_roots)
    return selected


def _resolve_toolchain(forbidden_roots: Sequence[Path]) -> Toolchain:
    def tool(name: str) -> Path:
        return _external_executable(runtime_proof.resolve_executable(name), forbidden_roots)

    return Toolchain(
        uv=tool("uv"),
        git=tool("git"),
        node=tool("node"),
        npm=tool("npm"),
        sh=None if os.name == "nt" else tool("sh"),
    )


def _deduplicated_parents(executables: Sequence[Path]) -> list[Path]:
    result: list[Path] = []
    for executable in executables:
        parent = executable.parent.resolve()
        if parent not in result:
            result.append(parent)
    return result


def _minimal_environment(
    run_root: Path,
    toolchain: Toolchain,
    *,
    environment_bins: Sequence[Path] = (),
) -> dict[str, str]:
    executables = [*environment_bins, toolchain.uv, toolchain.git, toolchain.node, toolchain.npm]
    if toolchain.sh is not None:
        executables.append(toolchain.sh)
    path_entries = _deduplicated_parents(executables)
    return runtime_proof.build_launcher_environment(
        os.environ,
        cache_dir=run_root / "control" / "cache",
        home_dir=run_root / "control" / "home",
        temp_dir=run_root / "control" / "tmp",
        path_entries=path_entries,
        forbidden_roots=[ROOT],
    )


class _BoundedCapture:
    def __init__(self) -> None:
        self._payload = bytearray()
        self._lock = threading.Lock()

    def append(self, chunk: bytes) -> None:
        with self._lock:
            self._payload.extend(chunk)
            excess = len(self._payload) - COMMAND_OUTPUT_TAIL_BYTES
            if excess > 0:
                del self._payload[:excess]

    def snapshot(self) -> bytes:
        with self._lock:
            return bytes(self._payload)


def _private_command_output(run_root: Path, suffix: str) -> Path:
    log_dir = run_root / "command-logs"
    log_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        log_dir.chmod(0o700)
    descriptor, raw_path = tempfile.mkstemp(dir=log_dir, prefix="command-", suffix=suffix)
    try:
        if os.name != "nt":
            os.fchmod(descriptor, 0o600)
    finally:
        os.close(descriptor)
    return Path(raw_path)


def _drain_bounded_output(stream: BinaryIO, capture: _BoundedCapture) -> None:
    try:
        while chunk := stream.read(65_536):
            capture.append(chunk)
    except (OSError, ValueError):
        return
    finally:
        with contextlib.suppress(OSError):
            stream.close()


def _wait_for_output_drains(threads: Sequence[threading.Thread], timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    for thread in threads:
        thread.join(max(0.0, deadline - time.monotonic()))
    return not any(thread.is_alive() for thread in threads)


def _persist_command_tail(path: Path, capture: _BoundedCapture) -> None:
    payload = capture.snapshot()
    with path.open("wb") as stream:
        stream.write(payload)


def _bounded_output_tail(path: Path) -> str:
    with path.open("rb") as stream:
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(max(0, size - COMMAND_OUTPUT_TAIL_BYTES))
        return stream.read(COMMAND_OUTPUT_TAIL_BYTES).decode("utf-8", errors="replace")


def _redact_diagnostic(
    value: str,
    command: Sequence[str],
    environment: Mapping[str, str],
) -> str:
    sensitive_names = re.compile(r"(?:AUTH|CREDENTIAL|KEY|PASSWORD|SECRET|SENTINEL|TOKEN)", re.IGNORECASE)
    redactions = {str(item) for item in command if item}
    for name, item in environment.items():
        if not item:
            continue
        if len(item) >= 4 or sensitive_names.search(name):
            redactions.add(item)
        if "PROXY" not in name.upper():
            continue
        try:
            parsed = urllib.parse.urlsplit(item)
        except ValueError:
            continue
        for credential in (parsed.username, parsed.password):
            if credential:
                redactions.add(credential)
                redactions.add(urllib.parse.unquote(credential))
    for redaction in sorted(redactions, key=len, reverse=True):
        value = value.replace(redaction, "<redacted>")
    return value


def _value_free_tail(
    stdout_path: Path,
    stderr_path: Path,
    command: Sequence[str],
    environment: Mapping[str, str],
) -> str:
    stdout_tail = _bounded_output_tail(stdout_path)
    stderr_tail = _bounded_output_tail(stderr_path)
    tail = "\n".join(part for part in (stdout_tail, stderr_tail) if part).strip()
    return _redact_diagnostic(tail, command, environment)[-COMMAND_OUTPUT_TAIL_BYTES:]


def _run_checked(
    command: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    label: str,
    run_root: Path,
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    if timeout <= 0:
        raise RuntimeError(f"{label} has no positive execution timeout")
    resolved_run_root = run_root.resolve(strict=True)
    resolved_cwd = cwd.resolve(strict=True)
    if not resolved_cwd.is_relative_to(resolved_run_root):
        raise RuntimeError(f"{label} working directory escaped the managed run root")
    stdout_path = _private_command_output(resolved_run_root, ".log")
    stderr_path = _private_command_output(resolved_run_root, ".err")
    stdout_capture = _BoundedCapture()
    stderr_capture = _BoundedCapture()
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    try:
        process = subprocess.Popen(
            list(command),
            cwd=resolved_cwd,
            env=dict(env),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=os.name != "nt",
            creationflags=creationflags,
        )
    except OSError:
        raise RuntimeError(f"{label} could not start") from None

    assert process.stdout is not None and process.stderr is not None
    threads = (
        threading.Thread(target=_drain_bounded_output, args=(process.stdout, stdout_capture), daemon=True),
        threading.Thread(target=_drain_bounded_output, args=(process.stderr, stderr_capture), daemon=True),
    )
    for thread in threads:
        thread.start()

    timed_out = False
    cleanup_failed = False
    try:
        returncode = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            _terminate(
                process,
                cleanup_environment=env,
                grace_timeout=COMMAND_CLEANUP_GRACE_SECONDS,
                force_timeout=COMMAND_CLEANUP_FORCE_SECONDS,
            )
        except BaseException:
            cleanup_failed = True
        returncode = process.poll()

    if not _wait_for_output_drains(threads, COMMAND_OUTPUT_DRAIN_TIMEOUT_SECONDS):
        try:
            _terminate(
                process,
                cleanup_environment=env,
                grace_timeout=COMMAND_CLEANUP_GRACE_SECONDS,
                force_timeout=COMMAND_CLEANUP_FORCE_SECONDS,
            )
        except BaseException:
            cleanup_failed = True
        if not _wait_for_output_drains(threads, PROCESS_GROUP_POLL_INTERVAL_SECONDS):
            cleanup_failed = True

    _persist_command_tail(stdout_path, stdout_capture)
    _persist_command_tail(stderr_path, stderr_capture)

    if timed_out:
        detail = _value_free_tail(stdout_path, stderr_path, command, env)
        message = f"{label} timed out after {timeout:g} seconds"
        if cleanup_failed:
            message += " and command cleanup failed"
        if detail:
            message += f"\noutput tail:\n{detail}"
        raise RuntimeError(message)
    if cleanup_failed:
        raise RuntimeError(f"{label} command cleanup could not be verified")

    stdout = _bounded_output_tail(stdout_path)
    stderr = _bounded_output_tail(stderr_path)
    completed = subprocess.CompletedProcess(list(command), returncode, stdout=stdout, stderr=stderr)
    if returncode != 0:
        detail = _value_free_tail(stdout_path, stderr_path, command, env)
        message = f"{label} failed with status {returncode}"
        if detail:
            message += f"\noutput tail:\n{detail}"
        raise RuntimeError(message)
    return completed


def _port_template_root(
    catalog_mode: Literal["source", "default"],
    *,
    template: str,
    source_template_root: Path,
    launcher_python: Path,
    launcher_environment: Mapping[str, str],
    run_root: Path,
) -> Path:
    if catalog_mode == "source":
        if not source_template_root.is_dir():
            raise RuntimeError(f"registered source template is missing: {source_template_root}")
        return source_template_root.resolve()
    if catalog_mode != "default":
        raise RuntimeError(f"unsupported catalog mode: {catalog_mode}")

    cache_root = run_root / "cookiecutter-cache"
    completed = _run_checked(
        [
            str(launcher_python),
            "-c",
            DEFAULT_CATALOG_TEMPLATE_SCRIPT,
            template,
            str(cache_root),
        ],
        cwd=run_root,
        env=launcher_environment,
        label="prepare packaged default catalog template",
        run_root=run_root,
        timeout=CATALOG_PREPARE_TIMEOUT_SECONDS,
    )
    try:
        payload = json.loads(completed.stdout)
        raw_template = payload["template"]
        if not isinstance(raw_template, str) or not raw_template:
            raise TypeError
        prepared = Path(raw_template).resolve(strict=True)
        resolved_cache = cache_root.resolve(strict=True)
    except (json.JSONDecodeError, KeyError, OSError, TypeError) as exc:
        raise RuntimeError("launcher returned an invalid packaged template path") from exc
    if not prepared.is_relative_to(resolved_cache) or not (prepared / "cookiecutter.json").is_file():
        raise RuntimeError("launcher packaged template path escaped its managed cache")
    return prepared


def _environment_python(environment_root: Path) -> Path:
    relative = Path("Scripts/python.exe") if os.name == "nt" else Path("bin/python")
    return environment_root / relative


def _environment_executable(environment_root: Path, name: str) -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    relative = Path("Scripts") if os.name == "nt" else Path("bin")
    return environment_root / relative / f"{name}{suffix}"


def _create_launcher_environment(
    run_root: Path,
    toolchain: Toolchain,
    launcher_artifact: WheelArtifact,
    env: Mapping[str, str],
) -> tuple[Path, Path, Path]:
    launcher_root = run_root / "launcher-venv"
    _run_checked(
        [str(toolchain.uv), "venv", "--python", sys.executable, str(launcher_root)],
        cwd=run_root,
        env=env,
        label="create launcher virtual environment",
        run_root=run_root,
        timeout=ENVIRONMENT_CREATE_TIMEOUT_SECONDS,
    )
    launcher_python = _environment_python(launcher_root)
    _run_checked(
        [
            str(toolchain.uv),
            "pip",
            "install",
            "--python",
            str(launcher_python),
            "--no-cache",
            "--no-config",
            "--default-index",
            PYPI_INDEX,
            str(launcher_artifact.path),
        ],
        cwd=run_root,
        env=env,
        label="install published AgentSeek launcher",
        run_root=run_root,
        timeout=DEPENDENCY_INSTALL_TIMEOUT_SECONDS,
    )
    agentseek_executable = _environment_executable(launcher_root, "agentseek")
    if not launcher_python.is_file() or not agentseek_executable.is_file():
        raise RuntimeError("launcher installation did not create the expected Python and agentseek executables")
    return launcher_root, launcher_python, agentseek_executable


def _reserve_port(preferred: int | None = None) -> tuple[socket.socket, int]:
    reservation = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if os.name == "nt":
            reservation.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            reservation.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        reservation.bind(("127.0.0.1", preferred or 0))
        reservation.listen(1)
    except OSError:
        reservation.close()
        requested = str(preferred) if preferred is not None else "a dynamic port"
        raise RuntimeError(f"failed to reserve {requested} on 127.0.0.1") from None
    return reservation, int(reservation.getsockname()[1])


def _allocate_ports(template: str, template_root: Path) -> PortPlan:
    try:
        raw_context = json.loads((template_root / "cookiecutter.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{template}: could not read cookiecutter port context") from exc
    if not isinstance(raw_context, dict):
        raise RuntimeError(f"{template}: cookiecutter context is not an object")

    reservations: list[socket.socket] = []
    allocated: list[int] = []
    context: dict[str, str] = {}
    try:
        fixed_backend = template in FIXED_BACKEND_TEMPLATES
        backend_port: int | None = None
        if fixed_backend:
            reservation, backend_port = _reserve_port(2024)
            reservations.append(reservation)
            allocated.append(backend_port)

        reservation, provider_port = _reserve_port()
        reservations.append(reservation)
        allocated.append(provider_port)

        for name in sorted(raw_context):
            if not name.endswith("_port"):
                continue
            reservation, port = _reserve_port()
            reservations.append(reservation)
            allocated.append(port)
            context[name] = str(port)

        if backend_port is None:
            rendered_backend = context.get("langgraph_port")
            if rendered_backend is None:
                raise RuntimeError(f"{template}: dynamic backend profile has no langgraph_port")
            backend_port = int(rendered_backend)

        if len(set(allocated)) != len(allocated):
            raise RuntimeError(f"{template}: runtime ports are not distinct")
        return PortPlan(
            context=context,
            provider_port=provider_port,
            backend_port=backend_port,
            expected_ports=tuple(allocated),
            reservations=tuple(reservations),
        )
    except BaseException:
        for reservation in reservations:
            reservation.close()
        raise


def _write_cookiecutter_config(home_dir: Path, run_root: Path, context: Mapping[str, str]) -> Path:
    config_path = home_dir / ".cookiecutterrc"
    lines = [
        f"cookiecutters_dir: {json.dumps(str(run_root / 'cookiecutter-cache'))}",
        f"replay_dir: {json.dumps(str(run_root / 'cookiecutter-replay'))}",
        "default_context:",
    ]
    lines.extend(f"  {name}: {json.dumps(value)}" for name, value in sorted(context.items()))
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return config_path


def _source_context(port_context: Mapping[str, str]) -> dict[str, str]:
    result = dict(port_context)
    result.update(
        {
            "_agentseek_source_path": "",
            "_agentseek_source_path_posix": "",
            "_agentseek_source_path_shell": "",
            "_agentseek_source_url": "https://github.com/ob-labs/agentseek.git",
        }
    )
    return result


def _render_source(
    template_root: Path,
    output_root: Path,
    context: Mapping[str, str],
    config_file: Path,
) -> Path:
    generated = cookiecutter(
        template=str(template_root),
        output_dir=str(output_root),
        no_input=True,
        extra_context=_source_context(context),
        config_file=str(config_file),
    )
    path = Path(generated).resolve()
    if not path.is_dir() or not path.is_relative_to(output_root.resolve()):
        raise RuntimeError(f"source render returned an invalid generated path: {path}")
    return path


def _render_default(
    command: Sequence[str],
    *,
    output_root: Path,
    env: Mapping[str, str],
    run_root: Path,
) -> Path:
    before = {path.resolve() for path in output_root.iterdir() if path.is_dir()}
    _run_checked(
        command,
        cwd=output_root,
        env=env,
        label="render installed default catalog template",
        run_root=run_root,
        timeout=TEMPLATE_RENDER_TIMEOUT_SECONDS,
    )
    created = [path.resolve() for path in output_root.iterdir() if path.is_dir() and path.resolve() not in before]
    if len(created) != 1:
        raise RuntimeError(f"default catalog render created {len(created)} project directories; expected one")
    return created[0]


def _write_generated_env(generated: Path) -> None:
    example = generated / ".env.example"
    if not example.is_file():
        raise RuntimeError(f"generated project has no .env.example: {generated}")
    content = example.read_text(encoding="utf-8")
    if content and not content.endswith("\n"):
        content += "\n"
    content += "SENTINEL=from-dotenv\n"
    (generated / ".env").write_text(content, encoding="utf-8")


def _generated_package(generated: Path) -> tuple[str, Path]:
    try:
        project = tomllib.loads((generated / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        project_name = project["name"]
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as exc:
        raise RuntimeError(f"generated project has invalid project metadata: {generated}") from exc
    if not isinstance(project_name, str) or not project_name:
        raise RuntimeError("generated project name is missing")
    package_name = re.sub(r"[-.]+", "_", project_name)
    package_root = generated / "src" / package_name
    if not package_root.is_dir():
        raise RuntimeError(f"generated package directory is missing: {package_root}")
    return package_name, package_root


def _install_contract_probe(generated: Path, original_graph_id: str) -> None:
    package_name, package_root = _generated_package(generated)
    manifest_path = generated / "langgraph.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"generated project has invalid langgraph.json: {generated}") from exc
    graphs = manifest.get("graphs") if isinstance(manifest, dict) else None
    if not isinstance(graphs, dict) or original_graph_id not in graphs:
        raise RuntimeError(f"generated manifest does not expose required graph {original_graph_id!r}")
    if PROBE_GRAPH_ID in graphs:
        raise RuntimeError(f"generated manifest already contains reserved graph {PROBE_GRAPH_ID!r}")

    (package_root / "_release_contract_probe.py").write_text(PROBE_MODULE, encoding="utf-8")
    module_path = f"./src/{package_name}/_release_contract_probe.py"
    graphs[PROBE_GRAPH_ID] = {
        "graph": f"{module_path}:graph",
        "prepare_input": f"{module_path}:prepare_input",
        "extract_output": f"{module_path}:extract_output",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _install_generated_project(
    generated: Path,
    api_artifact: WheelArtifact,
    toolchain: Toolchain,
    env: Mapping[str, str],
    template: str,
    run_root: Path,
) -> None:
    artifact_dir = api_artifact.path.parent.resolve()
    _run_checked(
        [
            str(toolchain.uv),
            "sync",
            "--python",
            sys.executable,
            "--no-cache",
            "--no-config",
            "--default-index",
            PYPI_INDEX,
            "--find-links",
            str(artifact_dir),
        ],
        cwd=generated,
        env=env,
        label=f"{template}: install generated Python environment",
        run_root=run_root,
        timeout=DEPENDENCY_INSTALL_TIMEOUT_SECONDS,
    )
    frontend_command = build_frontend_install_command(generated, toolchain.npm)
    if frontend_command is not None:
        frontend_root = generated / "frontend"
        _run_checked(
            frontend_command,
            cwd=frontend_root,
            env=env,
            label=f"{template}: install generated frontend",
            run_root=run_root,
            timeout=DEPENDENCY_INSTALL_TIMEOUT_SECONDS,
        )
        if not (frontend_root / "node_modules").is_dir():
            raise RuntimeError(f"{template}: npm exited successfully without creating frontend/node_modules")


def _validate_api_lock(generated: Path, artifact: WheelArtifact) -> dict[str, str]:
    lock_path = generated / "uv.lock"
    try:
        payload = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise RuntimeError(f"generated project has no valid uv.lock: {generated}") from exc
    packages = payload.get("package")
    matches = (
        [item for item in packages if isinstance(item, dict) and item.get("name") == "agentseek-api"]
        if isinstance(packages, list)
        else []
    )
    if len(matches) != 1 or matches[0].get("version") != artifact.version:
        versions = [item.get("version") for item in matches]
        raise RuntimeError(f"generated uv.lock does not pin agentseek-api=={artifact.version}: {versions}")

    package = matches[0]
    wheels = package.get("wheels")
    expected_hash = f"sha256:{artifact.sha256}"
    matching_wheels: list[Mapping[str, object]] = []
    if isinstance(wheels, list):
        for wheel in wheels:
            if not isinstance(wheel, dict):
                continue
            location = wheel.get("url") or wheel.get("path")
            if not isinstance(location, str):
                continue
            filename = Path(urllib.parse.unquote(urllib.parse.urlparse(location).path)).name
            if filename != artifact.filename:
                continue
            if wheel.get("hash") == expected_hash:
                matching_wheels.append(wheel)
                continue
            if "path" not in wheel or wheel.get("hash") is not None:
                continue
            source = package.get("source")
            registry = source.get("registry") if isinstance(source, dict) else None
            if not isinstance(registry, str) or not registry:
                continue
            if registry.startswith("file:"):
                registry_path = Path(urllib.parse.unquote(urllib.parse.urlparse(registry).path))
            elif "://" in registry:
                continue
            else:
                registry_path = Path(registry)
                if not registry_path.is_absolute():
                    registry_path = generated / registry_path
            referenced_wheel = (registry_path / location).resolve()
            if referenced_wheel != artifact.path.resolve() or not referenced_wheel.is_file():
                continue
            if hashlib.sha256(referenced_wheel.read_bytes()).hexdigest() == artifact.sha256:
                matching_wheels.append(wheel)
    if len(matching_wheels) != 1:
        raise RuntimeError(
            f"generated uv.lock does not contain verified universal wheel {artifact.filename} with {expected_hash}"
        )
    return {
        "version": artifact.version,
        "wheel_filename": artifact.filename,
        "wheel_sha256": artifact.sha256,
    }


def _collect_import(
    python: Path,
    distribution: str,
    module: str,
    environment_root: Path,
    expected_version: str,
) -> ImportRecord:
    record = runtime_proof.collect_import_record(python, distribution, module, environment_root)
    if record.version != expected_version:
        raise RuntimeError(f"{distribution} import version is {record.version}, expected {expected_version}")
    python_path = Path(record.python).absolute()
    if not python_path.is_relative_to(environment_root.absolute()):
        raise RuntimeError(f"{distribution} interpreter is outside expected environment: {record.python}")
    return record


def _read_catalog_proof(
    launcher_python: Path,
    launcher_env: Mapping[str, str],
    launcher_root: Path,
    template: str,
    catalog_mode: Literal["source", "default"],
) -> dict[str, object]:
    completed = _run_checked(
        [str(launcher_python), "-c", CATALOG_LOCK_SCRIPT],
        cwd=launcher_root,
        env=launcher_env,
        label="read packaged AgentSeek catalog lock",
        run_root=launcher_root.parent,
        timeout=CATALOG_PROOF_TIMEOUT_SECONDS,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("launcher returned invalid catalog-lock proof") from exc
    lock = payload.get("lock") if isinstance(payload, dict) else None
    digest = payload.get("sha256") if isinstance(payload, dict) else None
    if not isinstance(lock, dict) or not isinstance(digest, str) or len(digest) != 64:
        raise RuntimeError("launcher returned incomplete catalog-lock proof")
    coordinate_names = (
        "catalog_repository",
        "catalog_commit",
        "catalog_release",
        "core_repository",
        "core_commit",
        "core_release",
    )
    coordinates: dict[str, object] = {"sha256": digest}
    for name in coordinate_names:
        value = lock.get(name)
        if not isinstance(value, str) or not value:
            raise RuntimeError(f"packaged catalog lock has no {name}")
        coordinates[name] = value
    templates = lock.get("templates")
    digests = lock.get("template_digests")
    template_digest = digests.get(template) if isinstance(digests, dict) else None
    if catalog_mode == "default":
        if not isinstance(templates, dict) or template not in templates:
            raise RuntimeError(f"default catalog lock does not contain rendered template {template}")
        if not isinstance(template_digest, str) or len(template_digest) != 64:
            raise RuntimeError(f"default catalog lock has no digest for rendered template {template}")
    if isinstance(template_digest, str):
        coordinates["template_digest"] = template_digest
    return coordinates


def _child_environment(
    base: Mapping[str, str],
    profile: SmokeProfile,
    run_root: Path,
    provider_port: int,
    backend_port: int,
    runtime_environment: Mapping[str, str],
) -> dict[str, str]:
    provider_url = f"http://127.0.0.1:{provider_port}/v1"
    backend_url = f"http://127.0.0.1:{backend_port}"
    database_token = hashlib.sha256(str(run_root.resolve()).encode()).hexdigest()[:12]
    api_database_name = f"smoke_api_{database_token}"
    seekdb_database_name = f"smoke_seekdb_{database_token}"
    database_root = (run_root / "databases").resolve()
    database_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    result = dict(base)
    result.update(COMMON_PROVIDER_ENV)
    result.update(profile.environment)
    result.update(
        {
            "SENTINEL": "from-shell",
            "NO_PROXY": "127.0.0.1,localhost",
            "no_proxy": "127.0.0.1,localhost",
            "LANGSMITH_TRACING": "false",
            "LANGCHAIN_TRACING_V2": "false",
            "AGENTSEEK_OTEL_ENABLED": "false",
            "OPENAI_API_BASE": provider_url,
            "OPENAI_BASE_URL": provider_url,
            "AGENTSEEK_API_BASE": provider_url,
            "BUB_API_BASE": provider_url,
            "EMBEDDING_BASE_URL": provider_url,
            "VLM_BASE_URL": provider_url,
            "ANTHROPIC_API_URL": provider_url,
            "GOOGLE_API_BASE": provider_url,
            "OPENAI_MODEL": "gpt-4o-mini",
            "BUB_MODEL": "openai:gpt-4o-mini",
            "LANGCHAIN_REMOTE_MODEL": "openai:gpt-4o-mini",
            "LANGGRAPH_URL": backend_url,
            "LANGGRAPH_HOST": "127.0.0.1",
            "FRONTEND_HOST": "127.0.0.1",
            "SEEKDB_PATH": str(database_root / "rag-seekdb"),
            "SEEKDB_DB_NAME": seekdb_database_name,
            "OCEANBASE_DB_NAME": api_database_name,
            "SEEKDB_HOST": "127.0.0.1",
            "SEEKDB_PORT": "1",
        }
    )
    result.update(runtime_environment)
    if profile.uses_preexisting_embedded_database:
        embed_dir = result.get("SEEKDB_EMBED_DIR")
        if result.get("SEEKDB_EMBED") != "true" or not embed_dir:
            raise RuntimeError("profile requires an embedded seekdb runtime")
        result.update(
            {
                "SEEKDB_PATH": embed_dir,
                "SEEKDB_DB_NAME": "test",
                "OCEANBASE_DB_NAME": "test",
            }
        )
    return result


def _request(url: str, *, method: str = "GET", payload: Mapping[str, object] | None = None) -> dict[str, object]:
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=body, method=method)
    request.add_header("content-type", "application/json")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=30) as response:  # noqa: S310 - loopback release-proof target
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[-4000:]
        raise RuntimeError(f"runtime request failed with HTTP {exc.code}: {url}\n{detail}") from exc
    if not isinstance(result, dict):
        raise RuntimeError(f"runtime request returned a non-object response: {url}")
    return result


def _read_log(process: subprocess.Popen[bytes]) -> str:
    log_path = getattr(process, "_agentseek_log_path", None)
    if not log_path:
        return "(process log unavailable)"
    path = Path(log_path)
    if not path.exists():
        return "(log file unavailable)"
    raw_command = process.args
    if isinstance(raw_command, (str, bytes)):
        command = (os.fsdecode(raw_command),)
    else:
        command = tuple(os.fsdecode(item) for item in raw_command)
    environment = dict(getattr(process, "_agentseek_environment", {}))
    diagnostic_environment = getattr(process, "_agentseek_diagnostic_environment", {})
    if isinstance(diagnostic_environment, Mapping):
        environment.update(diagnostic_environment)
    diagnostic = _bounded_output_tail(path)
    return _redact_diagnostic(diagnostic, command, environment)[-COMMAND_OUTPUT_TAIL_BYTES:]


def _wait_for_port(port: int, processes: Sequence[subprocess.Popen[bytes]], deadline: float) -> None:
    while time.monotonic() < deadline:
        for process in processes:
            if process.poll() is not None:
                raise RuntimeError(
                    f"runtime process exited with status {process.returncode} before acquiring port {port}\n"
                    f"{_read_log(process)}"
                )
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                return
        except OSError:
            time.sleep(0.25)
    logs = "\n".join(_read_log(process) for process in processes)
    raise TimeoutError(f"expected runtime service did not acquire 127.0.0.1:{port}\n{logs}")


def _wait_for_runtime(
    base_url: str,
    lifecycle: subprocess.Popen[bytes],
    provider: subprocess.Popen[bytes],
    expected_ports: Sequence[int],
    timeout: float = 120,
) -> None:
    deadline = time.monotonic() + timeout
    for port in expected_ports:
        _wait_for_port(port, (lifecycle, provider), deadline)
    while time.monotonic() < deadline:
        for process, label in ((lifecycle, "agentseek dev"), (provider, "fake provider")):
            if process.poll() is not None:
                raise RuntimeError(f"{label} exited with status {process.returncode}\n{_read_log(process)}")
        try:
            _request(f"{base_url}/health")
            return
        except (OSError, RuntimeError, urllib.error.URLError):
            time.sleep(0.5)
    raise TimeoutError(f"API did not become ready at {base_url}/health\n{_read_log(lifecycle)}")


def _start_process(
    command: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    log_path: Path,
    windows_supervisor_python: Path | None = None,
) -> tuple[subprocess.Popen[bytes], object]:
    launch_command = list(command)
    marker: Path | None = None
    nonce: str | None = None
    if os.name == "nt":
        if windows_supervisor_python is None:
            raise RuntimeError("Windows runtime launch requires a Job Object supervisor")
        supervisor_python = _external_executable(windows_supervisor_python, [ROOT])
        try:
            wrapper = WINDOWS_JOB_WRAPPER.resolve(strict=True)
        except OSError as exc:
            raise RuntimeError("Windows Job Object wrapper is unavailable") from exc
        if not wrapper.is_file():
            raise RuntimeError("Windows Job Object wrapper is invalid")
        marker_id = secrets.token_hex(16)
        nonce = secrets.token_hex(32)
        if WINDOWS_EMPTY_TREE_NONCE_PATTERN.fullmatch(nonce) is None:
            raise RuntimeError("Windows Job Object nonce generation failed")
        marker = log_path.with_name(f".{log_path.name}.{marker_id}.tree-empty.json")
        if marker.exists() or marker.is_symlink():
            raise RuntimeError("Windows Job Object marker already exists")
        launch_command = [
            str(supervisor_python),
            str(wrapper),
            str(marker),
            *launch_command,
        ]

    stream = log_path.open("wb")
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    try:
        process = subprocess.Popen(
            launch_command,
            cwd=cwd,
            env=dict(env),
            stdin=subprocess.PIPE if os.name == "nt" else None,
            stdout=stream,
            stderr=subprocess.STDOUT,
            start_new_session=os.name != "nt",
            creationflags=creationflags,
        )
    except BaseException:
        stream.close()
        raise
    if marker is not None and nonce is not None:
        nonce_payload = f"{nonce}\n".encode("ascii")
        try:
            if process.stdin is None or process.stdin.write(nonce_payload) != len(nonce_payload):
                raise OSError("Windows Job Object nonce write was incomplete")
            process.stdin.flush()
            process.stdin.close()
        except BaseException as exc:
            cleanup_failed = False
            if process.stdin is not None:
                try:
                    process.stdin.close()
                except BaseException:
                    cleanup_failed = True
            try:
                process.kill()
            except OSError:
                cleanup_failed = True
            try:
                process.wait(timeout=FORCE_SHUTDOWN_TIMEOUT_SECONDS)
            except (OSError, subprocess.TimeoutExpired):
                cleanup_failed = True
            try:
                stream.close()
            except BaseException:
                cleanup_failed = True
            handoff_error = RuntimeError("Windows Job Object nonce handoff failed")
            if cleanup_failed:
                handoff_error.add_note(SECONDARY_CLEANUP_NOTE)
            raise handoff_error from exc
    process._agentseek_log_path = str(log_path)  # type: ignore[attr-defined]
    process._agentseek_environment = dict(env)  # type: ignore[attr-defined]
    if marker is not None and nonce is not None:
        process._agentseek_windows_empty_tree_marker = str(marker)  # type: ignore[attr-defined]
        process._agentseek_windows_empty_tree_nonce = nonce  # type: ignore[attr-defined]
        process._agentseek_diagnostic_environment = {  # type: ignore[attr-defined]
            "AGENTSEEK_WINDOWS_JOB_MARKER": str(marker),
            "AGENTSEEK_WINDOWS_JOB_NONCE": nonce,
        }
    return process, stream


def _wait_for_posix_group_exit(process: subprocess.Popen[bytes], timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while True:
        leader_reaped = process.poll() is not None
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            if leader_reaped:
                # Once the direct child is reaped, EPERM proves that no
                # remaining group member is signalable by this harness.
                return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(PROCESS_GROUP_POLL_INTERVAL_SECONDS)


def _windows_cleanup_tool(environment: Mapping[str, str]) -> tuple[Path, dict[str, str]]:
    selected_name = next(
        (name for name in ("SystemRoot", "SYSTEMROOT", "WINDIR") if environment.get(name)),
        None,
    )
    if selected_name is None:
        raise RuntimeError("Windows cleanup environment has no system root")
    raw_root = environment[selected_name]
    system_root = Path(raw_root)
    if not system_root.is_absolute():
        raise RuntimeError("Windows cleanup system root is not absolute")
    try:
        taskkill = (system_root / "System32" / "taskkill.exe").resolve(strict=True)
    except OSError as exc:
        raise RuntimeError("Windows cleanup taskkill is unavailable") from exc
    if not taskkill.is_file() or taskkill.is_relative_to(ROOT.resolve()):
        raise RuntimeError("Windows cleanup taskkill path is invalid")
    return taskkill, {selected_name: raw_root}


def _windows_empty_tree_marker_status(process: subprocess.Popen[bytes]) -> str:
    raw_path = getattr(process, "_agentseek_windows_empty_tree_marker", None)
    expected_nonce = getattr(process, "_agentseek_windows_empty_tree_nonce", None)
    if (
        not isinstance(raw_path, str)
        or not raw_path
        or not isinstance(expected_nonce, str)
        or WINDOWS_EMPTY_TREE_NONCE_PATTERN.fullmatch(expected_nonce) is None
    ):
        return "marker-metadata-invalid"
    path = Path(raw_path)
    try:
        if not path.is_absolute():
            return "marker-path-invalid"
        if path.is_symlink():
            return "marker-symlink"
        if not path.exists():
            return "marker-missing"
        if not path.is_file():
            return "marker-not-file"
        with path.open("rb") as stream:
            raw = stream.read(WINDOWS_EMPTY_TREE_MARKER_MAX_BYTES + 1)
        if len(raw) > WINDOWS_EMPTY_TREE_MARKER_MAX_BYTES:
            return "marker-oversized"
        payload = json.loads(raw)
    except OSError:
        return "marker-unreadable"
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "marker-malformed"
    if not isinstance(payload, dict) or set(payload) != {"nonce", "owner_pid", "schema_version", "status"}:
        return "marker-schema-invalid"
    if payload["nonce"] != expected_nonce:
        return "marker-nonce-mismatch"
    # Windows virtual-environment launchers may retain an outer process while
    # a child interpreter executes the wrapper. The secret nonce authenticates
    # the marker; the positive PID remains an auditable wrapper identity.
    if type(payload["owner_pid"]) is not int or payload["owner_pid"] <= 0:
        return "marker-owner-invalid"
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        return "marker-version-invalid"
    if payload["status"] != "empty":
        return "marker-status-invalid"
    return "marker-valid"


def _windows_empty_tree_marker_proves_empty(process: subprocess.Popen[bytes]) -> bool:
    return _windows_empty_tree_marker_status(process) == "marker-valid"


def _is_windows_job_wrapper(process: subprocess.Popen[bytes]) -> bool:
    return (
        getattr(process, "_agentseek_windows_empty_tree_marker", None) is not None
        or getattr(process, "_agentseek_windows_empty_tree_nonce", None) is not None
    )


def _windows_cleanup_request_path(marker: Path) -> Path:
    return marker.with_name(f"{marker.name}.cleanup-request")


def _write_windows_cleanup_request(process: subprocess.Popen[bytes]) -> None:
    marker_value = getattr(process, "_agentseek_windows_empty_tree_marker", None)
    if not isinstance(marker_value, str):
        raise RuntimeError(WINDOWS_TREE_CLEANUP_ERROR)
    marker = Path(marker_value)
    request = _windows_cleanup_request_path(marker)
    try:
        with request.open("xb") as stream:
            stream.write(WINDOWS_CLEANUP_REQUEST_PAYLOAD)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        # A pre-existing request can only stop the owned Job early. It cannot
        # forge the nonce-bearing empty-tree marker, so continue fail-closed.
        pass
    except OSError as exc:
        raise RuntimeError(WINDOWS_TREE_CLEANUP_ERROR) from exc


def _force_windows_wrapper_exit(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        with contextlib.suppress(OSError):
            process.kill()
    with contextlib.suppress(OSError, subprocess.TimeoutExpired):
        process.wait(timeout=FORCE_SHUTDOWN_TIMEOUT_SECONDS)


def _terminate_windows_job_wrapper(process: subprocess.Popen[bytes]) -> None:
    marker_value = getattr(process, "_agentseek_windows_empty_tree_marker", None)
    request = _windows_cleanup_request_path(Path(marker_value)) if isinstance(marker_value, str) else None
    try:
        _write_windows_cleanup_request(process)
    except RuntimeError:
        _force_windows_wrapper_exit(process)
        raise RuntimeError(WINDOWS_TREE_CLEANUP_ERROR) from None
    wait_outcome = "wrapper-exit-unknown"
    try:
        exit_code = process.wait(timeout=LAUNCHER_SHUTDOWN_TIMEOUT_SECONDS)
        wait_outcome = "wrapper-exit-zero" if exit_code == 0 else "wrapper-exit-nonzero"
    except subprocess.TimeoutExpired:
        wait_outcome = "wrapper-timeout"
        _force_windows_wrapper_exit(process)
    except OSError:
        wait_outcome = "wrapper-wait-error"
        _force_windows_wrapper_exit(process)
    marker_outcome = _windows_empty_tree_marker_status(process)
    if marker_outcome == "marker-valid":
        return
    request_outcome = (
        "request-pending" if request is not None and (request.exists() or request.is_symlink()) else "request-consumed"
    )
    error = RuntimeError(WINDOWS_TREE_CLEANUP_ERROR)
    error.add_note(f"Windows cleanup diagnostic: {request_outcome}, {wait_outcome}, {marker_outcome}.")
    log_tail = _read_log(process)
    if log_tail:
        error.add_note(f"Windows wrapper log tail (redacted):\n{log_tail}")
    raise error


def _terminate_windows_process(process: subprocess.Popen[bytes], environment: Mapping[str, str]) -> None:
    if process.poll() is not None:
        if _windows_empty_tree_marker_proves_empty(process):
            return
        raise RuntimeError(WINDOWS_TREE_CLEANUP_ERROR)
    if _is_windows_job_wrapper(process):
        _terminate_windows_job_wrapper(process)
        return
    try:
        taskkill, cleanup_environment = _windows_cleanup_tool(environment)
    except RuntimeError:
        with contextlib.suppress(OSError):
            process.kill()
        with contextlib.suppress(OSError, subprocess.TimeoutExpired):
            process.wait(timeout=FORCE_SHUTDOWN_TIMEOUT_SECONDS)
        if _windows_empty_tree_marker_proves_empty(process):
            return
        raise RuntimeError(WINDOWS_TREE_CLEANUP_ERROR) from None
    try:
        completed = subprocess.run(
            [str(taskkill), "/PID", str(process.pid), "/T", "/F"],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=taskkill.parent,
            env=cleanup_environment,
            timeout=WINDOWS_TASKKILL_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        completed = None
    if completed is None or completed.returncode != 0:
        if process.poll() is None:
            with contextlib.suppress(OSError):
                process.kill()
        with contextlib.suppress(OSError, subprocess.TimeoutExpired):
            process.wait(timeout=FORCE_SHUTDOWN_TIMEOUT_SECONDS)
        if _windows_empty_tree_marker_proves_empty(process):
            return
        raise RuntimeError(WINDOWS_TREE_CLEANUP_ERROR)
    try:
        process.wait(timeout=FORCE_SHUTDOWN_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(OSError):
            process.kill()
        with contextlib.suppress(OSError, subprocess.TimeoutExpired):
            process.wait(timeout=FORCE_SHUTDOWN_TIMEOUT_SECONDS)
        if _windows_empty_tree_marker_proves_empty(process):
            return
        raise RuntimeError(WINDOWS_TREE_CLEANUP_ERROR) from None


def _terminate(
    process: subprocess.Popen[bytes],
    *,
    cleanup_environment: Mapping[str, str] | None = None,
    grace_timeout: float = LAUNCHER_SHUTDOWN_TIMEOUT_SECONDS,
    force_timeout: float = FORCE_SHUTDOWN_TIMEOUT_SECONDS,
) -> None:
    if os.name == "nt":
        _terminate_windows_process(process, cleanup_environment or {})
        return

    group_missing = False
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        group_missing = True
    group_exited = group_missing or _wait_for_posix_group_exit(process, grace_timeout)
    if not group_exited:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        if not _wait_for_posix_group_exit(process, force_timeout):
            raise RuntimeError("owned process group did not exit after forced cleanup")

    if process.poll() is None:
        try:
            process.wait(timeout=force_timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=force_timeout)


def _terminate_processes(
    lifecycle: subprocess.Popen[bytes] | None,
    provider: subprocess.Popen[bytes] | None,
    *,
    cleanup_environment: Mapping[str, str] | None = None,
) -> None:
    first_error: BaseException | None = None
    for process in (lifecycle, provider):
        if process is None:
            continue
        try:
            _terminate(process, cleanup_environment=cleanup_environment)
        except BaseException as exc:
            if first_error is None:
                first_error = exc
    if first_error is not None:
        raise first_error


def _cleanup_runtime_processes(
    resources: RuntimeProcesses,
    cleanup_environment: Mapping[str, str],
    primary_error: BaseException | None,
) -> None:
    first_error: BaseException | None = None
    try:
        _terminate_processes(
            resources.lifecycle,
            resources.provider,
            cleanup_environment=cleanup_environment,
        )
    except BaseException as exc:
        first_error = exc
    for stream in (resources.lifecycle_stream, resources.provider_stream):
        if stream is None:
            continue
        try:
            stream.close()  # type: ignore[attr-defined]
        except BaseException as exc:
            if first_error is None:
                first_error = exc
    if first_error is None:
        return
    if primary_error is not None:
        primary_error.add_note(SECONDARY_CLEANUP_NOTE)
        return
    raise first_error


@contextlib.contextmanager
def _managed_runtime_processes(
    cleanup_environment: Mapping[str, str],
) -> Iterator[RuntimeProcesses]:
    resources = RuntimeProcesses()
    primary_error: BaseException | None = None
    try:
        yield resources
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        _cleanup_runtime_processes(resources, cleanup_environment, primary_error)


def _run_graph(
    base_url: str,
    *,
    graph_id: str,
    run_input: Mapping[str, object],
) -> tuple[dict[str, object], dict[str, str]]:
    assistant = _request(
        f"{base_url}/assistants",
        method="POST",
        payload={"name": f"runtime-proof-{graph_id}", "graph_id": graph_id},
    )
    assistant_id = assistant.get("assistant_id")
    if not isinstance(assistant_id, str) or not assistant_id:
        raise RuntimeError(f"assistant creation returned no assistant_id for graph {graph_id}")
    thread = _request(
        f"{base_url}/threads",
        method="POST",
        payload={"metadata": {"suite": "published-runtime-proof", "graph_id": graph_id}},
    )
    thread_id = thread.get("thread_id")
    if not isinstance(thread_id, str) or not thread_id:
        raise RuntimeError(f"thread creation returned no thread_id for graph {graph_id}")
    run = _request(
        f"{base_url}/threads/{thread_id}/runs",
        method="POST",
        payload={"assistant_id": assistant_id, "input": dict(run_input)},
    )
    run_id = run.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise RuntimeError(f"run creation returned no run_id for graph {graph_id}")
    result = _request(f"{base_url}/threads/{thread_id}/runs/{run_id}/wait")
    status = result.get("status")
    if status != "success":
        raise RuntimeError(f"graph {graph_id} run did not succeed: {result}")
    return result, {"graph_id": graph_id, "run_id": run_id, "status": status}


def _artifact_record(artifact: WheelArtifact, source: str) -> dict[str, str]:
    return {
        "name": artifact.name,
        "version": artifact.version,
        "filename": artifact.filename,
        "sha256": artifact.sha256,
        "source": source,
        "url": artifact.url,
    }


def _import_record(record: ImportRecord) -> dict[str, str]:
    return {
        "distribution": record.distribution,
        "version": record.version,
        "module_path": record.module_path,
        "python": record.python,
    }


def _require_value_free_proof(payload: Mapping[str, object], child_environment: Mapping[str, str]) -> None:
    runtime = payload.get("runtime")
    expected_runtime_fields = {"provider_port", "backend_port", "expected_ports"}
    if not isinstance(runtime, dict) or set(runtime) != expected_runtime_fields:
        raise RuntimeError("proof payload contains invalid runtime port record")
    provider_port = runtime["provider_port"]
    backend_port = runtime["backend_port"]
    expected_ports = runtime["expected_ports"]
    if (
        type(provider_port) is not int
        or type(backend_port) is not int
        or not isinstance(expected_ports, list)
        or not expected_ports
        or any(type(port) is not int for port in expected_ports)
    ):
        raise RuntimeError("proof payload contains invalid runtime port record")
    all_ports = [provider_port, backend_port, *expected_ports]
    if (
        any(not 1 <= port <= 65535 for port in all_ports)
        or provider_port == backend_port
        or len(set(expected_ports)) != len(expected_ports)
        or provider_port not in expected_ports
        or backend_port not in expected_ports
    ):
        raise RuntimeError("proof payload contains invalid runtime port record")

    serialized = json.dumps(payload, sort_keys=True)
    sensitive_names = {
        "OPENAI_API_KEY",
        "AGENTSEEK_API_KEY",
        "AGENTSEEK_MODEL_API_KEY",
        "SILICONFLOW_API_KEY",
        "EMBEDDING_API_KEY",
        "BUB_API_KEY",
        "TAVILY_API_KEY",
        "SENTINEL",
    }
    leaked = [
        name for name in sorted(sensitive_names) if (value := child_environment.get(name)) and value in serialized
    ]
    if leaked:
        raise RuntimeError(f"proof payload contains secret or sentinel values for: {', '.join(leaked)}")


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", choices=sorted(PROFILES), required=True)
    parser.add_argument("--catalog-mode", choices=("source", "default"), required=True)
    parser.add_argument("--agentseek-version", required=True)
    parser.add_argument(
        "--agentseek-api-version",
        help="Expected API version; defaults to the selected template's reviewed release",
    )
    parser.add_argument("--agentseek-wheel", type=Path)
    parser.add_argument("--database-mode", choices=("auto", "embedded", "sqlite"), default="auto")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--proof-output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.agentseek_api_version is None:
        args.agentseek_api_version = AGENTSEEK_API_VERSIONS[args.template]
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    require_release_python(sys.version_info.major, sys.version_info.minor)
    forbidden_roots = [ROOT]
    output_root = _outside_repository(args.output_root, label="output root", forbidden_roots=forbidden_roots)
    proof_output = _outside_repository(args.proof_output, label="proof output", forbidden_roots=forbidden_roots)
    output_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    run_root = Path(tempfile.mkdtemp(prefix="template-runtime-", dir=output_root)).resolve()
    profile = PROFILES[args.template]
    source_template_root = ROOT / "templates" / args.template
    expected_api_version = AGENTSEEK_API_VERSIONS[args.template]
    if args.agentseek_api_version != expected_api_version:
        raise RuntimeError(f"{args.template} release proof requires agentseek-api=={expected_api_version}")
    if args.agentseek_wheel is not None and args.agentseek_version != "0.1.3":
        raise RuntimeError("--agentseek-wheel is reserved for the AgentSeek 0.1.3 candidate proof")

    artifact_dir = run_root / "artifacts"
    api_artifact = runtime_proof.download_published_wheel(
        "agentseek-api",
        args.agentseek_api_version,
        artifact_dir,
    )
    if args.agentseek_wheel is None:
        launcher_artifact = runtime_proof.download_published_wheel(
            "agentseek",
            args.agentseek_version,
            artifact_dir,
        )
        launcher_source = "pypi"
    else:
        launcher_artifact = validate_candidate_wheel(
            args.agentseek_wheel,
            version=args.agentseek_version,
            forbidden_roots=forbidden_roots,
            destination=artifact_dir,
        )
        launcher_source = "candidate-path"

    toolchain = _resolve_toolchain(forbidden_roots)
    base_environment = _minimal_environment(run_root, toolchain)
    launcher_root, launcher_python, agentseek_executable = _create_launcher_environment(
        run_root,
        toolchain,
        launcher_artifact,
        base_environment,
    )
    agentseek_executable = _external_executable(agentseek_executable, forbidden_roots)
    launcher_environment = _minimal_environment(
        run_root,
        toolchain,
        environment_bins=(agentseek_executable,),
    )

    port_template_root = _port_template_root(
        args.catalog_mode,
        template=args.template,
        source_template_root=source_template_root,
        launcher_python=launcher_python,
        launcher_environment=launcher_environment,
        run_root=run_root,
    )
    port_plan = _allocate_ports(args.template, port_template_root)
    try:
        cookiecutter_config = _write_cookiecutter_config(
            Path(launcher_environment["HOME"]),
            run_root,
            port_plan.context,
        )
        render_root = run_root / "rendered"
        render_root.mkdir(mode=0o700)
        if args.catalog_mode == "source":
            generated = _render_source(
                source_template_root,
                render_root,
                port_plan.context,
                cookiecutter_config,
            )
        else:
            create_command = build_create_command(
                agentseek_executable,
                template=args.template,
                output_root=render_root,
                catalog_mode="default",
            )
            generated = _render_default(
                create_command,
                output_root=render_root,
                env=launcher_environment,
                run_root=run_root,
            )

        _write_generated_env(generated)
        _install_contract_probe(generated, profile.graph_id)
        runtime_environment = build_runtime_environment(
            sys.platform,
            platform.machine(),
            run_root,
            args.database_mode,
        )
        child_root = generated / ".venv"
        child_python = _environment_python(child_root)
        child_environment = _child_environment(
            launcher_environment,
            profile,
            run_root,
            port_plan.provider_port,
            port_plan.backend_port,
            runtime_environment,
        )
        _install_generated_project(
            generated,
            api_artifact,
            toolchain,
            child_environment,
            args.template,
            run_root,
        )
        if not child_python.is_file():
            raise RuntimeError(f"generated sync did not create child interpreter: {child_python}")
        child_environment = _child_environment(
            _minimal_environment(
                run_root,
                toolchain,
                environment_bins=(agentseek_executable, child_python),
            ),
            profile,
            run_root,
            port_plan.provider_port,
            port_plan.backend_port,
            runtime_environment,
        )

        lock_record = _validate_api_lock(generated, api_artifact)
        launcher_import = _collect_import(
            launcher_python,
            "agentseek",
            "agentseek",
            launcher_root,
            args.agentseek_version,
        )
        api_import = _collect_import(
            child_python,
            "agentseek-api",
            "agentseek_api",
            child_root,
            args.agentseek_api_version,
        )
        catalog_record = _read_catalog_proof(
            launcher_python,
            launcher_environment,
            launcher_root,
            args.template,
            args.catalog_mode,
        )

        log_dir = run_root / "logs"
        log_dir.mkdir(mode=0o700)
        port_plan.release()
        with _managed_runtime_processes(launcher_environment) as runtime_processes:
            provider, provider_stream = _start_process(
                [
                    str(launcher_python),
                    str(FAKE_PROVIDER),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port_plan.provider_port),
                ],
                cwd=generated,
                env=child_environment,
                log_path=log_dir / "fake-provider.log",
                windows_supervisor_python=child_python,
            )
            runtime_processes.provider = provider
            runtime_processes.provider_stream = provider_stream
            lifecycle, lifecycle_stream = _start_process(
                [str(agentseek_executable), "dev", "--skip-check"],
                cwd=generated,
                env=child_environment,
                log_path=log_dir / "agentseek-dev.log",
                windows_supervisor_python=child_python,
            )
            runtime_processes.lifecycle = lifecycle
            runtime_processes.lifecycle_stream = lifecycle_stream
            base_url = f"http://127.0.0.1:{port_plan.backend_port}"
            _wait_for_runtime(
                base_url,
                lifecycle,
                provider,
                port_plan.expected_ports,
            )
            probe_result, probe_record = _run_graph(
                base_url,
                graph_id=PROBE_GRAPH_ID,
                run_input={"message": "probe"},
            )
            assert_contract_probe(probe_result)
            _, template_record = _run_graph(
                base_url,
                graph_id=profile.graph_id,
                run_input=profile.run_input,
            )
    finally:
        port_plan.release()

    proof_payload: dict[str, object] = {
        "schema_version": 1,
        "template": args.template,
        "catalog_mode": args.catalog_mode,
        "database_mode": args.database_mode,
        "runtime": {
            "provider_port": port_plan.provider_port,
            "backend_port": port_plan.backend_port,
            "expected_ports": list(port_plan.expected_ports),
        },
        "artifacts": {
            "agentseek": _artifact_record(launcher_artifact, launcher_source),
            "agentseek_api": _artifact_record(api_artifact, "pypi"),
        },
        "imports": {
            "agentseek": _import_record(launcher_import),
            "agentseek_api": _import_record(api_import),
        },
        "catalog_lock": catalog_record,
        "generated_lock": {"agentseek_api": lock_record},
        "result": {
            PROBE_GRAPH_ID: probe_record,
            "template_graph": template_record,
        },
    }
    _require_value_free_proof(proof_payload, child_environment)
    runtime_proof.write_proof(proof_output, proof_payload, forbidden_roots=forbidden_roots)
    print(json.dumps({"proof": str(proof_output), "status": "success", "template": args.template}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
