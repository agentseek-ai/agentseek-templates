from {{ cookiecutter.project_slug }}.patterns import PATTERNS


EXPECTED_ROLES = {
    "classify_and_act": ("bug-fixer", "feature-analyst", "support-agent"),
    "fan_out_and_synthesize": ("reviewer",),
    "adversarial_verification": ("reviewer", "verifier"),
    "generate_and_filter": ("architect",),
    "tournament": ("writer", "judge"),
    "loop_until_done": ("analyzer",),
}


def test_pattern_registry_covers_six_independent_assistants() -> None:
    assert tuple(PATTERNS) == tuple(EXPECTED_ROLES)
    assert {spec.assistant_id for spec in PATTERNS.values()} == set(EXPECTED_ROLES)
    for assistant_id, expected_roles in EXPECTED_ROLES.items():
        assert tuple(role.name for role in PATTERNS[assistant_id].subagents) == expected_roles


def test_example_prompts_are_natural_workflow_requests() -> None:
    forbidden = ("eval", "task()", "subagenttype", "responseschema")
    all_role_names = {role for roles in EXPECTED_ROLES.values() for role in roles}

    for spec in PATTERNS.values():
        prompt = spec.example_prompt
        lowered = prompt.lower()
        assert "workflow" in lowered
        assert not any(token in lowered for token in forbidden)
        assert not any(role in lowered for role in all_role_names)


def test_pattern_specific_completion_guards_are_explicit() -> None:
    assert "every request exactly once" in PATTERNS["classify_and_act"].coordinator_prompt
    assert "every discovered route" in PATTERNS["fan_out_and_synthesize"].coordinator_prompt
    assert "Only independently confirmed" in PATTERNS["adversarial_verification"].coordinator_prompt
    assert "three independent designs" in PATTERNS["generate_and_filter"].coordinator_prompt
    assert "5 → 3 → 2 → 1" in PATTERNS["tournament"].coordinator_prompt
    assert "four rounds" in PATTERNS["loop_until_done"].coordinator_prompt


def test_fixture_pattern_coordinators_name_the_supported_python_glob() -> None:
    fixture_patterns = (
        "fan_out_and_synthesize",
        "adversarial_verification",
        "loop_until_done",
    )

    for assistant_id in fixture_patterns:
        assert "`**/*.py`" in PATTERNS[assistant_id].coordinator_prompt


def test_fan_out_uses_one_first_pass_review_per_discovered_path() -> None:
    spec = PATTERNS["fan_out_and_synthesize"]

    assert "exactly one reviewer task per discovered path" in spec.coordinator_prompt
    assert "pass that path unchanged to read_file" in spec.subagents[0].system_prompt
