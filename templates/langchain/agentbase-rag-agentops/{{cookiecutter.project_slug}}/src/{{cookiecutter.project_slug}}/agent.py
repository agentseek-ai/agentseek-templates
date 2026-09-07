"""LangChain graph served by ``agentseek-api dev``."""

from __future__ import annotations

import json
import os

from agentbase_agentops_langchain import AgentOpsMiddleware
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain.tools import tool

from {{ cookiecutter.project_slug }}.retriever import create_retriever

load_dotenv()


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} must be set in .env")
    return value


retriever = create_retriever(
    endpoint=_required("AGENTBASE_ENDPOINT"),
    project_id=_required("AGENTBASE_PROJECT_ID"),
    api_key=_required("AGENTBASE_API_KEY"),
    knowledge_base_id=_required("AGENTBASE_KNOWLEDGE_BASE_ID"),
    limit=int(os.getenv("AGENTBASE_RAG_LIMIT", "{{ cookiecutter.retrieval_limit }}")),
)


@tool(response_format="content_and_artifact")
def search_knowledge_base(query: str):
    """Search the configured AgentBase knowledge base for supporting context."""
    documents = retriever.invoke(query)
    evidence = [
        {
            "content": document.page_content,
            "source": document.metadata.get("source", {}),
            "locator": document.metadata.get("locator", {}),
            "score": document.metadata.get("score"),
            "chunk_id": document.metadata.get("agentbase_chunk_id"),
            "source_id": document.metadata.get("agentbase_source_id"),
            "index_source": document.metadata.get("index_source"),
        }
        for document in documents
    ]
    # The marker makes evidence available to the browser while the artifact
    # remains available to LangChain callers that preserve tool artifacts.
    content = "AGENTBASE_EVIDENCE_JSON=" + json.dumps(evidence, ensure_ascii=False)
    return content, documents


agentops = AgentOpsMiddleware()
model = init_chat_model(os.getenv("AGENTSEEK_MODEL", "{{ cookiecutter.default_model }}"))
graph = create_agent(
    model=model,
    tools=[search_knowledge_base],
    system_prompt="{{ cookiecutter.system_prompt }}",
    middleware=[agentops],
)
