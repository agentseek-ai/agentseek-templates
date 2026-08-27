from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_model_request_rate_limit_env_attaches_single_burst_limiter() -> None:
    project_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.update(
        {
            "AGENTSEEK_MODEL_PROVIDER": "openai",
            "AGENTSEEK_MODEL": "gpt-4o-mini",
            "AGENTSEEK_MODEL_REQUESTS_PER_SECOND": "0.5",
            "OPENAI_API_KEY": "test-key",
            "OPENAI_API_BASE": "https://example.invalid/v1",
        }
    )
    code = """
from {{ cookiecutter.project_slug }}.agent import model
limiter = model.rate_limiter
print("none" if limiter is None else f"{limiter.requests_per_second}:{limiter.max_bucket_size}")
"""

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=project_root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "0.5:1"
