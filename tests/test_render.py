from __future__ import annotations

import asyncio
import importlib.util
import inspect
import json
import os
import shutil
import subprocess
import sys
import tomllib
import types
from pathlib import Path

import pytest
from agentseek.cli.lifecycle import normalize_lifecycle
from agentseek.cli.lifecycle.authored import LifecycleSpecV2
from agentseek.cli.lifecycle.spec import read_lifecycle_spec
from cookiecutter.main import cookiecutter
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_ROOT = REPOSITORY_ROOT / "templates"
INDEX = json.loads((TEMPLATES_ROOT / "index.json").read_text(encoding="utf-8"))
CORE_REPOSITORY = "https://github.com/ob-labs/agentseek.git"
CORE_COMMIT = "900f89518c32f8570d7648897394ed96a86a647a"
AGENTSEEK_API_VERSION = "0.2.3"
AGENTSEEK_API_DEPENDENCY = f"agentseek-api[embedded]=={AGENTSEEK_API_VERSION}"
AGENTSEEK_API_CANONICAL_NAME = canonicalize_name("agentseek-api")
MIGRATED_RUNTIME_TEMPLATES = {
    "deepagents/content-builder",
    "deepagents/mcp",
    "deepagents/research",
    "langchain/agentic-rag",
    "langchain/agentic-rag-hybrid",
    "langchain/cli-remote",
    "langchain/markdown-messages",
    "langchain/rubric",
}
# Reviewer #14's local-runtime proof explicitly covers these six templates.
# The two RAG variants below remain separately covered by catalog/lifecycle
# tests until their full runtime smoke is intentionally enabled in CI.
REVIEWER_LOCAL_RUNTIME_TEMPLATES = {
    "deepagents/content-builder",
    "deepagents/mcp",
    "deepagents/research",
    "langchain/agentic-rag-hybrid",
    "langchain/cli-remote",
    "langchain/rubric",
}
EXPECTED_CORE_DEPENDENCIES = {
    "bub/default": {"agentseek-ag-ui"},
    "deepagents/content-builder": set(),
    "deepagents/default": {"agentseek-ag-ui", "agentseek-langchain"},
    "deepagents/mcp": set(),
    "deepagents/research": set(),
    "deepagents/streaming": set(),
    "deepagents/sandbox": set(),
    "langchain/agentic-rag": set(),
    "langchain/agentic-rag-hybrid": set(),
    "langchain/agentic-rag-openvino": set(),
    "langchain/cli-remote": {"agentseek-langchain"},
    "langchain/default": {"agentseek-ag-ui", "agentseek-langchain"},
    "langchain/relay-observability": {"agentseek-ag-ui", "agentseek-langchain"},
    "langchain/markdown-messages": set(),
    "langchain/rubric": set(),
}
EXPECTED_NORMALIZED_TOPOLOGY = {
    "bub/default": {
        "services": (
            ("app", "web", "default", True, ("process:frontend",), ("frontend",), ()),
            ("copilotkit", "api", "hidden", False, ("process:frontend",), ("copilotkit",), ("docs",)),
            ("gateway", "protocol", "advanced", False, ("process:gateway",), ("gateway",), ("docs",)),
        ),
        "effects": {},
        "actions": (
            "project:start_dev",
            "service:app:open",
            "service:gateway:copy",
            "service:gateway:reference:docs",
        ),
    },
    "deepagents/content-builder": {
        "services": (
            ("frontend", "web", "default", True, ("process:frontend",), ("frontend",), ()),
            (
                "langgraph",
                "api",
                "advanced",
                False,
                ("process:langgraph",),
                ("langgraph",),
                ("api_docs", "docs", "studio"),
            ),
        ),
        "effects": {},
        "actions": (
            "project:start_dev",
            "service:frontend:open",
            "service:langgraph:copy",
            "service:langgraph:reference:api_docs",
            "service:langgraph:reference:docs",
            "service:langgraph:reference:studio",
        ),
    },
    "deepagents/default": {
        "services": (("gateway", "protocol", "default", True, ("process:gateway",), ("gateway",), ("docs",)),),
        "effects": {},
        "actions": (
            "project:start_dev",
            "service:gateway:copy",
            "service:gateway:reference:docs",
        ),
    },
    "deepagents/mcp": {
        "services": (
            (
                "calculator-http",
                "protocol",
                "hidden",
                False,
                ("process:calculator-http",),
                ("calculator-http",),
                ("docs",),
            ),
            ("frontend", "web", "default", True, ("process:frontend",), ("frontend",), ()),
            (
                "langgraph",
                "api",
                "advanced",
                False,
                ("process:langgraph",),
                ("langgraph",),
                ("api_docs", "docs", "studio"),
            ),
        ),
        "effects": {},
        "actions": (
            "project:start_dev",
            "service:frontend:open",
            "service:langgraph:copy",
            "service:langgraph:reference:api_docs",
            "service:langgraph:reference:docs",
            "service:langgraph:reference:studio",
        ),
    },
    "deepagents/research": {
        "services": (
            ("frontend", "web", "default", True, ("process:frontend",), ("frontend",), ("docs",)),
            (
                "langgraph",
                "api",
                "advanced",
                False,
                ("process:langgraph",),
                ("langgraph",),
                ("api_docs", "docs", "studio"),
            ),
        ),
        "effects": {},
        "actions": (
            "project:start_dev",
            "service:frontend:open",
            "service:frontend:reference:docs",
            "service:langgraph:copy",
            "service:langgraph:reference:api_docs",
            "service:langgraph:reference:docs",
            "service:langgraph:reference:studio",
        ),
    },
    "deepagents/streaming": {
        "services": (
            ("frontend", "web", "default", True, ("process:frontend",), ("frontend",), ("docs",)),
            (
                "langgraph",
                "api",
                "advanced",
                False,
                ("process:langgraph",),
                ("langgraph",),
                ("api_docs", "docs", "studio"),
            ),
        ),
        "effects": {},
        "actions": (
            "project:start_dev",
            "service:frontend:open",
            "service:frontend:reference:docs",
            "service:langgraph:copy",
            "service:langgraph:reference:api_docs",
            "service:langgraph:reference:docs",
            "service:langgraph:reference:studio",
        ),
    },
    "deepagents/sandbox": {
        "services": (
            (
                "backend",
                "api",
                "advanced",
                False,
                ("process:backend",),
                ("backend",),
                ("api_docs", "docs", "studio"),
            ),
            ("frontend", "web", "default", True, ("process:frontend",), ("frontend",), ("docs",)),
        ),
        "effects": {},
        "actions": (
            "project:start_dev",
            "service:backend:copy",
            "service:backend:reference:api_docs",
            "service:backend:reference:docs",
            "service:backend:reference:studio",
            "service:frontend:open",
            "service:frontend:reference:docs",
        ),
    },
    "langchain/agentic-rag": {
        "services": (
            (
                "backend",
                "api",
                "advanced",
                False,
                ("process:backend",),
                ("backend",),
                ("api_docs", "docs", "studio"),
            ),
            ("frontend", "web", "default", True, ("process:frontend",), ("frontend",), ()),
        ),
        "effects": {},
        "actions": (
            "project:start_dev",
            "service:backend:copy",
            "service:backend:reference:api_docs",
            "service:backend:reference:docs",
            "service:backend:reference:studio",
            "service:frontend:open",
        ),
    },
    "langchain/agentic-rag-hybrid": {
        "services": (
            (
                "backend",
                "api",
                "advanced",
                False,
                ("process:backend",),
                ("backend", "custom_routes"),
                ("api_docs", "docs", "studio"),
            ),
            ("frontend", "web", "default", True, ("process:frontend",), ("frontend",), ()),
            ("phoenix", "web", "advanced", False, ("task:phoenix",), (), ("docs",)),
            ("phoenix_seekdb", "database", "hidden", False, ("task:phoenix",), (), ("docs",)),
        ),
        "effects": {
            "phoenix": (("phoenix", "phoenix_seekdb"), ()),
            "phoenix-stop": ((), ("phoenix", "phoenix_seekdb")),
        },
        "actions": (
            "project:start_dev",
            "service:backend:copy",
            "service:backend:reference:api_docs",
            "service:backend:reference:docs",
            "service:backend:reference:studio",
            "service:frontend:open",
            "service:phoenix:open",
            "service:phoenix:reference:docs",
            "task:phoenix",
            "task:phoenix-stop",
        ),
    },
    "langchain/agentic-rag-openvino": {
        "services": (
            (
                "backend",
                "api",
                "advanced",
                False,
                ("process:backend",),
                ("backend",),
                ("api_docs", "docs", "studio"),
            ),
            ("frontend", "web", "default", True, ("process:frontend",), ("frontend",), ()),
            (
                "seekdb",
                "database",
                "advanced",
                False,
                ("process:seekdb", "task:seekdb"),
                (),
                ("docs",),
            ),
        ),
        "effects": {"seekdb": (("seekdb",), ())},
        "actions": (
            "project:start_dev",
            "service:backend:copy",
            "service:backend:reference:api_docs",
            "service:backend:reference:docs",
            "service:backend:reference:studio",
            "service:frontend:open",
            "service:seekdb:copy",
            "service:seekdb:reference:docs",
            "task:seekdb",
        ),
    },
    "langchain/cli-remote": {
        "services": (
            (
                "langgraph",
                "api",
                "default",
                True,
                ("process:langgraph",),
                ("langgraph",),
                ("api_docs", "docs", "studio"),
            ),
        ),
        "effects": {},
        "actions": (
            "project:start_dev",
            "service:langgraph:copy",
            "service:langgraph:reference:api_docs",
            "service:langgraph:reference:docs",
            "service:langgraph:reference:studio",
        ),
    },
    "langchain/default": {
        "services": (
            ("copilotkit", "api", "hidden", False, ("process:stack",), ("copilotkit",), ("docs",)),
            ("frontend", "web", "default", True, ("process:stack",), ("frontend",), ()),
            ("gateway", "protocol", "advanced", False, ("process:stack",), ("gateway",), ("docs",)),
            ("phoenix", "web", "advanced", False, ("process:stack",), ("phoenix",), ("docs",)),
            ("seekdb", "database", "hidden", False, ("process:stack",), (), ("docs",)),
        ),
        "effects": {},
        "actions": (
            "project:start_dev",
            "service:frontend:open",
            "service:gateway:copy",
            "service:gateway:reference:docs",
            "service:phoenix:open",
            "service:phoenix:reference:docs",
        ),
    },
    "langchain/relay-observability": {
        "services": (
            ("copilotkit", "api", "hidden", False, ("process:stack",), ("copilotkit",), ("docs",)),
            ("frontend", "web", "default", True, ("process:stack",), ("frontend",), ()),
            ("gateway", "protocol", "advanced", False, ("process:stack",), ("gateway",), ("docs",)),
            ("phoenix", "web", "advanced", False, ("process:stack",), ("phoenix",), ("docs",)),
            ("seekdb", "database", "hidden", False, ("process:stack",), (), ("docs",)),
        ),
        "effects": {},
        "actions": (
            "project:start_dev",
            "service:frontend:open",
            "service:gateway:copy",
            "service:gateway:reference:docs",
            "service:phoenix:open",
            "service:phoenix:reference:docs",
        ),
    },
    "langchain/markdown-messages": {
        "services": (
            (
                "backend",
                "api",
                "advanced",
                False,
                ("process:backend",),
                ("backend",),
                ("api_docs", "docs", "studio"),
            ),
            ("frontend", "web", "default", True, ("process:frontend",), ("frontend",), ("docs",)),
        ),
        "effects": {},
        "actions": (
            "project:start_dev",
            "service:backend:copy",
            "service:backend:reference:api_docs",
            "service:backend:reference:docs",
            "service:backend:reference:studio",
            "service:frontend:open",
            "service:frontend:reference:docs",
        ),
    },
    "langchain/rubric": {
        "services": (
            ("frontend", "web", "default", True, ("process:frontend",), ("frontend",), ("docs",)),
            (
                "langgraph",
                "api",
                "advanced",
                False,
                ("process:langgraph",),
                ("langgraph",),
                ("api_docs", "docs", "studio"),
            ),
        ),
        "effects": {},
        "actions": (
            "project:start_dev",
            "service:frontend:open",
            "service:frontend:reference:docs",
            "service:langgraph:copy",
            "service:langgraph:reference:api_docs",
            "service:langgraph:reference:docs",
            "service:langgraph:reference:studio",
        ),
    },
}


