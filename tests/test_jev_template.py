from __future__ import annotations

import json
import tomllib
from pathlib import Path

from cookiecutter.main import cookiecutter

ROOT = Path(__file__).resolve().parents[1]


def test_jev_harness_renders_with_explicit_live_credentials(tmp_path: Path) -> None:
    registry = json.loads((ROOT / "templates/index.json").read_text())
    assert "langchain/jev-harness" in registry
    config = tmp_path / "cookiecutter.json"
    config.write_text(json.dumps({"replay_dir": str(tmp_path / "replay")}))
    generated = Path(
        cookiecutter(
            str(ROOT / "templates/langchain/jev-harness"),
            no_input=True,
            output_dir=str(tmp_path),
            config_file=str(config),
            extra_context={"project_name": "Custom Harness", "frontend_port": "5199", "langgraph_port": "2099"},
        )
    )
    lifecycle = tomllib.loads((generated / ".agentseek/lifecycle.toml").read_text())
    assert lifecycle["version"] == 2
    assert lifecycle["env"]["TYPESAFE_API_KEY"]["required"] is True
    assert lifecycle["env"]["OPENAI_API_KEY"]["required"] is True
    assert lifecycle["tasks"]["test"]["command"] == ["uv", "run", "--group", "test", "pytest"]
    assert lifecycle["tasks"]["live-smoke"]["command"][-1] == "custom_harness.live_smoke"
    dependencies = tomllib.loads((generated / "pyproject.toml").read_text())["project"]["dependencies"]
    assert "langchain-typesafe[experimental]==0.0.1a2" in dependencies
    assert "langchain==1.3.15" in dependencies
    assert "agentseek-api[embedded]==0.3.2" in dependencies
    env = (generated / ".env.example").read_text()
    assert "TYPESAFE_API_KEY=\n" in env
    assert "OPENAI_API_KEY=\n" in env
    assert "LANGSMITH_TRACING=false" in env
    assert "OPENAI_API_BASE=https://api.siliconflow.cn/v1" in env
    assert "JEV_FAST_MODEL=deepseek-ai/DeepSeek-V4-Flash" in env
    assert "JEV_POWERFUL_MODEL=deepseek-ai/DeepSeek-V4-Pro" in env
    assert lifecycle["env"]["CHAT_MODEL_EXTRA_BODY"]["default"] == '{"enable_thinking":false}'
    assert not (generated / ".env").exists()
    graph = json.loads((generated / "langgraph.json").read_text())
    assert graph["graphs"]["agent"] == "custom_harness.agent:make_graph"
    assert "http://127.0.0.1:5199" in graph["http"]["cors"]["allow_origins"]
    assert (generated / "tests/test_harness.py").is_file()
    assert (generated / "frontend/src/App.test.tsx").is_file()
