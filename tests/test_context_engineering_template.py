from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT / "templates/deepagents/context-engineering/{{cookiecutter.project_slug}}/src/{{cookiecutter.project_slug}}"
)


def _context_module():
    path = SOURCE / "context.py"
    spec = importlib.util.spec_from_file_location("context_lab_core", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), module.__dict__)
    return module


@pytest.mark.parametrize(
    ("provider", "key_name", "canonical_base", "base_alias", "official_base"),
    [
        ("openai", "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "https://api.openai.com/v1"),
        ("anthropic", "ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "ANTHROPIC_API_URL", "https://api.anthropic.com"),
    ],
)
def test_selected_protocol_uses_own_key_endpoint_and_requires_explicit_model(
    provider, key_name, canonical_base, base_alias, official_base
):
    core = _context_module()
    env = {
        "AGENTSEEK_MODEL_PROVIDER": provider,
        "OPENAI_API_KEY": "openai-private",
        "ANTHROPIC_API_KEY": "anthropic-private",
        "QUERIT_API_KEY": "search-private",
        canonical_base: "https://canonical.example/v1",
        base_alias: "https://alias.example/v1",
    }
    settings = core.Settings.from_env(env)
    assert settings.provider == provider
    assert settings.api_key == env[key_name]
    assert settings.base_url == "https://canonical.example/v1"
    assert settings.require_live("selected-model", "") == "selected-model"
    with pytest.raises(ValueError, match="model"):
        settings.require_live("", "")
    del env[canonical_base]
    assert core.Settings.from_env(env).base_url == "https://alias.example/v1"
    del env[base_alias]
    assert core.Settings.from_env(env).base_url == official_base
    del env[key_name]
    with pytest.raises(ValueError, match=key_name):
        core.Settings.from_env(env).require_live("selected-model", "")
    assert "private" not in repr(settings)


def test_model_discovery_needs_only_selected_model_key_but_live_also_needs_search():
    core = _context_module()
    settings = core.Settings.from_env({"OPENAI_API_KEY": "private"})
    settings.require_model_key()
    with pytest.raises(ValueError, match="QUERIT_API_KEY"):
        settings.require_live("user-model", "")


def test_unknown_provider_and_unsafe_endpoint_are_rejected():
    core = _context_module()
    with pytest.raises(ValueError, match="provider"):
        core.Settings.from_env({"AGENTSEEK_MODEL_PROVIDER": "unconfigured"})
    for base in ("http://example.com/v1", "https://secret@example.com/v1", "https://example.com/v1?key=x"):
        with pytest.raises(ValueError, match="base URL"):
            core.Settings.from_env({"OPENAI_BASE_URL": base})


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize("base", ["http://localhost:11434/v1", "http://127.0.0.1:8000/v1", "http://[::1]:8000/v1"])
def test_local_compatible_endpoints_work_for_inference_and_model_discovery(provider, base):
    core = _context_module()
    settings = core.Settings.from_env(
        {"AGENTSEEK_MODEL_PROVIDER": provider, f"{provider.upper()}_BASE_URL": base, "AGENTSEEK_MODELS_BASE_URL": base}
    )
    assert settings.base_url == base
    assert settings.models_base_url == base


def test_reasoning_is_explicit_per_candidate_and_only_effective_for_openai():
    core = _context_module()
    settings = core.Settings.from_env({})
    assert settings.effective_options("") == {"reasoning_effort": None}
    assert settings.effective_options("low") == {"reasoning_effort": "low"}
    assert core.Settings.from_env({"AGENTSEEK_MODEL_PROVIDER": "anthropic"}).effective_options("high") == {
        "reasoning_effort": None
    }
    with pytest.raises(ValueError, match="reasoning effort"):
        settings.effective_options("turbo")


def test_memory_requires_approval_and_persists_owner_only(tmp_path):
    core = _context_module()
    path = tmp_path / "memory.json"
    store = core.MemoryStore(path)
    with pytest.raises(ValueError, match="approval"):
        store.save("Use short bullets", approved=False)
    assert not path.exists()
    store.save("Use short bullets", approved=True)
    assert core.MemoryStore(path).read() == "Use short bullets"
    assert path.stat().st_mode & 0o077 == 0
    store.save("", approved=True)
    assert core.MemoryStore(path).read() == ""


def test_fixture_is_bilingual_inspectable_and_not_a_model_benchmark():
    core = _context_module()
    for language in ("zh", "en"):
        result = core.fixture_run("Research", language, "user-selected-id", "Approved preference")
        assert result["execution"] == "fixture"
        assert result["metrics"]["provider_calls"] == 0
        assert result["metrics"]["tokens"] is None
        assert result["memory"] == "Approved preference"
        assert "/conversation_history/example.md" in result["files"]
        assert "/skills/research-brief/SKILL.md" in result["files"]
        assert "mode" not in result


def test_tracing_defaults_off_and_uses_explicit_standard_project():
    core = _context_module()
    assert not core.Settings.from_env({}).tracing_enabled
    settings = core.Settings.from_env({"LANGSMITH_TRACING": "true", "LANGSMITH_PROJECT": "my-compare"})
    assert settings.tracing_enabled
    assert settings.trace_project == "my-compare"


def test_optional_model_catalog_base_is_separate_from_inference_endpoint():
    core = _context_module()
    settings = core.Settings.from_env(
        {"OPENAI_BASE_URL": "https://inference.example/v1", "AGENTSEEK_MODELS_BASE_URL": "https://catalog.example/v1"}
    )
    assert settings.base_url == "https://inference.example/v1"
    assert settings.models_base_url == "https://catalog.example/v1"
    with pytest.raises(ValueError, match="base URL"):
        core.Settings.from_env({"AGENTSEEK_MODELS_BASE_URL": "https://secret@catalog.example/v1"})