def _assert_exact_agentseek_api_dependency(requirements: list[str]) -> None:
    api_dependencies: list[tuple[str, str]] = []
    for raw_requirement in requirements:
        parsed = Requirement(raw_requirement)
        if canonicalize_name(parsed.name) == AGENTSEEK_API_CANONICAL_NAME:
            api_dependencies.append((raw_requirement, str(parsed)))
    expected = [(AGENTSEEK_API_DEPENDENCY, AGENTSEEK_API_DEPENDENCY)]
    assert api_dependencies == expected, (
        f"agentseek-api dependencies must be exactly {expected}, got {api_dependencies}"
    )


def _assert_exact_api_pin_contract(generated_path: Path, template_key: str) -> None:
    project = tomllib.loads((generated_path / "pyproject.toml").read_text(encoding="utf-8"))
    _assert_exact_agentseek_api_dependency(project["project"].get("dependencies", []))

    requirements = generated_path / "requirements.txt"
    if template_key == "langchain/cli-remote":
        assert requirements.is_file(), "agentseek-api requirements.txt is missing for langchain/cli-remote"
        lines = [line.strip() for line in requirements.read_text(encoding="utf-8").splitlines() if line.strip()]
        _assert_exact_agentseek_api_dependency(lines)


def _registered_templates() -> list[tuple[str, Path]]:
    return [(key, TEMPLATES_ROOT / key) for key in sorted(INDEX)]


