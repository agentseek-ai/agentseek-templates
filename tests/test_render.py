from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
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
CORE_COMMIT = "2d91d5e8ab1b8eabae74c95057a5a0139e9b4abc"
EXPECTED_CORE_DEPENDENCIES = {
    "bub/default": {"agentseek-ag-ui"},
    "deepagents/content-builder": set(),
    "deepagents/default": {"agentseek-ag-ui", "agentseek-langchain"},
    "deepagents/mcp": set(),
    "deepagents/research": set(),
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
    }
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
    assert "actions/checkout@11d5960a326750d5838078e36cf38b85af677262" in job
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
