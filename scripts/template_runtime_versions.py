"""Reviewed API release for each API-based template; not a template registry.

Update a template's dependency pin and its entry together after validating the
generated runtime. Tests and CI share this policy so upgrades can be staged.
"""

AGENTSEEK_API_VERSIONS = {
    "deepagents/content-builder": "0.2.3",
    "deepagents/mcp": "0.2.3",
    "deepagents/powercontext": "0.3.2",
    "deepagents/research": "0.2.3",
    "langchain/agentbase-rag-agentops": "0.2.3",
    "langchain/agentic-rag": "0.2.3",
    "langchain/agentic-rag-hybrid": "0.2.3",
    "langchain/cli-remote": "0.2.3",
    "langchain/markdown-messages": "0.2.3",
    "langchain/rubric": "0.2.3",
}
