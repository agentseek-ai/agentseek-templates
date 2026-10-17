"""Interactive local setup. Secret inputs never echo or enter shell history."""
from __future__ import annotations

import getpass
import json
import os
import re
import tempfile
from pathlib import Path

from dotenv import dotenv_values

from .context import Settings


def main():
    path = Path(".env")
    current = dict(dotenv_values(path, interpolate=False)) if path.exists() else {}
    print("Context Lab · 本地配置 / local setup (no provider calls)")
    print("Use an endpoint and exact callable IDs enabled for your account.")
    default_provider = current.get("AGENTSEEK_MODEL_PROVIDER") or "openai"
    provider = input(f"Provider openai / anthropic [{default_provider}]: ").strip().lower() or default_provider
    current["AGENTSEEK_MODEL_PROVIDER"] = provider
    defaults = Settings.from_env(current)
    base_name = "OPENAI_BASE_URL" if provider == "openai" else "ANTHROPIC_BASE_URL"
    endpoint = input(f"{base_name} [{defaults.base_url}]: ").strip()
    current[base_name] = endpoint or defaults.base_url
    for name in (f"{provider.upper()}_API_KEY", "QUERIT_API_KEY"):
        value = getpass.getpass(f"{name} (hidden; Enter keeps existing): ").strip()
        current[name] = value or current.get(name) or ""
    current.setdefault("AGENTSEEK_MODELS_BASE_URL", "")
    current.setdefault("LANGSMITH_TRACING", "false")
    current.setdefault("LANGSMITH_API_KEY", "")
    current.setdefault("LANGSMITH_ENDPOINT", "https://apac.api.smith.langchain.com")
    current.setdefault("LANGSMITH_PROJECT", "{{ cookiecutter.project_slug }}")
    Settings.from_env(current)
    descriptor, temporary = tempfile.mkstemp(dir=Path.cwd())
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            for key, value in current.items():
                if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) and value is not None:
                    output.write(f"{key}={json.dumps(value, ensure_ascii=False)}\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print("Saved locally to .env (owner-only permissions). Restart server to load changes.")


if __name__ == "__main__":
    main()