def test_reviewed_contract_covers_every_registered_template() -> None:
    assert set(INDEX) == set(EXPECTED_CORE_DEPENDENCIES) == set(EXPECTED_NORMALIZED_TOPOLOGY)


def _render(
    template_root: Path,
    output_root: Path,
    tmp_path: Path,
    *,
    extra_context: dict[str, str] | None = None,
) -> Path:
    config_path = tmp_path / "cookiecutter-config.json"
    config_path.write_text(
        json.dumps(
            {
                "cookiecutters_dir": str(tmp_path / "cookiecutters"),
                "replay_dir": str(tmp_path / "replay"),
            }
        ),
        encoding="utf-8",
    )
    return Path(
        cookiecutter(
            template=str(template_root),
            output_dir=str(output_root),
            no_input=True,
            config_file=str(config_path),
            extra_context=extra_context,
        )
    )


def render_rubric(tmp_path: Path) -> Path:
    """Render the catalog-native rubric template with its reviewed defaults."""
    output_root = tmp_path / "rubric-output"
    output_root.mkdir()
    return _render(TEMPLATES_ROOT / "langchain/rubric", output_root, tmp_path)


@pytest.mark.parametrize(("template_key", "template_root"), _registered_templates(), ids=sorted(INDEX))
def test_registered_template_renders_as_complete_lifecycle_v2(
    template_key: str,
    template_root: Path,
    tmp_path: Path,
) -> None:
    isolated_template = tmp_path / "source" / template_root.name
    shutil.copytree(template_root, isolated_template)
    output_root = tmp_path / "output"
    output_root.mkdir()

    generated_path = _render(isolated_template, output_root, tmp_path)
    lifecycle_path = generated_path / ".agentseek" / "lifecycle.toml"
    lifecycle_text = lifecycle_path.read_text(encoding="utf-8")
    assert "{{" not in lifecycle_text

    spec = read_lifecycle_spec(lifecycle_path, project_root=generated_path)
    assert isinstance(spec, LifecycleSpecV2)
    assert spec.version == 2
    assert spec.template == template_key

    normalized = normalize_lifecycle(spec, project_root=generated_path)
    assert normalized.lifecycle_version == 2
    assert normalized.metadata_complete is True
    assert not normalized.warnings
    if normalized.services:
        assert sum(service.primary is True for service in normalized.services) == 1
    assert all(check.service_id is not None for check in normalized.checks)

    pyproject_path = generated_path / "pyproject.toml"
    assert pyproject_path.is_file()
    pyproject_text = pyproject_path.read_text(encoding="utf-8")
    assert "{{" not in pyproject_text
    pyproject = tomllib.loads(pyproject_text)
    assert pyproject["project"]["name"]


