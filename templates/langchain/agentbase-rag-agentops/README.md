# langchain/agentbase-rag-agentops

LangChain RAG template that searches an AgentBase knowledge base through
`agentbase-python-sdk` and exports LangChain Agent, LLM, Tool, and Retriever
traces through `agentbase-agentops-langchain`.

This template demonstrates how an AgentSeek application can consume AgentBase
as an enterprise knowledge and data service instead of building a separate
retrieval stack. The generated application keeps the LangChain graph and
conversation runtime local to AgentSeek, while AgentBase remains the managed
source for knowledge-base content and AppBase AgentOps receives the optional
execution telemetry.

## What is AgentBase?

AgentBase is an enterprise, full-stack application platform that is also
evolving into infrastructure for production Agents. It brings application
backend services, an OceanBase-backed data layer, knowledge and memory
services, model access, and operational governance into one project boundary.
The goal is to help an Agent or coding assistant move from a working demo to a
deployable application without assembling a separate product for every part
of the backend.

The platform is organized around five service entry points:

| Service | What it provides for an Agent application |
| --- | --- |
| RAG | Multi-source knowledge ingestion, cleaning and chunking, permission-aware retrieval, and retrieval/answer evaluation. |
| Memory | Structured extraction, long-term recall, team experience sharing, cross-application memory, and controlled forgetting. |
| Data API | Identity-scoped access to existing enterprise data through REST or SQL Proxy, with audit, limits, and usage tracking. |
| BaaS | Auth, TablesDB, Storage, Functions, Sites, Realtime, and model entry points for newly built applications. |
| AgentOps | Session, trace, and user-level run records, quality evaluation, bad-case analysis, and comparisons between prompts or model parameters. |

These services can be used independently or composed into one application.
For example, this template combines RAG retrieval with AgentOps tracing, while
an application built on top of the same project could additionally use Memory
for long-term user context or Data API for controlled access to business
systems.

### AgentBase platform value

- **A complete capability system:** Auth, data, storage, functions, sites,
  realtime features, model entry points, RAG, Memory, Data API, and AgentOps
  share one project boundary.
- **Independent scaling:** API, Console, Worker, Executor, and Realtime
  components can scale around their individual pressure points instead of
  requiring the whole application to scale as one machine.
- **An evolvable data foundation:** OceanBase and TablesDB support both
  dedicated tables for high-throughput, large-table workloads and shared-table
  layouts for projects with many logical schemas and frequent schema changes.
  Schema-versioning capabilities make data-model changes easier to validate,
  switch, and roll back.
- **A complete delivery path:** Functions, Sites, and sandbox execution cover
  backend logic, frontend deployment, and runtime execution in the same
  application lifecycle.
- **Production governance:** Permissions, organization/project boundaries,
  resource limits, usage accounting, and auditability provide the controls
  needed for enterprise delivery.

### The AgentBase services in more detail

**RAG — knowledge access with permission boundaries.** AgentBase can ingest
documents, web pages, and enterprise data, then apply source-specific parsing
and chunking. Retrieval can combine vector, full-text, and hybrid search while
respecting the caller's access scope. Evaluation closes the loop by measuring
answer accuracy and relevance so that teams can improve the knowledge source,
retrieval settings, and prompts together.

**Memory — useful long-term context.** Memory is more than a transcript
database. It extracts durable facts, user preferences, business context, and
validated experience from interactions; recalls them when relevant; and
supports transparency, control, and forgetting. Team memories can preserve
successful solutions and troubleshooting knowledge, with controlled reuse
across applications in the same organization.

**Data API — open existing data without copying it.** Agents can access an
enterprise's existing data through identity- and scope-aware REST or SQL Proxy
interfaces. SQL Proxy authenticates the caller, parses and rewrites SQL, and
executes it against the logical TablesDB layer with security and audit checks.
This allows data to remain in place while access is still governed, rate
limited, metered, and reviewable.

**BaaS — the application backend.** New Agent-generated applications can use
the same project for authentication, TablesDB data, file storage, server-side
functions, realtime updates, sites, and model entry points. This reduces the
amount of backend convention that an Agent must invent and gives generated
frontends and functions a stable contract to build against.

**AgentOps — an improvement loop, not only monitoring.** AgentOps records the
relationship between sessions, users, Agent runs, model calls, tool calls, and
retrieval calls. Teams can inspect bad cases, score semantic alignment and
logical correctness, compare prompt/model variants, and turn production runs
into evaluation data for the next iteration. This is the path from observing
an Agent to continuously improving and safely releasing it.

### AgentBase access points

Use the following addresses for the SIT deployment used by this template:

- **AgentBase Console:** <https://appbuild-sit.oceanbase.com/console>
- **AgentBase API base:** <https://appbuild-sit.oceanbase.com/v1>

The Console URL is for browser-based project and knowledge-base management.
The API base is for SDK and AgentOps requests and must include `/v1`; they are
not interchangeable. Authentication for the Console is provided by the
browser session, while backend SDK calls use the project credentials from the
environment.

The generated project uses a small `BaseRetriever` adapter rather than direct
HTTP calls. It maps `KnowledgeBases.create_search()` results to LangChain
`Document` objects, preserving the source, score, locator, and AgentBase chunk
ID in metadata. The knowledge-base ID is deliberately configured once in the
template/environment for this first version.

## AgentBase and endpoint configuration

For this template, AgentBase is used specifically as the remote knowledge-base
and AgentOps service. It stores documents, chunks, and indexes, then provides
vector, full-text, and hybrid retrieval. AgentSeek runs the LangChain graph
locally; the configured model provider generates the answer; AgentOps receives
execution telemetry. AgentBase is not the model provider, and it is not
replaced by the local embedded SeekDB database.

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

The API key belongs to an AgentBase/AppBase Project and should be scoped to the
knowledge base and observability operations required by the application. This
template needs `knowledgebases.read` to search the knowledge base and
`observability.ingest.write` to export AgentOps traces. Add
`observability.traces.read` only if the application also queries trace data.

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
