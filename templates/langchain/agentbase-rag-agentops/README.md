# langchain/agentbase-rag-agentops

LangChain RAG template that searches an AgentBase knowledge base through
`agentbase-python-sdk` and exports LangChain Agent, LLM, Tool, and Retriever
traces through `agentbase-agentops-langchain`.

The generated project uses a small `BaseRetriever` adapter rather than direct
HTTP calls. It maps `KnowledgeBases.create_search()` results to LangChain
`Document` objects, preserving the source, score, locator, and AgentBase chunk
ID in metadata. The knowledge-base ID is deliberately configured once in the
template/environment for this first version.

## Quick start

```bash
agentseek create langchain/agentbase-rag-agentops
cd <project_slug>
cp .env.example .env
# Set the AppBase project, API key, and knowledge base ID.
agentseek task sync
agentseek dev
```

The API key needs `knowledgebases.read` for retrieval and
`observability.ingest.write` for AgentOps export. Add
`observability.traces.read` only if the application also queries traces.

Do not enable NeMo Relay for the same agent: this template uses
`AgentOpsMiddleware`, and enabling both creates duplicate traces.

The generated lifecycle exposes two browser actions in AgentSeek desktop:
`Open RAG application` opens the local chat UI, while `Open AgentBase` opens
the configured AgentBase Console URL. Override `agentbase_console_url` when
creating the template if your deployment uses a different Console address.
