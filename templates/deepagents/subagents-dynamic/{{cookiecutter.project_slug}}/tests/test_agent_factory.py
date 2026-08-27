from pathlib import Path

from {{ cookiecutter.project_slug }} import agent_factory
from {{ cookiecutter.project_slug }}.patterns import PATTERNS


def test_each_pattern_builds_an_isolated_dynamic_agent(tmp_path: Path, monkeypatch) -> None:
    captured_agents: list[dict[str, object]] = []
    captured_interpreters: list[dict[str, object]] = []
    registered: list[tuple[str, object]] = []

    class FakeInterpreter:
        def __init__(self, **kwargs: object) -> None:
            captured_interpreters.append(kwargs)

    def fake_create_deep_agent(**kwargs: object) -> object:
        captured_agents.append(kwargs)
        return object()

    def fake_register_harness_profile(key: str, profile: object) -> None:
        registered.append((key, profile))

    monkeypatch.setattr(agent_factory, "CodeInterpreterMiddleware", FakeInterpreter)
    monkeypatch.setattr(agent_factory, "create_deep_agent", fake_create_deep_agent)
    monkeypatch.setattr(agent_factory, "register_harness_profile", fake_register_harness_profile)
    monkeypatch.setattr(agent_factory, "_registered_providers", set())

    model = object()
    examples_root = tmp_path / "examples"
    for spec in PATTERNS.values():
        if spec.fixture_directory:
            (examples_root / spec.fixture_directory).mkdir(parents=True)
        agent_factory.build_pattern_graph(model, spec, examples_root, "openai")

    assert len(captured_agents) == 6
    assert len(captured_interpreters) == 6
    assert len(registered) == 1
    assert registered[0][0] == "openai"
    assert registered[0][1].general_purpose_subagent.enabled is False

    expected_roles = {
        "classify_and_act": ["bug-fixer", "feature-analyst", "support-agent"],
        "fan_out_and_synthesize": ["reviewer"],
        "adversarial_verification": ["reviewer", "verifier"],
        "generate_and_filter": ["architect"],
        "tournament": ["writer", "judge"],
        "loop_until_done": ["analyzer"],
    }
    for spec, agent, interpreter in zip(PATTERNS.values(), captured_agents, captured_interpreters, strict=True):
        assert agent["model"] is model
        assert [subagent["name"] for subagent in agent["subagents"]] == expected_roles[spec.assistant_id]
        assert "harness_profile" not in agent
        assert interpreter["mode"] == "turn"
        assert interpreter["subagents"] is True
        assert interpreter["timeout"] == 300.0
        assert interpreter["memory_limit"] == 32 * 1024 * 1024
        assert interpreter["max_result_chars"] == 24_000

        ptc_names = [tool.name for tool in interpreter["ptc"]]
        if spec.fixture_directory:
            assert ptc_names == ["glob"]
            for subagent in agent["subagents"]:
                assert [tool.name for tool in subagent["tools"]] == ["read_file"]
        else:
            assert ptc_names == []
            for subagent in agent["subagents"]:
                assert subagent.get("tools", []) == []


def test_provider_profile_registration_is_idempotent(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(agent_factory, "register_harness_profile", lambda key, profile: calls.append(key))
    monkeypatch.setattr(agent_factory, "_registered_providers", set())

    agent_factory.ensure_harness_profile("openai")
    agent_factory.ensure_harness_profile("openai")

    assert calls == ["openai"]
