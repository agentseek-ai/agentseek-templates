import asyncio
import os
from types import SimpleNamespace

import pytest
from deepagents.backends import LocalShellBackend

from {{ cookiecutter.project_slug }}.sandbox import create_sandbox_backend


@pytest.mark.parametrize("asynchronous", [False, True])
def test_langsmith_path_glob_search_executes_the_real_upstream_script(tmp_path, monkeypatch, asynchronous):
    (tmp_path / "evidence.txt").write_text("needle one\nneedle two\n")
    local = LocalShellBackend(root_dir=tmp_path, env={"PATH": os.environ["PATH"]})

    def run(command, **kwargs):
        result = local.execute(command, **kwargs)
        return SimpleNamespace(stdout=result.output, stderr="", exit_code=result.exit_code)

    async def async_run(command, **kwargs):
        return await asyncio.to_thread(run, command, **kwargs)

    async_remote = SimpleNamespace(run=async_run)
    remote = SimpleNamespace(
        name="local-sdk-boundary",
        run=run,
        _client=SimpleNamespace(to_async=lambda: SimpleNamespace()),
        to_async=lambda **kwargs: async_remote,
    )
    client = SimpleNamespace(create_sandbox=lambda: remote, delete_sandbox=lambda name: None)
    monkeypatch.setenv("LANGSMITH_API_KEY", "dummy-key")
    monkeypatch.setattr("langsmith.sandbox.SandboxClient", lambda: client)
    backend, cleanup = create_sandbox_backend("langsmith")

    if asynchronous:
        result = asyncio.run(backend.agrep("needle", str(tmp_path), "**/*.txt", max_count=1))
    else:
        result = backend.grep("needle", str(tmp_path), "**/*.txt", max_count=1)

    assert result.error is None
    assert result.truncated is True
    assert result.matches == [{"path": str(tmp_path / "evidence.txt"), "line": 1, "text": "needle one"}]
    cleanup()
