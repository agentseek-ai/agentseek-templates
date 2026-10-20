"""Network-free shared inputs, provider configuration and approved memory."""
from __future__ import annotations

import json
import ipaddress
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

PROVIDER_BASES = {"openai": "https://api.openai.com/v1", "anthropic": "https://api.anthropic.com"}
REASONING_EFFORTS = {"minimal", "low", "medium", "high", "max", "none", "xhigh"}
CONTEXT_POLICY = {"max_output_tokens": 3000, "search_max_queries": 4, "search_results": 3,
                  "summary_trigger_tokens": 6000, "summary_keep_messages": 6, "recursion_limit": 32,
                  "request_timeout_seconds": 60, "request_max_retries": 1, "run_timeout_seconds": 180}


def validate_reasoning_effort(value):
    value = value.strip().lower()
    if value and value not in REASONING_EFFORTS:
        raise ValueError("Unknown reasoning effort. Use a supported level or leave it empty.")
    return value


def _env_integer(env, name, default, minimum, maximum):
    raw = (env.get(name) or "").strip()
    message = f"{name} must be an integer from {minimum} to {maximum}."
    try:
        value = int(raw) if raw else default
    except ValueError as error:
        raise ValueError(message) from error
    if not minimum <= value <= maximum:
        raise ValueError(message)
    return value


@dataclass(frozen=True)
class Settings:
    provider: str = "openai"
    api_key: str = field(default="", repr=False)
    querit_key: str = field(default="", repr=False)
    base_url: str = PROVIDER_BASES["openai"]
    models_base_url: str = ""
    tracing_enabled: bool = False
    trace_project: str = "context-lab"
    max_output_tokens: int = 3000
    recursion_limit: int = 32
    run_timeout_seconds: int = 180

    @property
    def context_policy(self):
        return dict(CONTEXT_POLICY, max_output_tokens=self.max_output_tokens,
                    recursion_limit=self.recursion_limit, run_timeout_seconds=self.run_timeout_seconds)

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        provider = (env.get("AGENTSEEK_MODEL_PROVIDER") or "openai").strip().lower()
        if provider not in PROVIDER_BASES:
            raise ValueError("Unknown model provider. Choose openai or anthropic.")
        prefix = provider.upper()
        alias = "OPENAI_API_BASE" if provider == "openai" else "ANTHROPIC_API_URL"
        base = (env.get(f"{prefix}_BASE_URL") or env.get(alias) or PROVIDER_BASES[provider]).strip().rstrip("/")
        models_base = (env.get("AGENTSEEK_MODELS_BASE_URL") or "").strip().rstrip("/")
        max_output_tokens = _env_integer(env, "CONTEXT_LAB_MAX_OUTPUT_TOKENS", 3000, 128, 32768)
        recursion_limit = _env_integer(env, "CONTEXT_LAB_RECURSION_LIMIT", 32, 8, 256)
        run_timeout_seconds = _env_integer(env, "CONTEXT_LAB_RUN_TIMEOUT_SECONDS", 180, 30, 1800)
        for url in (base, models_base):
            if not url:
                continue
            try:
                parsed = urlsplit(url)
                host = parsed.hostname
                parsed.port  # Validate the optional port as well as the hostname.
                try:
                    loopback = bool(host and ipaddress.ip_address(host).is_loopback)
                except ValueError:
                    loopback = host == "localhost"
                valid_scheme = parsed.scheme == "https" or (parsed.scheme == "http" and loopback)
                valid = (valid_scheme and host and parsed.username is None and parsed.password is None
                         and not parsed.query and not parsed.fragment)
            except ValueError:
                valid = False
            if not valid:
                raise ValueError("The base URL must use HTTPS (or HTTP on loopback) without credentials, query or fragment.")
        return cls(provider=provider, api_key=(env.get(f"{prefix}_API_KEY") or "").strip(),
                   querit_key=(env.get("QUERIT_API_KEY") or "").strip(), base_url=base, models_base_url=models_base,
                   tracing_enabled=(env.get("LANGSMITH_TRACING") or "false").strip().lower() in {"true", "1", "yes", "on"},
                   trace_project=(env.get("LANGSMITH_PROJECT") or "context-lab").strip(),
                   max_output_tokens=max_output_tokens, recursion_limit=recursion_limit,
                   run_timeout_seconds=run_timeout_seconds)

    def require_model_key(self):
        if not self.api_key:
            raise ValueError(f"Fill before provider access: {self.provider.upper()}_API_KEY")

    def effective_options(self, reasoning_effort=""):
        effort = validate_reasoning_effort(reasoning_effort)
        return {"reasoning_effort": (effort or None) if self.provider == "openai" else None}

    def require_live(self, model_id, reasoning_effort=""):
        self.require_model_key()
        if not self.querit_key:
            raise ValueError("Fill before Live comparison: QUERIT_API_KEY")
        if not model_id.strip() or len(model_id) > 120:
            raise ValueError("Select or enter an exact model ID (1 to 120 characters).")
        self.effective_options(reasoning_effort)
        return model_id.strip()


