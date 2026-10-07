"""Exercise the Daytona adapter against real local files instead of a cloud SDK."""

import asyncio
import os
from types import SimpleNamespace

import pytest
from deepagents.backends import LocalShellBackend
from deepagents.backends.sandbox import BaseSandbox
from langchain_daytona import DaytonaSandbox

from {{ cookiecutter.project_slug }}.sandbox import _daytona_backend_with_workspace


@pytest.fixture
def workspace_backend(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    local = LocalShellBackend(root_dir=workspace, virtual_mode=False, env={"PATH": os.environ["PATH"]})
    monkeypatch.setattr(DaytonaSandbox, "execute", lambda self, command, **kwargs: local.execute(command, **kwargs))
    monkeypatch.setattr(DaytonaSandbox, "upload_files", lambda self, files: local.upload_files(files))
    monkeypatch.setattr(DaytonaSandbox, "download_files", lambda self, paths: local.download_files(paths))
    # Daytona runs GNU grep in Linux; the local backend keeps this boundary
    # portable while still searching real files and applying the match limit.
    monkeypatch.setattr(DaytonaSandbox, "grep", lambda self, *args, **kwargs: local.grep(*args, **kwargs))

    async def local_agrep(self, *args, **kwargs):
        return await local.agrep(*args, **kwargs)

    monkeypatch.setattr(DaytonaSandbox, "agrep", local_agrep)
    return _daytona_backend_with_workspace(SimpleNamespace(id="local-sdk-boundary"), str(workspace)), workspace


@pytest.mark.parametrize("asynchronous", [False, True])
def test_workspace_grep_forwards_match_limit_and_reports_logical_paths(workspace_backend, asynchronous):
    backend, workspace = workspace_backend
    (workspace / "evidence.txt").write_text("needle one\nneedle two\n")

    if asynchronous:
        result = asyncio.run(backend.agrep("needle", "/", "**/*.txt", max_count=1))
    else:
        result = backend.grep("needle", "/", "**/*.txt", max_count=1)

    assert result.error is None
    assert len(result.matches) == 1
    assert result.matches[0]["path"] == "/evidence.txt"
    assert result.matches[0]["text"] == "needle one"


@pytest.mark.parametrize("asynchronous", [False, True])
def test_workspace_delete_reports_logical_path_and_removes_workspace_file(workspace_backend, asynchronous):
    backend, workspace = workspace_backend
    target = workspace / "disposable.txt"
    target.write_text("temporary fixture")

    if asynchronous:
        result = asyncio.run(backend.adelete(str(target)))
    else:
        result = backend.delete(str(target))

    assert result.error is None
    assert result.path == "/disposable.txt"
    assert not target.exists()


@pytest.mark.parametrize("asynchronous", [False, True])
def test_workspace_delete_rejects_traversal_before_touching_other_files(workspace_backend, asynchronous):
    backend, workspace = workspace_backend
    outside = workspace.parent / "outside.txt"
    outside.write_text("must remain outside the agent workspace")

    with pytest.raises(ValueError, match="inside the writable workspace"):
        if asynchronous:
            asyncio.run(backend.adelete("../outside.txt"))
        else:
            backend.delete("../outside.txt")

    assert outside.read_text() == "must remain outside the agent workspace"


def test_workspace_file_operations_keep_their_existing_logical_paths(workspace_backend):
    backend, workspace = workspace_backend
    assert backend.write("/example.txt", "before").path == "/example.txt"
    assert (workspace / "example.txt").read_text() == "before"
    assert backend.edit("example.txt", "before", "after").path == "/example.txt"
    assert backend.read("/example.txt").file_data["content"] == "after"
    assert [entry["path"] for entry in backend.ls("/").entries] == ["/example.txt"]
    assert [entry["path"] for entry in backend.glob("*.txt", "/").matches] == ["/example.txt"]
    assert backend.download_files(["/example.txt"])[0].content == b"after"


@pytest.mark.parametrize("asynchronous", [False, True])
def test_workspace_grep_executes_path_globs_without_shell_quote_errors(workspace_backend, monkeypatch, asynchronous):
    backend, workspace = workspace_backend
    # Exercise DeepAgents' actual sandbox search command on this portable
    # Python-glob route rather than the platform-specific GNU grep route.
    monkeypatch.setattr(DaytonaSandbox, "grep", BaseSandbox.grep)
    monkeypatch.setattr(DaytonaSandbox, "agrep", BaseSandbox.agrep)
    source = workspace / "src files"
    source.mkdir()
    (source / "evidence.py").write_text("needle one\nneedle two\n")

    if asynchronous:
        result = asyncio.run(backend.agrep("needle", "/", "src files/**/*.py", max_count=1))
    else:
        result = backend.grep("needle", "/", "src files/**/*.py", max_count=1)

    assert result.error is None
    assert result.truncated is True
    assert result.matches == [{"path": "/src files/evidence.py", "line": 1, "text": "needle one"}]


@pytest.mark.parametrize(("command", "output"), [
    ("printf '%s' '\"keep quotes\"' && printf '%s' ' /next'", '"keep quotes" /next'),
    ('python3 -c "print(\'user command\')" 2>/dev/null', "user command"),
])
def test_workspace_execute_preserves_ordinary_shell_commands(workspace_backend, command, output):
    backend, _ = workspace_backend

    result = backend.execute(command)

    assert result.exit_code == 0
    assert result.output.strip() == output


def test_workspace_execute_preserves_shell_expansion_in_user_python_scripts(workspace_backend):
    backend, workspace = workspace_backend

    result = backend.execute('python3 -c "\nimport os\nprint(\'$PWD\')\n" 2>/dev/null')

    assert result.exit_code == 0
    assert result.output.strip() == str(workspace)
