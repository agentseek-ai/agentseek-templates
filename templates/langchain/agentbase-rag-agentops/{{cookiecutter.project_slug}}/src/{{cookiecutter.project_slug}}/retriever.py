"""LangChain adapter for the AgentBase knowledge-base search API."""

from __future__ import annotations

from typing import Any

from agentbase.client import Client
from agentbase.services.knowledge_bases import KnowledgeBases
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict


class AgentbaseKnowledgeBaseRetriever(BaseRetriever):
    """Retrieve AgentBase search results as LangChain documents."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    knowledge_bases: Any
    knowledge_base_id: str
    limit: int = 4
    search_mode: str = "hybrid"

    def _get_relevant_documents(self, query: str, *, run_manager: Any) -> list[Document]:
        response = self.knowledge_bases.create_search(
            self.knowledge_base_id,
            query,
            limit=self.limit,
            search_mode=self.search_mode,
        )
        return [self._to_document(result) for result in response.results]

    @staticmethod
    def _to_document(result: Any) -> Document:
        source = _as_mapping(getattr(result, "source", {}))
        locator = _as_mapping(getattr(result, "locator", {}))
        metadata = dict(_as_mapping(getattr(result, "metadata", {})))
        metadata.update(
            {
                "agentbase_chunk_id": getattr(result, "id", None),
                "agentbase_source_id": getattr(result, "sourceid", None),
                "source": source,
                "locator": locator,
                "score": getattr(result, "score", None),
                "index_source": getattr(result, "indexsource", None),
                "result_type": getattr(result, "resulttype", None),
                "result_generation": getattr(result, "resultgeneration", None),
            }
        )
        return Document(page_content=result.content, metadata=metadata)


def create_retriever(*, endpoint: str, project_id: str, api_key: str, knowledge_base_id: str, limit: int) -> AgentbaseKnowledgeBaseRetriever:
    """Build the SDK client once and expose the configured knowledge base."""
    client = (
        Client()
        .set_endpoint(endpoint)
        .set_project(project_id)
        .set_key(api_key)
        # KnowledgeBases reads this header through Client.get_config("project").
        # SDK 15.5.0's set_project() does not populate that header itself.
        .add_header("X-Appwrite-Project", project_id)
    )
    return AgentbaseKnowledgeBaseRetriever(
        knowledge_bases=KnowledgeBases(client),
        knowledge_base_id=knowledge_base_id,
        limit=limit,
    )


def _as_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(by_alias=True)
    return {"value": value}
