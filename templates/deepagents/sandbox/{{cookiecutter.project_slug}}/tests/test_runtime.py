from types import SimpleNamespace

import pytest

from {{ cookiecutter.project_slug }} import runtime, sandbox


def test_process_reuses_one_backend_and_deletes_it_once(monkeypatch):
    created = []
    deleted = []
    backend = object()

    def create_backend():
        created.append(backend)
        return backend, sandbox._best_effort_cleanup(
            lambda: deleted.append(backend),
            provider="daytona",
            sandbox_id="temporary",
        )

    monkeypatch.setattr(runtime, "_backend", runtime._UNINITIALIZED)
    monkeypatch.setattr(runtime, "_provider_cleanup", None)
    monkeypatch.setattr(runtime, "create_sandbox_backend", create_backend)
    monkeypatch.setattr(runtime.atexit, "register", lambda callback: None)

    assert runtime.get_backend() is backend
    assert runtime.get_backend() is backend
    runtime.cleanup_sandbox()
    runtime.cleanup_sandbox()
    assert created == [backend]
    assert deleted == [backend]


@pytest.mark.parametrize("provider", ["daytona", "langsmith"])
def test_missing_provider_credentials_fail_before_creating_a_sandbox(monkeypatch, provider):
    monkeypatch.delenv("DAYTONA_API_KEY", raising=False)
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="API_KEY is required"):
        sandbox.create_sandbox_backend(provider)


def test_daytona_factory_loads_real_workspace_adapter_and_owns_cleanup(monkeypatch):
    remote = SimpleNamespace(id="temporary", get_work_dir=lambda: "/home/daytona/workspace")
    deleted = []
    client = SimpleNamespace(create=lambda: remote, delete=lambda resource: deleted.append(resource))
    monkeypatch.setenv("DAYTONA_API_KEY", "dummy-key")
    monkeypatch.setattr("daytona.Daytona", lambda: client)

    backend, cleanup = sandbox.create_sandbox_backend("daytona")

    assert backend.id == "temporary"
    assert backend.workspace == "/home/daytona/workspace"
    assert backend._resolve_path("/code.py") == "/home/daytona/workspace/code.py"
    cleanup()
    cleanup()
    assert deleted == [remote]


def test_langsmith_factory_loads_real_backend_and_owns_cleanup(monkeypatch):
    remote = SimpleNamespace(name="temporary")
    deleted = []
    client = SimpleNamespace(create_sandbox=lambda: remote, delete_sandbox=lambda name: deleted.append(name))
    monkeypatch.setenv("LANGSMITH_API_KEY", "dummy-key")
    monkeypatch.setattr("langsmith.sandbox.SandboxClient", lambda: client)

    backend, cleanup = sandbox.create_sandbox_backend("langsmith")

    assert backend.id == "temporary"
    cleanup()
    cleanup()
    assert deleted == ["temporary"]
