from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

import pytest
from cookiecutter.main import cookiecutter

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("template", ["content-builder", "research"])
def test_course_lock_is_valid_for_custom_project_name(tmp_path: Path, template: str) -> None:
    """A learner must be able to use the reviewed lock with a renamed scaffold."""
    project = Path(
        cookiecutter(
            str(ROOT / "templates/deepagents" / template),
            no_input=True,
            default_config={"replay_dir": str(tmp_path / "replay")},
            output_dir=str(tmp_path),
            extra_context={"project_slug": "custom_course_agent", "default_model": "course-model"},
        )
    )
    lock_path = project / "uv.lock"
    assert lock_path.is_file(), "The course needs a shipped dependency lock"
    lock = tomllib.loads(lock_path.read_text())
    packages = {item["name"]: item for item in lock["package"]}
    assert packages["deepagents"]["version"] == "0.7.8"
    assert packages["agentseek-api"]["version"] == "0.2.3"
    assert packages["custom-course-agent"]["source"] == {"editable": "."}
    result = subprocess.run(
        ["uv", "lock", "--check", "--offline", "--project", str(project)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("template", "model"),
    [
        ("content-builder", "deepseek-ai/DeepSeek-V3.2"),
        ("research", "deepseek-ai/DeepSeek-V3.2"),
        ("mcp", "Qwen/Qwen2.5-7B-Instruct"),
    ],
)
def test_default_model_and_endpoint_match_real_validation(tmp_path: Path, template: str, model: str) -> None:
    project = Path(
        cookiecutter(
            str(ROOT / "templates/deepagents" / template),
            no_input=True,
            default_config={"replay_dir": str(tmp_path / "replay")},
            output_dir=str(tmp_path),
        )
    )
    assignments = {
        name.strip(): value.strip()
        for line in (project / ".env.example").read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#") and "=" in line
        for name, value in [line.split("=", 1)]
    }
    assert assignments["AGENTSEEK_MODEL_PROVIDER"] == "openai"
    assert assignments["AGENTSEEK_MODEL"] == model
    assert assignments["OPENAI_API_BASE"] == "https://api.siliconflow.cn/v1"
    assert assignments["OPENAI_API_KEY"] == ""
    if template == "mcp":
        assert assignments["AGENTSEEK_MODEL_API_KEY"] == ""
    else:
        assert assignments["AGENTSEEK_PARALLEL_TOOL_CALLS"] == "false"
    model_file = "model.py" if template == "mcp" else "agent.py"
    assert model in (project / "src" / project.name / model_file).read_text()
