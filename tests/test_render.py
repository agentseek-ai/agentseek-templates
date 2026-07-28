from __future__ import annotations

import json
import shutil
import tomllib
from pathlib import Path

import pytest
from agentseek.cli.lifecycle import normalize_lifecycle
from agentseek.cli.lifecycle.authored import LifecycleSpecV2
from agentseek.cli.lifecycle.spec import read_lifecycle_spec
from cookiecutter.main import cookiecutter

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_ROOT = REPOSITORY_ROOT / "templates"
INDEX = json.loads((TEMPLATES_ROOT / "index.json").read_text(encoding="utf-8"))
CORE_REPOSITORY = "https://github.com/ob-labs/agentseek.git"
CORE_COMMIT = "883addad1e2993c4be6fc8ba053f87f25fb5057a"
EXPECTED_CORE_DEPENDENCIES = {
    "bub/default": {"agentseek-ag-ui"},
    "deepagents/content-builder": set(),
    "deepagents/default": {"agentseek-ag-ui", "agentseek-langchain"},
    "deepagents/research": set(),
    "deepagents/sandbox": set(),
    "langchain/agentic-rag": set(),
    "langchain/agentic-rag-hybrid": set(),
    "langchain/agentic-rag-openvino": set(),
    "langchain/cli-remote": {"agentseek-langchain"},
    "langchain/default": {"agentseek-ag-ui", "agentseek-langchain"},
    "langchain/markdown-messages": set(),
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
}


def _registered_templates() -> list[tuple[str, Path]]:
    return [(key, TEMPLATES_ROOT / key) for key in sorted(INDEX)]


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

    assert "--no-browser" in spec.processes["langgraph"].command
