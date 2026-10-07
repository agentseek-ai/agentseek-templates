"""Check the provider payload rather than just the environment parser."""
import json
import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize("value, expected", [("", None), ("false", False), ("true", True)])
def test_parallel_tool_call_flag_reaches_provider_payload(value, expected):
    process = subprocess.run(
        [sys.executable, "-c", "from {{ cookiecutter.project_slug }}.agent import model; import json; print(json.dumps(model._get_request_payload([]).get('parallel_tool_calls')))"],
        env={**os.environ, "AGENTSEEK_PARALLEL_TOOL_CALLS": value,
             "AGENTSEEK_MODEL_PROVIDER": "openai", "AGENTSEEK_MODEL": "course-config",
             "OPENAI_API_KEY": "unused", "CONTENT_MODE": "text"},
        capture_output=True, text=True, check=False,
    )
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout) is expected


def test_invalid_parallel_tool_call_flag_fails_at_startup():
    process = subprocess.run(
        [sys.executable, "-c", "from {{ cookiecutter.project_slug }}.agent import graph"],
        env={**os.environ, "AGENTSEEK_PARALLEL_TOOL_CALLS": "sometimes",
             "AGENTSEEK_MODEL_PROVIDER": "openai", "AGENTSEEK_MODEL": "course-config",
             "OPENAI_API_KEY": "unused", "CONTENT_MODE": "text"},
        capture_output=True, text=True, check=False,
    )
    assert process.returncode != 0
    assert "AGENTSEEK_PARALLEL_TOOL_CALLS must be true or false" in process.stderr
