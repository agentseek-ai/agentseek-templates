"""Bounded Tavily research tools for the LangChain agent."""

from __future__ import annotations

import os

import httpx
from langchain_core.tools import tool
from markdownify import markdownify
from tavily import TavilyClient

MAX_PAGE_CHARS = 4_000
MAX_TOTAL_CHARS = 10_000


def fetch_webpage_content(url: str, timeout: float = 15.0) -> str:
    """Fetch one page as bounded Markdown; return a safe error on failure."""
    try:
        response = httpx.get(url, timeout=timeout, follow_redirects=True)
        response.raise_for_status()
        text = markdownify(response.text).strip()
        if len(text) > MAX_PAGE_CHARS:
            return text[:MAX_PAGE_CHARS] + "\n[内容已截断：最多保留 4,000 个字符]"
        return text
    except Exception as exc:  # network failures must not abort the whole search
        return f"[抓取失败：{type(exc).__name__}]"


@tool
def tavily_search(query: str) -> str:
    """Search the web for research questions and return bounded source summaries."""
    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY is required for tavily_search.")
    max_results = min(max(int(os.getenv("TAVILY_MAX_RESULTS", "3")), 1), 3)
    topic = os.getenv("TAVILY_TOPIC", "general")
    results = TavilyClient(api_key=api_key).search(query, max_results=max_results, topic=topic).get("results", [])
    header = f"🔍 {len(results)} result(s) for: {query}"
    chunks = [header[:MAX_TOTAL_CHARS]]
    total = len(chunks[0])
    for result in results[:3]:
        title = str(result.get("title", "Untitled"))
        url = str(result.get("url", ""))
        content = fetch_webpage_content(url)
        block = f"\n\n## {title}\nURL: {url}\n\n{content}\n---"
        marker = "\n[总结果已截断：最多 10,000 个字符]"
        if total + len(block) > MAX_TOTAL_CHARS:
            remaining = max(MAX_TOTAL_CHARS - total - len(marker), 0)
            chunks.append(block[:remaining] + marker)
            break
        chunks.append(block)
        total += len(block)
    return "".join(chunks)


@tool
def think_tool(reflection: str) -> str:
    """Record a short evidence assessment and next research action."""
    bounded = reflection.strip()[:800]
    return f"Research action recorded: {bounded}"