@pytest.mark.parametrize("template_key", sorted(MIGRATED_RUNTIME_TEMPLATES))
def test_migrated_templates_pin_the_published_api_release(
    template_key: str,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    generated_path = _render(TEMPLATES_ROOT / template_key, output_root, tmp_path)
    _assert_exact_api_pin_contract(generated_path, template_key)


def _write_exact_pin_contract_fixture(
    root: Path,
    dependencies: list[str],
    requirements: str | None,
) -> Path:
    generated = root / "generated"
    generated.mkdir()
    dependency_lines = "\n".join(f"    {json.dumps(item)}," for item in dependencies)
    (generated / "pyproject.toml").write_text(
        f"[project]\ndependencies = [\n{dependency_lines}\n]\n",
        encoding="utf-8",
    )
    if requirements is not None:
        (generated / "requirements.txt").write_text(requirements, encoding="utf-8")
    return generated


@pytest.mark.parametrize(
    "requirements",
    [
        pytest.param(None, id="missing"),
        pytest.param(
            "agentseek-api[embedded]==0.2.3\nagentseek-api[embedded]==0.2.3\n",
            id="duplicate",
        ),
        pytest.param(
            "agentseek-api[embedded]==0.2.3\nAgentSeek_API[embedded]>=0.2\n",
            id="pep503-equivalent-conflict",
        ),
    ],
)
def test_exact_api_pin_contract_rejects_invalid_cli_requirements(
    requirements: str | None,
    tmp_path: Path,
) -> None:
    generated = _write_exact_pin_contract_fixture(
        tmp_path,
        ["agentseek-api[embedded]==0.2.3"],
        requirements,
    )

    with pytest.raises(AssertionError, match="agentseek-api"):
        _assert_exact_api_pin_contract(generated, "langchain/cli-remote")


@pytest.mark.parametrize(
    "dependencies",
    [
        [],
        ["agentseek-api[embedded]==0.2.3", "agentseek-api[embedded]==0.2.3"],
        ["agentseek-api[embedded]==0.2.3", "AgentSeek_API[embedded]>=0.2"],
    ],
    ids=["missing", "duplicate", "pep503-equivalent-conflict"],
)
def test_exact_api_pin_contract_rejects_invalid_pyproject_dependencies(
    dependencies: list[str],
    tmp_path: Path,
) -> None:
    generated = _write_exact_pin_contract_fixture(
        tmp_path,
        dependencies,
        "agentseek-api[embedded]==0.2.3\n",
    )

    with pytest.raises(AssertionError, match="agentseek-api"):
        _assert_exact_api_pin_contract(generated, "langchain/cli-remote")


@pytest.mark.parametrize("template_key", sorted(MIGRATED_RUNTIME_TEMPLATES))
def test_migrated_templates_declare_agentseek_api_runtime_and_dependency(
    template_key: str,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    generated_path = _render(TEMPLATES_ROOT / template_key, output_root, tmp_path)
    lifecycle = tomllib.loads((generated_path / ".agentseek" / "lifecycle.toml").read_text(encoding="utf-8"))
    processes = lifecycle["processes"]
    commands = [" ".join(str(part) for part in process["command"]) for process in processes.values()]
    assert any(
        ("agentseek-api" in command and " dev" in command)
        or (template_key == "deepagents/mcp" and "langgraph_dev" in command)
        for command in commands
    )
    assert all("langgraph dev" not in command for command in commands)

    pyproject = tomllib.loads((generated_path / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = set(pyproject["project"].get("dependencies", []))
    requirements = (
        (generated_path / "requirements.txt").read_text(encoding="utf-8")
        if (generated_path / "requirements.txt").is_file()
        else ""
    )
    has_agentseek_api = any(dependency.startswith("agentseek-api") for dependency in dependencies)
    assert has_agentseek_api or "agentseek-api" in requirements
    assert "mcp>=1.27.1,<2" in dependencies


@pytest.mark.parametrize("template_key", sorted(MIGRATED_RUNTIME_TEMPLATES))
def test_migrated_templates_resolve_api_through_uv_without_path_activation(
    template_key: str,
    tmp_path: Path,
) -> None:
    """The lifecycle must let ``uv run`` resolve the API executable itself."""
    output_root = tmp_path / "output"
    output_root.mkdir()
    generated_path = _render(TEMPLATES_ROOT / template_key, output_root, tmp_path)
    lifecycle = tomllib.loads((generated_path / ".agentseek" / "lifecycle.toml").read_text(encoding="utf-8"))

    tools = set(lifecycle.get("tools", {}).get("required", []))
    assert "agentseek-api" not in tools
    api_commands = [
        " ".join(str(part) for part in process["command"])
        for process in lifecycle["processes"].values()
        if "agentseek-api" in " ".join(str(part) for part in process["command"])
        or (template_key == "deepagents/mcp" and "langgraph_dev" in " ".join(str(part) for part in process["command"]))
    ]
    assert len(api_commands) == 1
    if template_key == "deepagents/mcp":
        assert api_commands[0].startswith("uv run python -m")
    else:
        assert "uv run agentseek-api dev" in api_commands[0]


@pytest.mark.parametrize("template_key", sorted(REVIEWER_LOCAL_RUNTIME_TEMPLATES))
def test_migrated_local_api_templates_declare_embedded_persistence(
    template_key: str,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    generated_path = _render(TEMPLATES_ROOT / template_key, output_root, tmp_path)

    pyproject = tomllib.loads((generated_path / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = pyproject["project"].get("dependencies", [])
    assert any(dependency.startswith("agentseek-api[embedded]") for dependency in dependencies)

    requirements_path = generated_path / "requirements.txt"
    if requirements_path.is_file():
        assert "agentseek-api[embedded]" in requirements_path.read_text(encoding="utf-8")

    env_example = (generated_path / ".env.example").read_text(encoding="utf-8")
    assert "SEEKDB_EMBED=true" in env_example
    assert "SEEKDB_EMBED_DIR=" in env_example
    assert "OCEANBASE_DB_NAME=" in env_example

    env_values = {
        line.split("=", 1)[0]: line.split("=", 1)[1]
        for line in env_example.splitlines()
        if line and not line.startswith("#") and "=" in line
    }
    lifecycle_path = generated_path / ".agentseek" / "lifecycle.toml"
    lifecycle_text = lifecycle_path.read_text(encoding="utf-8")
    lifecycle = tomllib.loads(lifecycle_text)
    assert "{{" not in env_example + lifecycle_text + (generated_path / "pyproject.toml").read_text(encoding="utf-8")
    lifecycle_env = lifecycle["env"]
    for name in ("SEEKDB_EMBED", "SEEKDB_EMBED_DIR", "OCEANBASE_DB_NAME"):
        assert name in lifecycle_env
        assert str(lifecycle_env[name]["default"]) == env_values[name]

    if template_key == "langchain/agentic-rag-hybrid":
        assert env_values["SEEKDB_EMBED_DIR"] != env_values["SEEKDB_PATH"]


@pytest.mark.parametrize("template_key", ["deepagents/mcp"])
def test_migrated_local_api_lifecycle_has_no_posix_shell(
    template_key: str,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    generated_path = _render(TEMPLATES_ROOT / template_key, output_root, tmp_path)
    lifecycle = tomllib.loads((generated_path / ".agentseek" / "lifecycle.toml").read_text(encoding="utf-8"))

    commands = [
        [str(part) for part in process["command"]]
        for process in lifecycle["processes"].values()
        if "agentseek-api" in " ".join(str(part) for part in process["command"])
        or "langgraph_dev" in " ".join(str(part) for part in process["command"])
    ]
    assert commands
    assert all(command[:2] not in (["sh", "-lc"], ["bash", "-lc"]) for command in commands)


def test_deepagents_mcp_uses_cross_platform_host_wrapper(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    generated_path = _render(TEMPLATES_ROOT / "deepagents/mcp", output_root, tmp_path)
    lifecycle = tomllib.loads((generated_path / ".agentseek" / "lifecycle.toml").read_text(encoding="utf-8"))

    command = lifecycle["processes"]["langgraph"]["command"]
    assert command[:5] == ["uv", "run", "python", "-m", f"{generated_path.name}.langgraph_dev"]
    wrapper = generated_path / "src" / generated_path.name / "langgraph_dev.py"
    wrapper_text = wrapper.read_text(encoding="utf-8")
    assert "LANGGRAPH_HOST" in wrapper_text
    assert '"--host"' in wrapper_text


def test_deepagents_mcp_wrapper_builds_argv_without_shell(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    generated_path = _render(TEMPLATES_ROOT / "deepagents/mcp", output_root, tmp_path)
    wrapper = generated_path / "src" / generated_path.name / "langgraph_dev.py"
    spec = importlib.util.spec_from_file_location("generated_langgraph_dev", wrapper)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls: list[list[str]] = []
    monkeypatch.setenv("LANGGRAPH_HOST", "0.0.0.0")
    monkeypatch.setattr(module.shutil, "which", lambda name: "/fake/agentseek-api")
    monkeypatch.setattr(module.subprocess, "call", lambda command: calls.append(command) or 17)

    assert module.main() == 17
    assert calls == [["/fake/agentseek-api", "dev", "--host", "0.0.0.0", "--port", "2024"]]


def test_deepagents_mcp_graph_factory_is_sync_inside_running_event_loop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    generated_path = _render(TEMPLATES_ROOT / "deepagents/mcp", output_root, tmp_path)
    project_slug = generated_path.name
    agent_path = generated_path / "src" / project_slug / "agent.py"

    class FakeCompiledStateGraph:
        pass

    class FakeProfile:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    expected_graph = FakeCompiledStateGraph()
    load_calls = 0

    async def fake_load_mcp_tools(config: object) -> types.SimpleNamespace:
        nonlocal load_calls
        load_calls += 1
        await asyncio.sleep(0)
        return types.SimpleNamespace(client=object(), tools=(object(),), tool_names=("add",))

    deepagents = types.ModuleType("deepagents")
    deepagents.GeneralPurposeSubagentProfile = FakeProfile
    deepagents.HarnessProfile = FakeProfile
    deepagents.create_deep_agent = lambda **kwargs: expected_graph
    deepagents.register_harness_profile = lambda *args: None

    langgraph = types.ModuleType("langgraph")
    langgraph_graph = types.ModuleType("langgraph.graph")
    langgraph_state = types.ModuleType("langgraph.graph.state")
    langgraph_state.CompiledStateGraph = FakeCompiledStateGraph

    project_package = types.ModuleType(project_slug)
    project_package.__path__ = [str(generated_path / "src" / project_slug)]
    config_module = types.ModuleType(f"{project_slug}.config")
    config_module.load_mcp_config = lambda path: object()
    mcp_tools_module = types.ModuleType(f"{project_slug}.mcp_tools")
    mcp_tools_module.load_mcp_tools = fake_load_mcp_tools
    model_module = types.ModuleType(f"{project_slug}.model")
    model_module.resolve_model_binding = lambda: types.SimpleNamespace(
        profile_key="test-profile",
        model=object(),
    )

    for name, stub in {
        "deepagents": deepagents,
        "langgraph": langgraph,
        "langgraph.graph": langgraph_graph,
        "langgraph.graph.state": langgraph_state,
        project_slug: project_package,
        f"{project_slug}.config": config_module,
        f"{project_slug}.mcp_tools": mcp_tools_module,
        f"{project_slug}.model": model_module,
    }.items():
        monkeypatch.setitem(sys.modules, name, stub)

    module_name = f"{project_slug}.agent_under_test"
    spec = importlib.util.spec_from_file_location(module_name, agent_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)

    async def call_factory_from_api_loop() -> object:
        return module.make_graph()

    graph = asyncio.run(call_factory_from_api_loop())
    if inspect.iscoroutine(graph):
        graph.close()

    assert graph is expected_graph
    assert module.make_graph() is expected_graph
    assert load_calls == 1


@pytest.mark.parametrize("template_key", sorted(MIGRATED_RUNTIME_TEMPLATES))
def test_migrated_templates_expose_api_health_and_preserve_graph_config(
    template_key: str,
    tmp_path: Path,
) -> None:
    """Regression-test the minimum AgentSeek API contract at render time."""
    output_root = tmp_path / "output"
    output_root.mkdir()
    generated_path = _render(TEMPLATES_ROOT / template_key, output_root, tmp_path)

    lifecycle = tomllib.loads((generated_path / ".agentseek" / "lifecycle.toml").read_text(encoding="utf-8"))
    api_processes = [
        process
        for process in lifecycle["processes"].values()
        if "agentseek-api" in " ".join(str(part) for part in process["command"])
        or (template_key == "deepagents/mcp" and "langgraph_dev" in " ".join(str(part) for part in process["command"]))
    ]
    assert len(api_processes) == 1
    api_process = api_processes[0]
    api_command = " ".join(str(part) for part in api_process["command"])
    if template_key == "deepagents/mcp":
        assert api_command.startswith("uv run python -m")
    else:
        assert "agentseek-api dev" in api_command

    api_checks = [
        check
        for check in lifecycle["checks"].values()
        if check.get("service") in lifecycle["services"]
        and lifecycle["services"][check["service"]].get("tech") == "agentseek-api"
    ]
    assert api_checks
    assert any(check.get("service") is not None for check in api_checks)
    assert all(check["target"].endswith(("/health", "/ok")) for check in api_checks)

    graph_config = generated_path / "langgraph.json"
    assert graph_config.is_file()
    config_text = graph_config.read_text(encoding="utf-8")
    assert "{{" not in config_text
    try:
        graph_data = json.loads(config_text)
    except json.JSONDecodeError:
        graph_data = tomllib.loads(config_text)
    assert "graphs" in graph_data


@pytest.mark.parametrize(
    "template_key",
    ["deepagents/content-builder", "deepagents/research"],
)
def test_agentseek_api_templates_render_local_seekdb_url(
    template_key: str,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    generated_path = _render(TEMPLATES_ROOT / template_key, output_root, tmp_path)
    env_example = (generated_path / ".env.example").read_text(encoding="utf-8")

    assert "SEEKDB_EMBED=true" in env_example
    assert "SEEKDB_EMBED_DIR=" in env_example
    assert "OCEANBASE_DB_NAME=test" in env_example


@pytest.mark.parametrize("template_key", ["deepagents/mcp", "langchain/rubric"])
def test_embedded_seekdb_templates_declare_pyseekdb_extra(
    template_key: str,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    generated_path = _render(TEMPLATES_ROOT / template_key, output_root, tmp_path)
    pyproject = tomllib.loads((generated_path / "pyproject.toml").read_text(encoding="utf-8"))

    assert "pyobvector[pyseekdb]" in pyproject["project"]["dependencies"]


def test_agentic_rag_renders_agentseek_embedded_seekdb_aliases(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    generated_path = _render(TEMPLATES_ROOT / "langchain/agentic-rag", output_root, tmp_path)
    env_example = (generated_path / ".env.example").read_text(encoding="utf-8")

    assert "SEEKDB_EMBED=true" in env_example
    assert "SEEKDB_EMBED_DIR=" in env_example
    assert "OCEANBASE_DB_NAME=" in env_example


def test_markdown_messages_declares_embedded_seekdb_for_agentseek_api(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    generated_path = _render(TEMPLATES_ROOT / "langchain/markdown-messages", output_root, tmp_path)
    env_example = (generated_path / ".env.example").read_text(encoding="utf-8")
    assert "SEEKDB_EMBED=true" in env_example
    assert "SEEKDB_EMBED_DIR=" in env_example
    assert "OCEANBASE_DB_NAME=test" in env_example
    pyproject = tomllib.loads((generated_path / "pyproject.toml").read_text(encoding="utf-8"))
    assert AGENTSEEK_API_DEPENDENCY in pyproject["project"]["dependencies"]


def test_openvino_remains_on_its_reviewed_runtime_until_a_model_fixture_exists(tmp_path: Path) -> None:
    assert "langchain/agentic-rag-openvino" not in MIGRATED_RUNTIME_TEMPLATES
    output_root = tmp_path / "output"
    output_root.mkdir()
    generated_path = _render(TEMPLATES_ROOT / "langchain/agentic-rag-openvino", output_root, tmp_path)
    project = tomllib.loads((generated_path / "pyproject.toml").read_text(encoding="utf-8"))
    lifecycle = tomllib.loads((generated_path / ".agentseek" / "lifecycle.toml").read_text(encoding="utf-8"))
    dependencies = set(project["project"]["dependencies"])
    backend = " ".join(lifecycle["processes"]["backend"]["command"])

    assert project["project"]["requires-python"] == ">=3.10"
    assert "langgraph-cli[inmem]>=0.4" in dependencies
    assert not any(item.startswith("agentseek-api") for item in dependencies)
    assert "uv run langgraph dev" in backend


def test_sandbox_remains_on_its_reviewed_runtime_until_a_local_provider_exists(tmp_path: Path) -> None:
    assert "deepagents/sandbox" not in MIGRATED_RUNTIME_TEMPLATES
    output_root = tmp_path / "output"
    output_root.mkdir()
    generated_path = _render(TEMPLATES_ROOT / "deepagents/sandbox", output_root, tmp_path)
    project = tomllib.loads((generated_path / "pyproject.toml").read_text(encoding="utf-8"))
    lifecycle = tomllib.loads((generated_path / ".agentseek" / "lifecycle.toml").read_text(encoding="utf-8"))
    dependencies = set(project["project"]["dependencies"])
    backend = lifecycle["processes"]["backend"]["command"]

    assert not any(item.startswith("agentseek-api") for item in dependencies)
    assert "langgraph-cli[inmem]>=0.4" in dependencies
    assert backend == [
        "uv",
        "run",
        "langgraph",
        "dev",
        "--no-browser",
        "--port",
        "2024",
    ]


@pytest.mark.parametrize(("template_key", "template_root"), _registered_templates(), ids=sorted(INDEX))
def test_registered_template_normalizes_to_reviewed_topology(
    template_key: str,
    template_root: Path,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    generated_path = _render(template_root, output_root, tmp_path)
    spec = read_lifecycle_spec(
        generated_path / ".agentseek" / "lifecycle.toml",
        project_root=generated_path,
    )
    normalized = normalize_lifecycle(spec, project_root=generated_path)

    actual_services = tuple(
        (
            service.id,
            service.kind,
            service.display,
            service.primary,
            tuple(provider.id for provider in service.providers),
            service.check_ids,
            tuple(link.rel for link in service.links),
        )
        for service in normalized.services
    )
    actual_effects = {task.id: (task.starts, task.stops) for task in normalized.tasks if task.starts or task.stops}
    actual_actions = tuple(action.id for action in normalized.actions)
    expected = EXPECTED_NORMALIZED_TOPOLOGY[template_key]

    assert actual_services == expected["services"]
    assert actual_effects == expected["effects"]
    assert actual_actions == expected["actions"]


@pytest.mark.parametrize(("template_key", "template_root"), _registered_templates(), ids=sorted(INDEX))
def test_generated_core_dependencies_are_immutable(
    template_key: str,
    template_root: Path,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    generated_path = _render(template_root, output_root, tmp_path)
    pyproject = tomllib.loads((generated_path / "pyproject.toml").read_text(encoding="utf-8"))
    sources = pyproject.get("tool", {}).get("uv", {}).get("sources", {})
    core_sources = {
        dependency: source
        for dependency, source in sources.items()
        if dependency.startswith("agentseek-") or str(source.get("subdirectory", "")).startswith("contrib/agentseek-")
    }
    assert set(core_sources) == EXPECTED_CORE_DEPENDENCIES[template_key]
    for dependency, source in core_sources.items():
        assert source == {
            "git": CORE_REPOSITORY,
            "rev": CORE_COMMIT,
            "subdirectory": f"contrib/{dependency}",
        }


def test_mcp_lifecycle_advertises_protocol_url_and_separate_health_check(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    generated_path = _render(TEMPLATES_ROOT / "deepagents/mcp", output_root, tmp_path)
    spec = read_lifecycle_spec(
        generated_path / ".agentseek" / "lifecycle.toml",
        project_root=generated_path,
    )
    normalized = normalize_lifecycle(spec, project_root=generated_path)

    calculator_service = next(service for service in normalized.services if service.id == "calculator-http")
    calculator_check = next(check for check in normalized.checks if check.id == "calculator-http")

    assert calculator_service.url == "http://127.0.0.1:8765/mcp"
    assert calculator_check.target == "http://127.0.0.1:8765/health"


def test_relay_observability_render_runs_child_tests_with_dummy_credentials(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    generated_path = _render(
        TEMPLATES_ROOT / "langchain/relay-observability",
        output_root,
        tmp_path,
        extra_context={"project_name": "Rendered Relay Child"},
    )
    env = {
        **os.environ,
        "OPENAI_API_KEY": "test-openai-key",
        "TAVILY_API_KEY": "test-tavily-key",
        "RELAY_ENABLED": "false",
        "UV_CACHE_DIR": str(tmp_path / "uv-cache"),
    }
    for proxy_name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        env.pop(proxy_name, None)
    sync = subprocess.run(
        ["uv", "sync", "--extra", "dev"],
        cwd=generated_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert sync.returncode == 0, sync.stdout + sync.stderr
    child_command = ["uv", "run", "python", "-m", "pytest", "-q"]
    result = subprocess.run(
        child_command,
        cwd=generated_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_deepagents_default_render_runs_child_tests(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    generated_path = _render(
        TEMPLATES_ROOT / "deepagents/default",
        output_root,
        tmp_path,
        extra_context={"project_name": "Rendered DeepAgents Default"},
    )
    rendered_readme = (generated_path / "README.md").read_text(encoding="utf-8")
    assert "HarnessProfile" in rendered_readme
    assert "ProviderProfile" in rendered_readme
    assert "use_responses_api=False" in rendered_readme
    assert "Chat Completions" in rendered_readme
    env = {
        **os.environ,
        "BUB_MODEL": "openai:test-model",
        "BUB_API_KEY": "test-api-key",
        "UV_CACHE_DIR": str(tmp_path / "uv-cache"),
    }
    for proxy_name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        env.pop(proxy_name, None)
    sync = subprocess.run(
        ["uv", "sync", "--dev"],
        cwd=generated_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert sync.returncode == 0, sync.stdout + sync.stderr
    result = subprocess.run(
        ["uv", "run", "python", "-m", "pytest", "-q"],
        cwd=generated_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_cli_remote_does_not_claim_that_local_dev_provides_an_external_server(tmp_path: Path) -> None:
    template_root = TEMPLATES_ROOT / "langchain/cli-remote"
    output_root = tmp_path / "output"
    output_root.mkdir()

    generated_path = _render(
        template_root,
        output_root,
        tmp_path,
        extra_context={"langgraph_url": "https://example.com/agents"},
    )
    spec = read_lifecycle_spec(
        generated_path / ".agentseek" / "lifecycle.toml",
        project_root=generated_path,
    )
    normalized = normalize_lifecycle(spec, project_root=generated_path)

    langgraph = next(service for service in normalized.services if service.id == "langgraph")
    assert langgraph.url == "https://example.com/agents"
    assert langgraph.providers == ()
    assert "project:start_dev" not in {action.id for action in normalized.actions}


def test_cli_remote_local_dev_does_not_open_studio_implicitly(tmp_path: Path) -> None:
    template_root = TEMPLATES_ROOT / "langchain/cli-remote"
    output_root = tmp_path / "output"
    output_root.mkdir()

    generated_path = _render(template_root, output_root, tmp_path)
    spec = read_lifecycle_spec(
        generated_path / ".agentseek" / "lifecycle.toml",
        project_root=generated_path,
    )

    assert "agentseek-api" in spec.processes["langgraph"].command
    assert "--no-browser" not in spec.processes["langgraph"].command


def test_rubric_template_pins_characterized_runtime(tmp_path: Path) -> None:
    generated = render_rubric(tmp_path)
    project = tomllib.loads((generated / "pyproject.toml").read_text(encoding="utf-8"))

    assert "deepagents==0.7.1" in project["project"]["dependencies"]
    assert "langchain==1.3.14" in project["project"]["dependencies"]
    assert "langgraph==1.2.10" in project["project"]["dependencies"]


def test_rubric_template_exposes_only_reviewed_lazy_graph_factories(tmp_path: Path) -> None:
    generated = render_rubric(tmp_path)
    langgraph = json.loads((generated / "langgraph.json").read_text(encoding="utf-8"))

    assert langgraph["graphs"] == {
        "rubric-demo": "rubric_lab.graphs:make_demo_graph",
        "rubric-live": "rubric_lab.graphs:make_live_graph",
    }


def test_rubric_example_exposes_the_provider_native_live_model_contract(tmp_path: Path) -> None:
    generated = render_rubric(tmp_path)
    assignments = {
        name: value
        for raw_line in (generated / ".env.example").read_text(encoding="utf-8").splitlines()
        if (line := raw_line.strip()) and not line.startswith("#") and "=" in line
        for name, value in [line.split("=", maxsplit=1)]
    }

    assert assignments == {
        "AGENTSEEK_MODEL_PROVIDER": "openai",
        "AGENTSEEK_MODEL": "gpt-5-mini",
        "RUBRIC_GRADER_MODEL": "gpt-5-mini",
        "OPENAI_API_KEY": "",
        "OPENAI_API_BASE": "",
        "ANTHROPIC_API_KEY": "",
        "ANTHROPIC_API_URL": "",
        "GOOGLE_API_KEY": "",
        "GOOGLE_API_BASE": "",
        "LANGSMITH_TRACING": "false",
        "LANGSMITH_API_KEY": "",
        "LANGSMITH_PROJECT": "",
        "SEEKDB_EMBED": "true",
        "SEEKDB_EMBED_DIR": "~/.agentseek/rubric_lab/seekdb",
        "OCEANBASE_DB_NAME": "test",
    }


@pytest.mark.parametrize(
    ("provider", "default_model"),
    [
        ("openai", "gpt-5-mini"),
        ("anthropic", "claude-sonnet-4-6"),
        ("google", "gemini-2.5-flash"),
    ],
)
def test_rubric_provider_choice_renders_compatible_default_models(
    provider: str,
    default_model: str,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "rubric-provider-output"
    output_root.mkdir()
    generated = _render(
        TEMPLATES_ROOT / "langchain/rubric",
        output_root,
        tmp_path,
        extra_context={"default_provider": provider},
    )
    assignments = {
        name: value
        for raw_line in (generated / ".env.example").read_text(encoding="utf-8").splitlines()
        if (line := raw_line.strip()) and not line.startswith("#") and "=" in line
        for name, value in [line.split("=", maxsplit=1)]
    }

    assert assignments["AGENTSEEK_MODEL_PROVIDER"] == provider
    assert assignments["AGENTSEEK_MODEL"] == default_model
    assert assignments["RUBRIC_GRADER_MODEL"] == default_model


def test_rubric_lifecycle_keeps_live_models_optional_and_smokes_rendered_package(tmp_path: Path) -> None:
    generated = render_rubric(tmp_path)
    lifecycle = tomllib.loads((generated / ".agentseek" / "lifecycle.toml").read_text(encoding="utf-8"))

    assert lifecycle["env_file"] == ".env"
    for variable in (
        "AGENTSEEK_MODEL_PROVIDER",
        "AGENTSEEK_MODEL",
        "RUBRIC_GRADER_MODEL",
        "OPENAI_API_KEY",
        "OPENAI_API_BASE",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_API_URL",
        "GOOGLE_API_KEY",
        "GOOGLE_API_BASE",
    ):
        assert lifecycle["env"][variable]["required"] is False
    assert set(lifecycle["tasks"]) >= {"sync", "frontend", "rubric-smoke"}
    assert lifecycle["tasks"]["rubric-smoke"]["command"] == [
        "uv",
        "run",
        "python",
        "-m",
        "rubric_lab.smoke",
    ]


def test_rubric_readme_starts_with_the_keyless_first_run_sequence(tmp_path: Path) -> None:
    generated = render_rubric(tmp_path)
    readme = (generated / "README.md").read_text(encoding="utf-8")
    first_run = """```bash
cp .env.example .env
uvx agentseek task sync
uvx agentseek task frontend
uvx agentseek task rubric-smoke
uvx agentseek info
uvx agentseek doctor
uvx agentseek dev --dry-run
uvx agentseek dev
```"""

    assert first_run in readme


def test_rubric_readme_documents_acceptance_and_mode_boundaries(tmp_path: Path) -> None:
    generated = render_rubric(tmp_path)
    readme = " ".join((generated / "README.md").read_text(encoding="utf-8").split())

    assert "terminal `satisfied`" in readme
    assert "passing Evidence for the exact current candidate" in readme
    assert "Guided Demo needs no model key" in readme
    assert "Live Model reads provider settings only from server variables" in readme
    assert "not a sandbox" in readme
    assert "fresh thread" in readme
    for status in ("satisfied", "needs_revision", "max_iterations_reached", "failed", "grader_error"):
        assert f"`{status}`" in readme


def test_rubric_readmes_document_provider_native_server_setup(tmp_path: Path) -> None:
    generated = render_rubric(tmp_path)

    for readme_path in (TEMPLATES_ROOT / "langchain/rubric" / "README.md", generated / "README.md"):
        readme = " ".join(readme_path.read_text(encoding="utf-8").split())
        assert "`$EDITOR .env`" in readme
        assert "exactly one provider-native credential/base block" in readme
        assert "`AGENTSEEK_MODEL_PROVIDER`" in readme
        assert "`AGENTSEEK_MODEL`" in readme
        assert "`RUBRIC_GRADER_MODEL`" in readme
        assert "server" in readme
        assert "browser" in readme
        assert "`RUBRIC_API_KEY`" not in readme
        assert "`RUBRIC_PROVIDER`" not in readme
        assert "`RUBRIC_API_BASE`" not in readme
        assert "`RUBRIC_WORKER_MODEL`" not in readme


def test_rubric_readmes_record_exact_course_source_and_runtime_placement(tmp_path: Path) -> None:
    generated = render_rubric(tmp_path)
    source_url = (
        "https://github.com/datawhalechina/deepagents-in-action/blob/"
        "6fcef2294bc1ae19e97054426c1355923b50493a/content/ch13-grading-rubrics.md"
    )

    for readme_path in (TEMPLATES_ROOT / "langchain/rubric" / "README.md", generated / "README.md"):
        readme = " ".join(readme_path.read_text(encoding="utf-8").split())
        assert source_url in readme
        assert "generic LangChain `AgentMiddleware`" in readme
        assert "`create_agent`" in readme
        assert "`create_deep_agent`" in readme
        assert "Beta" in readme
        assert "characterization suite" in readme


def test_rubric_frontend_keeps_provider_credentials_out_of_browser_artifacts(tmp_path: Path) -> None:
    generated = render_rubric(tmp_path)
    frontend = generated / "frontend"
    production_files = [
        path
        for path in frontend.rglob("*")
        if path.is_file() and ".test." not in path.name and path.name != "package-lock.json"
    ]
    forbidden_names = (
        "RUBRIC_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
    )

    assert (frontend / ".env.example").is_file()
    for path in production_files:
        contents = path.read_text(encoding="utf-8")
        assert all(name not in contents for name in forbidden_names), path


def test_rubric_python_uses_plain_langchain_agent_boundary(tmp_path: Path) -> None:
    generated = render_rubric(tmp_path)

    for path in (generated / "src").rglob("*.py"):
        assert "create_deep_agent" not in path.read_text(encoding="utf-8"), path


@pytest.mark.parametrize(
    "forbidden_name",
    ("RUBRIC_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"),
)
def test_generated_frontend_bundle_guard_rejects_each_provider_credential_name(
    tmp_path: Path,
    forbidden_name: str,
) -> None:
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (assets / "index.js").write_bytes(f"window.__value='{forbidden_name}';".encode())

    completed = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "scripts" / "verify_generated_frontend_bundle.py"),
            str(dist),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert forbidden_name in completed.stderr


def test_generated_frontend_bundle_guard_accepts_clean_binary_assets(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (assets / "index.js").write_bytes(b"const mode='guided';\x00\xff")

    completed = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "scripts" / "verify_generated_frontend_bundle.py"),
            str(dist),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert completed.stderr == ""


def test_rubric_generated_smoke_job_exercises_fresh_keyless_project() -> None:
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "main.yml").read_text(encoding="utf-8")
    marker = "\n  rubric-generated-smoke:\n"

    assert marker in workflow
    job = workflow.split(marker, maxsplit=1)[1]
    assert "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" in job
    assert "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065" in job
    assert "actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020" in job
    assert "astral-sh/setup-uv@d0cc045d04ccac9d8b7881df0226f9e82c39688e" in job
    assert "cookiecutter templates/langchain/rubric" in job
    assert "cp .env.example .env" in job
    assert "uv sync --group test" in job
    assert "uv run python -m pytest -q" in job
    assert "uv run python -m rubric_lab.smoke" in job
    assert "npm test" in job
    assert "npm run build" in job
    build_position = job.index("npm run build")
    assert "Reject provider credential names from generated production bundle" in job
    bundle_guard_position = job.index("Reject provider credential names from generated production bundle")
    assert bundle_guard_position > build_position
    assert '"${GITHUB_WORKSPACE}/scripts/verify_generated_frontend_bundle.py" dist' in job
    assert "agentseek task rubric-smoke" in job
    assert "agentseek info" in job
    assert "agentseek doctor" in job
    assert "agentseek dev --dry-run" in job
    env_copy_position = job.index("cp .env.example .env")
    assert env_copy_position < job.index("agentseek task rubric-smoke")
    assert env_copy_position < job.index("agentseek info")
    assert env_copy_position < job.index("agentseek doctor")
    assert env_copy_position < job.index("agentseek dev --dry-run")
    assert "RUBRIC_API_KEY" not in job
    assert "secrets." not in job


def test_markdown_messages_generated_smoke_uses_declared_embedded_runtime() -> None:
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "main.yml").read_text(encoding="utf-8")
    marker = "\n  markdown-messages-generated-api-smoke:\n"

    assert marker in workflow
    job = workflow.split(marker, maxsplit=1)[1]
    assert "uv sync" in job
    assert "OPENAI_API_KEY=smoke-test-key" in job
    assert "LANGSMITH_TRACING=false" in job
    assert "fake_openai_server.py" in job
    assert "uv run agentseek-api dev --port 2024" in job
    assert "http://127.0.0.1:2024/health" in job
    assert "POST http://127.0.0.1:2024/assistants/search" in job
    assert "/threads/${thread_id}/runs" in job


def test_reviewer_local_runtime_matrix_matches_rendered_template_set() -> None:
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "main.yml").read_text(encoding="utf-8")
    matrix = workflow.split("  migrated-local-runtime-matrix:", maxsplit=1)[1]
    matrix_templates = {
        line.strip().split(":", maxsplit=1)[1].strip()
        for line in matrix.splitlines()
        if line.strip().startswith("- template:")
    }
    assert matrix_templates >= REVIEWER_LOCAL_RUNTIME_TEMPLATES
    assert matrix_templates <= set(INDEX)
    assert "template: deepagents/mcp\n            os: ubuntu-latest" in matrix
    assert "template: deepagents/mcp\n            os: windows-latest" in matrix
    for template_key in REVIEWER_LOCAL_RUNTIME_TEMPLATES:
        assert (TEMPLATES_ROOT / template_key).is_dir()
    assert '--template "${{ matrix.template }}"' in matrix
    assert '--output-root "${{ runner.temp }}/r/${{ matrix.id }}"' in matrix


def test_runtime_floor_smoke_rejects_empty_versions() -> None:
    script = REPOSITORY_ROOT / "scripts" / "runtime_floor_smoke.py"
    for option in ("--agentseek-api-version", "--pydantic-settings-version"):
        completed = subprocess.run(
            [sys.executable, str(script), option, "", "--pydantic-settings-version", "2.0.0"]
            if option == "--agentseek-api-version"
            else [sys.executable, str(script), "--agentseek-api-version", "0.0.0", option, ""],
            capture_output=True,
            text=True,
        )
        assert completed.returncode != 0


def test_runtime_floor_smoke_uses_public_main_app_import() -> None:
    script = (REPOSITORY_ROOT / "scripts" / "runtime_floor_smoke.py").read_text(encoding="utf-8")
    assert "from agentseek_api.main import app" in script
    assert "from agentseek_api.cli import app" not in script


def test_deepagents_streaming_template_keeps_langgraph_v3_contract(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    generated_path = _render(TEMPLATES_ROOT / "deepagents/streaming", output_root, tmp_path)

    pyproject = tomllib.loads((generated_path / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = set(pyproject["project"]["dependencies"])
    assert "langgraph-cli[inmem]>=0.4" in dependencies
    assert "deepagents==0.6.12" in dependencies
    assert not any(dependency.startswith("agentseek-api") for dependency in dependencies)

    graph_config = json.loads((generated_path / "langgraph.json").read_text(encoding="utf-8"))
    assert graph_config["dependencies"] == ["."]
    assert graph_config["graphs"]["streaming"].endswith(".agent:graph")
    assert graph_config["http"]["app"].endswith(".routes:app")

    env_example = (generated_path / ".env.example").read_text(encoding="utf-8")
    assert "SEEKDB_" not in env_example
    assert "OCEANBASE_DB_NAME" not in env_example

    route_source = next((generated_path / "src").glob("*/routes.py")).read_text(encoding="utf-8")
    adapter_source = next((generated_path / "src").glob("*/event_adapter.py")).read_text(encoding="utf-8")
    frontend_source = (generated_path / "frontend/src/EventTimeline.tsx").read_text(encoding="utf-8")
    generated_readme = (generated_path / "README.md").read_text(encoding="utf-8")
    assert "agentseek-api" not in generated_readme
    assert "agentseek task" not in generated_readme
    assert "uv run langgraph dev" in generated_readme
    for projection in ("subagents", "messages", "tool_calls", "values", "output"):
        assert projection in route_source
    assert 'version="v3"' in route_source
    assert "astream_events(" in route_source
    assert "stream_events(" not in route_source.replace("astream_events(", "")
    assert "while callable(value)" in route_source
    assert 'phase="failed"' in route_source

    lifecycle = tomllib.loads((generated_path / ".agentseek/lifecycle.toml").read_text(encoding="utf-8"))
    assert lifecycle["services"]["langgraph"]["tech"] == "langgraph"
    assert lifecycle["processes"]["langgraph"]["command"] == [
        "uv",
        "run",
        "langgraph",
        "dev",
        "--port",
        "2024",
        "--no-browser",
    ]
    assert lifecycle["checks"]["langgraph"]["target"] == "http://127.0.0.1:2024"
    assert "astream_events" in generated_readme
    assert 'version="v3"' in generated_readme
    for event_kind in ("message", "subagent", "tool_call", "values", "output", "raw", "error"):
        assert f'"kind": "{event_kind}"' in adapter_source
    assert "state snapshot" in frontend_source
