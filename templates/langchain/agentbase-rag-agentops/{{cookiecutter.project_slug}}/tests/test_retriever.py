import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest
from agentbase.client import Client
from agentbase.exception import AgentbaseException
from agentbase.services.knowledge_bases import KnowledgeBases

from {{ cookiecutter.project_slug }}.retriever import (
    AgentbaseKnowledgeBaseRetriever,
    create_retriever,
)


class FakeKnowledgeBases:
    def create_search(self, knowledge_base_id, query, **kwargs):
        assert knowledge_base_id == "kb-demo"
        assert query == "where is the guide?"
        assert kwargs == {"limit": 2, "search_mode": "hybrid"}
        result = SimpleNamespace(
            id="chunk-1",
            content="The guide is in the docs folder.",
            sourceid="doc-1",
            source={"name": "guide.md"},
            locator={"page": 3},
            metadata={"topic": "setup"},
            score=0.91,
            indexsource="rag",
            resulttype="chunk",
            resultgeneration=None,
        )
        return SimpleNamespace(results=[result])


def test_retriever_maps_sdk_result_to_document():
    retriever = AgentbaseKnowledgeBaseRetriever(
        knowledge_bases=FakeKnowledgeBases(), knowledge_base_id="kb-demo", limit=2
    )

    documents = retriever.invoke("where is the guide?")

    assert documents[0].page_content == "The guide is in the docs folder."
    assert documents[0].metadata == {
        "topic": "setup",
        "agentbase_chunk_id": "chunk-1",
        "agentbase_source_id": "doc-1",
        "source": {"name": "guide.md"},
        "locator": {"page": 3},
        "score": 0.91,
        "index_source": "rag",
        "result_type": "chunk",
        "result_generation": None,
    }


def test_retriever_sets_project_header_required_by_sdk_service():
    retriever = create_retriever(
        endpoint="https://appbuild-sit.oceanbase.com/v1",
        project_id="project-demo",
        api_key="secret",
        knowledge_base_id="kb-demo",
        limit=4,
    )

    assert retriever.knowledge_bases.client.get_headers()["x-appwrite-project"] == "project-demo"


def test_sdk_boundary_sends_expected_search_request_to_local_http_stub():
    """Exercise the pinned SDK without contacting a real AgentBase deployment."""

    requests: list[dict[str, object]] = []

    class SearchHandler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 - required by BaseHTTPRequestHandler
            body = self.rfile.read(int(self.headers["Content-Length"]))
            requests.append(
                {
                    "path": self.path,
                    "project": self.headers.get("X-Appwrite-Project"),
                    "key": self.headers.get("X-Appwrite-Key"),
                    "body": json.loads(body),
                }
            )
            payload = {
                "total": 1,
                "results": [
                    {
                        "$id": "chunk-1",
                        "content": "The guide is in the docs folder.",
                        "sourceId": "doc-1",
                        "source": {"name": "guide.md"},
                        "locator": {"page": 3},
                        "metadata": {"topic": "setup"},
                        "imageContexts": [],
                        "score": 0.91,
                        "indexSource": "rag",
                        "resultType": "chunk",
                        "resultGeneration": None,
                    }
                ],
                "reranked": False,
                "capabilities": {},
                "degradedCapabilities": [],
            }
            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), SearchHandler)
    try:
        server_thread = __import__("threading").Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        client = (
            Client()
            .set_endpoint(f"http://127.0.0.1:{server.server_port}/v1")
            .set_project("project-demo")
            .set_key("secret")
            .add_header("X-Appwrite-Project", "project-demo")
        )

        response = KnowledgeBases(client).create_search(
            "kb-demo", "where is the guide?", limit=2, search_mode="hybrid"
        )

        assert response.results[0].score == 0.91
        assert requests == [
            {
                "path": "/v1/knowledgebases/kb-demo/search",
                "project": "project-demo",
                "key": "secret",
                "body": {"query": "where is the guide?", "limit": 2, "searchMode": "hybrid"},
            }
        ]
    finally:
        server.shutdown()
        server.server_close()


def test_retriever_returns_empty_list_for_empty_sdk_response():
    class EmptyKnowledgeBases:
        def create_search(self, *_args, **_kwargs):
            return SimpleNamespace(results=[])

    retriever = AgentbaseKnowledgeBaseRetriever(
        knowledge_bases=EmptyKnowledgeBases(), knowledge_base_id="kb-demo", limit=2
    )

    assert retriever.invoke("no matches") == []


def test_retriever_propagates_agentbase_errors():
    class FailingKnowledgeBases:
        def create_search(self, *_args, **_kwargs):
            raise AgentbaseException("Knowledge base not found", 404, "not_found")

    retriever = AgentbaseKnowledgeBaseRetriever(
        knowledge_bases=FailingKnowledgeBases(), knowledge_base_id="missing", limit=2
    )

    with pytest.raises(AgentbaseException, match="Knowledge base not found"):
        retriever.invoke("anything")
