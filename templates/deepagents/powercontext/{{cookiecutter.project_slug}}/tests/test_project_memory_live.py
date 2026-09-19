"""Optional real HTTP/database Memory checks; no model calls or fabricated recall."""

from __future__ import annotations

import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from langchain.messages import HumanMessage

os.environ.setdefault("OPENAI_API_KEY", "offline-test-key")

from {{ cookiecutter.project_slug }} import routes  # noqa: E402
from {{ cookiecutter.project_slug }}.powercontext_middleware import (  # noqa: E402
    prepare_context,
    recall_options,
)

pytestmark = pytest.mark.skipif(
    not os.getenv("POWERCONTEXT_TEST_URL"), reason="Set POWERCONTEXT_TEST_URL for a real Server"
)


@pytest.fixture
def project(monkeypatch):
    monkeypatch.setenv("POWERCONTEXT_URL", os.environ["POWERCONTEXT_TEST_URL"])
    monkeypatch.setenv("POWERCONTEXT_TOKEN", os.getenv("POWERCONTEXT_TEST_TOKEN", ""))
    monkeypatch.setenv("POWERCONTEXT_SCOPE_ID", "")
    monkeypatch.setenv("POWERCONTEXT_PROJECT_KEY", f"agentseek-live-{uuid4()}")
    monkeypatch.setenv("POWERCONTEXT_MAX_BYTES", "8000")
    return TestClient(routes.app)


@pytest.mark.anyio
async def test_explicit_write_fresh_recall_scope_isolation_and_disabled_run(project, monkeypatch):
    # A read before initialization must neither create a Scope nor use the Server default.
    assert project.get("/custom/memory").status_code == 409
    created = project.post("/custom/memory/initialize").json()
    assert project.post("/custom/memory/initialize").json() == created
    fact = "Project Phoenix release requires Mei approval in Singapore on Tuesday."
    saved = project.post("/custom/memory", json={"text": fact})
    assert saved.status_code == 200, saved.text
    assert saved.json()["entry"]["citation"]["entry_version_id"]
    assert project.get("/custom/memory").json()["entries"][0]["text"] == fact

    # This fresh request contains no previous conversation or saved fact.
    request = SimpleNamespace(messages=[HumanMessage(content="Project Phoenix release plan?")], system_message=None)
    content, status = await prepare_context(request)
    assert status["status"] == "ready", status
    assert fact in content
    assert status["scope_id"] == created["scope_id"]
    assert status["content_bytes"] == len(content.encode("utf-8")) <= status["max_bytes"]
    assert len(request.messages) == 1

    token = recall_options.set((False, None))
    try:
        assert await prepare_context(request) == (None, {"status": "disabled", "content_bytes": 0})
    finally:
        recall_options.reset(token)

    token = recall_options.set((True, 512))
    try:
        _, small = await prepare_context(request)
        assert small["status"] in {"ready", "empty"}
        assert small["content_bytes"] <= 512
    finally:
        recall_options.reset(token)
    assert project.get("/custom/memory").json()["entries"][0]["text"] == fact

    monkeypatch.setenv("POWERCONTEXT_PROJECT_KEY", f"agentseek-other-{uuid4()}")
    assert project.get("/custom/memory").status_code == 409
    other = project.post("/custom/memory/initialize").json()
    assert other["scope_id"] != created["scope_id"]
    assert project.get("/custom/memory").json()["entries"] == []
    content, status = await prepare_context(request)
    assert content is None and status["status"] == "empty"


def test_browser_cannot_choose_scope_or_write_blank_memory(project):
    for payload in ({"text": " "}, {"text": "decision", "scope_id": "another-project"}):
        assert project.post("/custom/memory", json=payload).status_code == 422