class MemoryStore:
    """Only an explicit user action can persist memory; graph state is ephemeral."""
    def __init__(self, path):
        self.path = Path(path)

    def read(self):
        if not self.path.exists():
            return ""
        text = json.loads(self.path.read_text(encoding="utf-8"))["text"]
        if not isinstance(text, str) or len(text) > 6000:
            raise ValueError("Saved memory must contain text of at most 6000 characters.")
        return text

    def save(self, text, *, approved):
        if not approved:
            raise ValueError("Explicit user approval is required to persist memory.")
        if not isinstance(text, str) or len(text) > 6000:
            raise ValueError("Memory must contain at most 6000 characters.")
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary = tempfile.mkstemp(dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                json.dump({"text": text}, output, ensure_ascii=False)
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def fixture_run(prompt, language, model_id, memory):
    """Illustrative content, never a recorded model run or benchmark."""
    zh = language == "zh"
    labels = ["原文外置", "可恢复摘要", "按需加载技能", "隔离研究子任务", "读取已批准记忆"] if zh else [
        "Offload source", "Recoverable summary", "Load skill on demand", "Isolate research", "Load approved memory"]
    details = ([
        "/sources/example.md → 短预览与可回读路径",
        "/conversation_history/example.md → 摘要与可恢复原文",
        "/skills/research-brief/SKILL.md → 只加载相关指引",
        "researcher → 精简发现、证据与不确定性",
        "/memories/AGENTS.md → 用户已批准的记忆快照",
    ] if zh else [
        "/sources/example.md → preview + retrievable path",
        "/conversation_history/example.md → summary + recoverable original",
        "/skills/research-brief/SKILL.md → relevant instructions only",
        "researcher → bounded findings, evidence and uncertainty",
        "/memories/AGENTS.md → user-approved snapshot",
    ])
    report = ("# 演示研究简报\n\n这是离线示意数据，不是模型执行结果。\n\n任务：" if zh else
              "# Illustrative research brief\n\nOffline fixture, not model execution.\n\nTask: ") + prompt
    report += "\n\n" + ("保留原文，按需读取；摘要保留指向原文的路径；只在必要时加载技能。" if zh else
                          "Keep originals retrievable; summaries retain source paths; load skills only when useful.")
    return {"execution": "fixture", "model": model_id or "illustrative / no model", "memory": memory,
            "answer": report, "files": {"/reports/brief.md": report, "/sources/example.md":
            "Illustrative source file. No network request was made.",
            "/conversation_history/example.md":
                "# Illustrative conversation history / 对话历史示意\n\n"
                "Earlier task: compare two approaches. Evidence: preserve full source files and cite their paths.\n"
                "示例历史：比较两个方案，保留完整来源并引用文件路径。\n\n"
                "This is a teaching fixture, not actual summarized conversation history.\n"
                "这是教学示例，没有发生真实的摘要调用。",
            "/skills/research-brief/SKILL.md":
                "---\nname: research-brief\ndescription: Illustrative research brief skill / 研究简报技能示意\n---\n"
                "Return concise findings, direct source links and uncertainty. Preserve source files.\n"
                "用精简发现、直接来源链接与不确定性组织简报，保留完整原文。\n\n"
                "Illustrative fixture only; no skill was loaded by a model in this offline demo.\n"
                "离线教学示例，没有模型实际加载本技能。",
            "/memories/AGENTS.md": memory},
            "events": [{"kind": "illustration", "name": name, "detail": detail} for name, detail in zip(labels, details)],
            "metrics": {"provider_calls": 0, "search_calls": 0, "tokens": None, "elapsed_ms": 0}}
