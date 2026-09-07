import pytest


def test_agentops_can_be_disabled_without_credentials(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENTBASE_AGENTOPS_ENABLED", "false")

    from agentbase_agentops_langchain import AgentOpsMiddleware

    middleware = AgentOpsMiddleware()

    assert middleware.active is False
    assert middleware.disabled_reason == "disabled by configuration"
    assert middleware.flush(timeout_millis=100) is True
