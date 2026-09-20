# Deep Agents — PowerContext

A project release assistant that makes cross-conversation Memory visible. Save a project decision,
open a new conversation, and inspect the bounded context supplied to the coordinator and researcher.
Turn recall off to compare a fresh run without the saved evidence.

The template includes:

- Explicit Memory writes, saved entry citations, and a persistent Server-owned project Scope binding.
- A **New conversation** control that clears conversation context while retaining project Memory.
- A recall switch and UTF-8 byte budget; changing either starts a fresh comparison thread.
- Actual prepared-context text in the execution timeline, plus separate empty, disabled, and unavailable states.
- A three-second recall deadline, fail-open model execution, and request-local context injection.
- A bilingual (English / Simplified Chinese) interface with a header language button that switches
  every label and remembers the reader's choice.
- A focused answer view: the browser shows only the recalled PowerContext evidence and the agents'
  final answer, while the route consumes and discards the v3 protocol projections.

## Try it

Render `deepagents/powercontext`, then follow the generated README: `agentseek dev` starts the
PowerContext Server together with the API and the frontend. Configure the agent model, click
**Create project memory**, review and save the example Project Phoenix release decision, then ask:

```text
What is the release plan for Project Phoenix?
```

Repeat the question after **New conversation** and with recall disabled. The saved Singapore/Tuesday/
approval/rollback facts are not embedded in the agent prompt or checklist tool; they come from the
explicitly saved Memory. The scenario is an illustrative demonstration, not a benchmark claim.

## Configuration and boundaries

`powercontext_url` defaults to `http://127.0.0.1:8000`, `powercontext_max_bytes` to `8000`, and
`powercontext_scope` to empty. An optional Scope value must be a real Server-owned ID. Otherwise,
**Create project memory** creates a Scope and binds `POWERCONTEXT_PROJECT_KEY` (the project slug
by default) through the public Scope API. Use distinct project keys for independent projects.

The generated SDK and Server use PowerContext **1.0.0**, the latest stable PyPI release verified on
2026-09-19. It includes the required Scope binding API, replacing the Git commit dependency.
The generated `.env` selects embedded seekdb for PowerContext Memory, with a data directory separate
from AgentSeek API checkpoints. The Server runs as a managed lifecycle process: `agentseek dev` starts
it with the API and the frontend, reuses one that is already ready at `powercontext_url`, and stops it
with the rest of the project. Set `POWERCONTEXT_AUTOSTART=false` to keep the Server fully external.
The generated README includes provider settings and live verification commands.

Only explicit user saves write Memory. Automatic transcript capture, Handoff, Work Contract,
Experience review, and Task Outcome are outside this template. Historical context is untrusted and
never enters the saved chat history. PowerContext holds project Memory in its own database; the
custom route's conversation history lasts only for the current backend process.

The template is a local development app. Backend configuration owns the Server URL, bearer token,
and Scope selection. Shared deployment needs application authentication and authorization. The UI
shows project Memory and the context supplied to the model, so it belongs within that same access boundary.

The subtree is self-contained and declares lifecycle version 2. It retains Deep Agents `0.6.12` and
serves the graph through the AgentSeek API runtime. PowerContext project Memory and API checkpoints
each use their own embedded seekdb database. OpenAI-compatible streamed tool calls retain their names
when a gateway sends empty continuation fields. See the generated README for the full tour.

- [PowerContext](https://github.com/oceanbase/powercontext)
- [Deep Agents Event Streaming](https://docs.langchain.com/oss/python/deepagents/event-streaming)
