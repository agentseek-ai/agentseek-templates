from __future__ import annotations

from {{ cookiecutter.project_slug }}.tools import (
    MAX_PAGE_CHARS,
    MAX_TOTAL_CHARS,
    fetch_webpage_content,
)


def test_fetch_failure_is_a_bounded_marker(monkeypatch) -> None:
    def fail(*_args, **_kwargs):
        raise RuntimeError("offline")

    monkeypatch.setattr("{{ cookiecutter.project_slug }}.tools.httpx.get", fail)
    result = fetch_webpage_content("https://example.invalid")
    assert result.startswith("[抓取失败：")
    assert len(result) < MAX_PAGE_CHARS
    assert MAX_TOTAL_CHARS == 10_000
