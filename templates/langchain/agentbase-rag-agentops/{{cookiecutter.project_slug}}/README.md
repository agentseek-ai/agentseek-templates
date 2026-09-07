# {{ cookiecutter.project_name }}

This project is a browser-based LangChain Agent that retrieves from one
AgentBase knowledge base, renders retrieval evidence, and exports execution
traces to AppBase AgentOps.

## AgentBase at a glance

AgentBase is an enterprise application backend and Agent infrastructure
platform. It provides a shared project boundary for knowledge retrieval,
long-term memory, controlled access to enterprise data, application backend
services, and AgentOps. This example uses two of those capabilities together:

- **RAG** supplies permission-aware context from documents, web pages, or
  enterprise knowledge sources through vector, full-text, or hybrid search;
- **AgentOps** records the relationship between sessions, Agent runs, model
  calls, tool calls, and retrieval calls so teams can inspect bad cases and
  evaluate changes over time.

The same AgentBase project can later add Memory for durable user preferences
and team experience, or Data API for identity-scoped access to existing
business data without copying it into the local application. AgentBase also
offers BaaS capabilities such as Auth, TablesDB, Storage, Functions, Sites,
and Realtime for applications that need a complete backend.

For the SIT deployment used by this template:

- **Console:** <https://appbuild-sit.oceanbase.com/console> — manage the
  project and knowledge base in a browser;
- **API base:** <https://appbuild-sit.oceanbase.com/v1> — used by the backend
  SDK and AgentOps integration; keep the `/v1` suffix.

The Console address and API base are different entry points. AgentBase
credentials stay in the backend environment, while the local embedded SeekDB
instance stores AgentSeek runtime state and does not replace the AgentBase
knowledge base.

## AgentBase basics

AgentBase is the remote knowledge-base service for this application. It stores
documents, chunks and indexes, and exposes vector, full-text, or hybrid search.
This template does not create a local vector index: the pinned
`agentbase-python-sdk==15.5.0` calls
`POST /v1/knowledgebases/{knowledgeBaseId}/search`, and the local LangChain
retriever maps each result to a `Document` with source, locator, score, and
chunk metadata.

The components have separate responsibilities:

- AgentBase supplies retrieved context;
- OpenAI or another LangChain provider generates the answer;
- AgentSeek hosts the local graph and embedded runtime state;
- AppBase AgentOps receives OTLP traces from `AgentOpsMiddleware`.

AgentBase does not proxy model requests, and embedded SeekDB does not contain
your AgentBase documents.

## AgentBase API and credentials

Copy `.env.example` to `.env` and set these values:

```dotenv
AGENTBASE_ENDPOINT=https://appbuild-sit.oceanbase.com/v1
AGENTBASE_PROJECT_ID=<project-id>
AGENTBASE_API_KEY=<project-api-key>
AGENTBASE_KNOWLEDGE_BASE_ID=<knowledge-base-id>
```

`AGENTBASE_ENDPOINT` is the SDK API base URL and must include `/v1`. Create the
Project API Key in the AgentBase/AppBase Console for the same Project as the
knowledge base. Grant only the permissions needed:

- `knowledgebases.read` — required for retrieval;
- `observability.ingest.write` — required to export AgentOps traces;
- `observability.traces.read` — optional, only for querying traces.

`AGENTBASE_AGENTOPS_ENDPOINT` is the OTLP trace destination and is separate
from the browser Console URL. The lifecycle Console shortcut defaults to
`https://appbuild-sit.oceanbase.com/console`; it is controlled by the
`agentbase_console_url` template variable and is not used for SDK requests.

Never commit `AGENTBASE_API_KEY`, put it in a URL, or expose it through a
`VITE_*` variable. AgentBase requests and credentials stay on the backend.

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

If retrieval returns 401/403, verify that the Project ID and API key belong to
the same Project and that the key has `knowledgebases.read`. A 404 usually
means the knowledge-base ID is not exact or belongs to another Project. Keep
`/v1` on `AGENTBASE_ENDPOINT`; use the Console URL only for the browser link.

`AGENTBASE_AGENTOPS_CAPTURE_CONTENT=false` is the safe default: prompts,
responses, tool arguments, and document content are not exported. Review your
data policy before enabling it.

The Retriever uses AgentBase SDK `KnowledgeBases.create_search()` in hybrid
mode. It maps every result to a LangChain `Document`; the AgentOps middleware
therefore records both the retrieval call and its parent Agent invocation. The
browser parses the `AGENTBASE_EVIDENCE_JSON` tool payload into source cards.

## Threads and checkpoint persistence

Following the `deepagents/subagents-dynamic` pattern, the graph does not create
an `InMemorySaver` or another process-local checkpointer. The `agentseek-api`
runtime owns checkpoint persistence and uses the embedded SeekDB configuration
above. The frontend keeps the server-issued LangGraph `thread_id` in a
controlled `useStream` state, so consecutive messages in one open page share
the same checkpoint. A page reload starts a new thread; connect a durable
thread ID to your authenticated conversation record when cross-reload resume
is required.

Open the frontend at `http://127.0.0.1:{{ cookiecutter.frontend_port }}`. Each
request includes a generated session ID and the configured environment tags;
the backend also accepts LangChain `metadata`/`tags` when called directly.

AgentSeek desktop exposes both browser actions from the lifecycle: **Open RAG
application** opens the local chat UI, and **Open AgentBase** opens
`{{ cookiecutter.agentbase_console_url }}`. The Console URL is a public link;
authentication is handled by your browser session and no API key is placed in
the lifecycle or URL.
