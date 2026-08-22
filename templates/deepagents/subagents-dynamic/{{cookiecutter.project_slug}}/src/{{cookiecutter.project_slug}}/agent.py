"""Provider binding and six exported Dynamic Subagents graphs."""

from __future__ import annotations

import os
import warnings
from pathlib import Path

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.rate_limiters import InMemoryRateLimiter

from {{ cookiecutter.project_slug }}.agent_factory import build_pattern_graph
from {{ cookiecutter.project_slug }}.patterns import PATTERNS

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_ROOT = PROJECT_ROOT / "examples"
SUPPORTED_MODEL_PROVIDERS = {
    "openai": "openai",
    "anthropic": "anthropic",
    "google": "google_genai",
    "google_genai": "google_genai",
    "gemini": "google_genai",
}


def _nonempty_env(name: str) -> str | None:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else None


def _normalize_provider(value: str) -> str:
    provider = value.strip().replace("-", "_").lower()
    if provider not in SUPPORTED_MODEL_PROVIDERS:
        raise ValueError("AGENTSEEK_MODEL_PROVIDER must be openai, anthropic, or google_genai")
    return SUPPORTED_MODEL_PROVIDERS[provider]


MODEL = (
    _nonempty_env("AGENTSEEK_MODEL")
    or _nonempty_env("DEEPAGENTS_MODEL")
    or _nonempty_env("BUB_MODEL")
    or "{{ cookiecutter.default_model }}"
)
MODEL_PROVIDER = _normalize_provider(
    os.getenv("AGENTSEEK_MODEL_PROVIDER", "{{ cookiecutter.default_model_provider }}")
)

model_kwargs: dict[str, object] = {
    "model": MODEL,
    "model_provider": MODEL_PROVIDER,
    "temperature": 0,
    "max_retries": 3,
}
requests_per_second = _nonempty_env("AGENTSEEK_MODEL_REQUESTS_PER_SECOND")
if requests_per_second:
    try:
        parsed_requests_per_second = float(requests_per_second)
    except ValueError:
        warnings.warn("Ignoring invalid AGENTSEEK_MODEL_REQUESTS_PER_SECOND", stacklevel=2)
    else:
        if parsed_requests_per_second <= 0:
            warnings.warn("Ignoring non-positive AGENTSEEK_MODEL_REQUESTS_PER_SECOND", stacklevel=2)
        else:
            model_kwargs["rate_limiter"] = InMemoryRateLimiter(
                requests_per_second=parsed_requests_per_second,
                check_every_n_seconds=0.1,
                max_bucket_size=1,
            )
if MODEL_PROVIDER == "openai":
    if _nonempty_env("OPENAI_API_KEY"):
        model_kwargs["api_key"] = _nonempty_env("OPENAI_API_KEY")
    if _nonempty_env("OPENAI_API_BASE"):
        model_kwargs["base_url"] = _nonempty_env("OPENAI_API_BASE")
    timeout_value = _nonempty_env("LANGCHAIN_OPENAI_STREAM_CHUNK_TIMEOUT_S")
    stream_chunk_timeout: float | None = 300.0
    if timeout_value:
        try:
            parsed_timeout = float(timeout_value)
        except ValueError:
            warnings.warn("Ignoring invalid LANGCHAIN_OPENAI_STREAM_CHUNK_TIMEOUT_S", stacklevel=2)
        else:
            stream_chunk_timeout = None if parsed_timeout <= 0 else parsed_timeout
    model_kwargs["stream_chunk_timeout"] = stream_chunk_timeout
elif MODEL_PROVIDER == "anthropic":
    if _nonempty_env("ANTHROPIC_API_KEY"):
        model_kwargs["api_key"] = _nonempty_env("ANTHROPIC_API_KEY")
    if _nonempty_env("ANTHROPIC_API_URL"):
        model_kwargs["base_url"] = _nonempty_env("ANTHROPIC_API_URL")
else:
    if _nonempty_env("GOOGLE_API_KEY"):
        model_kwargs["api_key"] = _nonempty_env("GOOGLE_API_KEY")
    if _nonempty_env("GOOGLE_API_BASE"):
        model_kwargs["base_url"] = _nonempty_env("GOOGLE_API_BASE")

model = init_chat_model(**model_kwargs)


def _build(assistant_id: str):
    return build_pattern_graph(model, PATTERNS[assistant_id], EXAMPLES_ROOT, MODEL_PROVIDER)


classify_and_act = _build("classify_and_act")
fan_out_and_synthesize = _build("fan_out_and_synthesize")
adversarial_verification = _build("adversarial_verification")
generate_and_filter = _build("generate_and_filter")
tournament = _build("tournament")
loop_until_done = _build("loop_until_done")
