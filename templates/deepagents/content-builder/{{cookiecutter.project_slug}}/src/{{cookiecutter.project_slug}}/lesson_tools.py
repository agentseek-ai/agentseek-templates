"""Small local tools for the course; all paths stay inside the project."""
from __future__ import annotations

import json
import re
from pathlib import Path

from langchain_core.tools import tool

EXAMPLE_DIR = Path(__file__).resolve().parents[2]


def _path(*parts: str) -> Path:
    target = EXAMPLE_DIR.joinpath(*parts).resolve()
    if not target.is_relative_to(EXAMPLE_DIR.resolve()):
        raise ValueError("Path must stay inside the project")
    return target


def _slug(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", value):
        raise ValueError("Use a lowercase slug with letters, digits, underscores or hyphens")
    return value


@tool
def read_source(name: str) -> str:
    """Read a fixed course source by filename, such as planning.md or files.md."""
    if not re.fullmatch(r"[a-z0-9_-]+\.md", name):
        raise ValueError("Use a Markdown filename from sources/")
    return _path("sources", name).read_text(encoding="utf-8")


@tool
def save_report(slug: str, content: str) -> str:
    """Save a Markdown report to blogs/<slug>/post.md. Include headings and source paths."""
    target = _path("blogs", _slug(slug), "post.md")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Saved blogs/{slug}/post.md; use read_report to verify it."


@tool
def read_report(slug: str) -> str:
    """Read back blogs/<slug>/post.md to verify the actual saved report."""
    return _path("blogs", _slug(slug), "post.md").read_text(encoding="utf-8")


@tool
def save_preference(key: str, value: str) -> str:
    """Save an explicitly requested preference (language, tone, or format) for future threads."""
    if key not in {"language", "tone", "format"}:
        raise ValueError("Preference key must be language, tone, or format")
    if not value.strip() or len(value) > 200 or "\n" in value or "\r" in value:
        raise ValueError("Preference must be a single nonempty line of at most 200 characters")
    target = _path("memory", "preferences.md")
    entries = {}
    if target.exists():
        for line in target.read_text(encoding="utf-8").splitlines():
            if ": " in line and not line.startswith("#"):
                name, text = line.split(": ", 1)
                entries[name] = text
    entries[key] = value.strip()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# Saved preferences\n\n" + "".join(f"{k}: {v}\n" for k, v in sorted(entries.items())), encoding="utf-8")
    return target.read_text(encoding="utf-8")


@tool
def publish_report(slug: str) -> str:
    """Append a local test publication record after human approval. Does not publish externally."""
    report = _path("blogs", _slug(slug), "post.md")
    if not report.is_file():
        raise ValueError("Save and verify the report first")
    log = _path("reports", "publications.jsonl")
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"action": "publish_report", "report": f"blogs/{slug}/post.md"}) + "\n")
    return f"Recorded local test publication for blogs/{slug}/post.md"
