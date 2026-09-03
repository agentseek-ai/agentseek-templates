# langchain/agentbase-rag-agentops

LangChain RAG template that searches an AgentBase knowledge base through
`agentbase-python-sdk` and exports LangChain Agent, LLM, Tool, and Retriever
traces through `agentbase-agentops-langchain`.

The generated project uses a small `BaseRetriever` adapter rather than direct
HTTP calls. It maps `KnowledgeBases.create_search()` results to LangChain
`Document` objects, preserving the source, score, locator, and AgentBase chunk
ID in metadata. The knowledge-base ID is deliberately configured once in the
template/environment for this first version.

## AgentBase and endpoint configuration

AgentBase is the remote knowledge-base service used by this template. It stores
documents, chunks and indexes, then provides vector, full-text and hybrid
retrieval. AgentSeek runs the LangChain graph locally; the model provider
generates the answer; AgentOps receives observability traces. AgentBase is not
the model provider and is not replaced by the local embedded SeekDB database.

The SDK endpoint is the API base URL and must include `/v1`:

```dotenv
AGENTBASE_ENDPOINT=https://appbuild-sit.oceanbase.com/v1
AGENTBASE_PROJECT_ID=<project-id>
AGENTBASE_API_KEY=<project-api-key>
AGENTBASE_KNOWLEDGE_BASE_ID=<knowledge-base-id>
```

Create the Project API Key in the target AgentBase/AppBase Project. Grant the
minimum permissions needed:

- `knowledgebases.read` for RAG retrieval;
- `observability.ingest.write` for AgentOps trace export;
- `observability.traces.read` only when the application queries traces.

`AGENTBASE_AGENTOPS_ENDPOINT` is the separate OTLP trace destination and also
uses the `/v1` API base URL. It is not the browser Console URL. The generated
lifecycle's `agentbase_console_url` controls the desktop **Open AgentBase**
link and defaults to `https://appbuild-sit.oceanbase.com/console`.

Keep the API key in `.env` or a secret manager. Do not commit it, put it in a
URL, or expose it through `VITE_*` variables; all AgentBase SDK calls run on
the backend.

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

If retrieval returns 401/403, check that the Project ID and API key belong to
the same Project and that the key has `knowledgebases.read`. A 404 for the
knowledge base usually means `AGENTBASE_KNOWLEDGE_BASE_ID` is not the exact ID
from that Project. Keep `/v1` on `AGENTBASE_ENDPOINT`; use the Console URL only
for the desktop browser link.

Do not enable NeMo Relay for the same agent: this template uses
`AgentOpsMiddleware`, and enabling both creates duplicate traces.

The generated lifecycle exposes two browser actions in AgentSeek desktop:
`Open RAG application` opens the local chat UI, while `Open AgentBase` opens
the configured AgentBase Console URL. Override `agentbase_console_url` when
creating the template if your deployment uses a different Console address.
