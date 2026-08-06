from __future__ import annotations

from types import SimpleNamespace

from {{ cookiecutter.project_slug }} import demo_binding


def test_build_agent_disables_responses_api_for_openai_provider(monkeypatch) -> None:
    registrations = []
    captured = {}

    monkeypatch.setattr(
        demo_binding,
        "register_provider_profile",
        lambda key, profile: registrations.append((key, profile)),
    )

    def fake_create_deep_agent(**kwargs):
        captured.update(kwargs)
        return "agent"

    monkeypatch.setattr(demo_binding, "create_deep_agent", fake_create_deep_agent)
    monkeypatch.setattr(
        demo_binding,
        "get_settings",
        lambda: SimpleNamespace(
            require_model=lambda: "openai:glm-5.2",
            apply_openai_env_bridge=lambda: None,
        ),
    )

    assert demo_binding.build_agent() == "agent"
    assert len(registrations) == 1
    key, profile = registrations[0]
    assert key == "openai"
    assert profile.init_kwargs["use_responses_api"] is False
    assert captured["model"] == "openai:glm-5.2"
    assert captured["tools"] == [demo_binding.outline_answer]
