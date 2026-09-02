# {{ cookiecutter.project_name }}

This project is a browser-based LangChain Agent that retrieves from one
AgentBase knowledge base, renders retrieval evidence, and exports execution
traces to AppBase AgentOps.

## What AgentBase provides

AgentBase is the backend service behind the knowledge base: it stores documents,
processes and indexes them, and exposes vector, full-text, or hybrid search.
This template does not build a local vector index. The
`agentbase-python-sdk==15.5.0` client calls the AgentBase
`POST /v1/knowledgebases/{knowledgeBaseId}/search` API and maps the response to
LangChain `Document` objects. `AGENTBASE_PROJECT_ID` selects the project,
`AGENTBASE_API_KEY` authenticates the server request, and
`AGENTBASE_KNOWLEDGE_BASE_ID` selects the exact knowledge base.

AgentBase is separate from the model provider: OpenAI (or another LangChain
provider) generates the answer, while AgentBase supplies the retrieved context.
AppBase AgentOps is a third, optional plane that receives OTLP traces from the
LangChain AgentOps middleware. It does not proxy model or knowledge-base calls.

## Setup

```bash
cp .env.example .env
$EDITOR .env
agentseek task sync
agentseek task frontend
agentseek task test
agentseek task frontend-test
agentseek dev
```

The generated `.env.example` enables AgentSeek's embedded SeekDB persistence.
That database is only used by the local AgentSeek API runtime (checkpoint and
runtime state); the RAG documents remain in AgentBase. Keeping
`SEEKDB_PATH` outside the project prevents database files from triggering
development reloads. A separate local MySQL/SeekDB server is not needed.

Set `AGENTBASE_PROJECT_ID`, `AGENTBASE_API_KEY`, and
`AGENTBASE_KNOWLEDGE_BASE_ID`. The API key requires `knowledgebases.read`.
For traces it also requires `observability.ingest.write`.

`AGENTBASE_AGENTOPS_CAPTURE_CONTENT=false` is the safe default: prompts,
responses, tool arguments, and document content are not exported. Review your
data policy before enabling it.

The Retriever uses AgentBase SDK `KnowledgeBases.create_search()` in hybrid
mode. It maps every result to a LangChain `Document`; the AgentOps middleware
therefore records both the retrieval call and its parent Agent invocation. The
browser parses the `AGENTBASE_EVIDENCE_JSON` tool payload into source cards.

Open the frontend at `http://127.0.0.1:{{ cookiecutter.frontend_port }}`. Each
request includes a generated session ID and the configured environment tags;
the backend also accepts LangChain `metadata`/`tags` when called directly.
