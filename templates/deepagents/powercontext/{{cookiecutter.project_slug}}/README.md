# {{ cookiecutter.project_name | replace("DeepAgents", "Deep Agents") }}

Save a release decision, open a new conversation, and watch a Deep Agents coordinator and
researcher use it through PowerContext. Turn recall off to compare a fresh run without that evidence.

PowerContext is an open-source context layer for AI agents. This example demonstrates durable project
Memory and bounded recall before each asynchronous Deep Agents model call. The release scenario is
illustrative; it is not a benchmark or a customer case study.

## Run locally

The generated app uses Python 3.12+, Node.js 22.12+ (or a Vite-compatible newer release), and uv.
Install and start the matching PowerContext Server in its own terminal:

```bash
uv tool install "powercontext[cli,server] @ git+https://github.com/oceanbase/powercontext.git@04b780cd51b603736a83d4ce6bc43d27eb6e01a4"
powercontext server run
```

The default local Server uses persistent SQLite. Explicit Memory writes and full-text recall need
no generation or embedding model. Keep the Server running at `http://127.0.0.1:8000`.

In the generated project:

```bash
cp .env.example .env
cp frontend/.env.example frontend/.env
# Edit .env: set the selected agent provider's API key and model.
uv sync
npm install --prefix frontend
uv run langgraph dev --port {{ cookiecutter.langgraph_port }} --no-browser
```

Start the frontend in another terminal:

```bash
npm run dev --prefix frontend
```

Open `http://127.0.0.1:{{ cookiecutter.frontend_port }}`. The same setup is available through
`agentseek task sync`, `agentseek task frontend`, and `agentseek dev`.

## Five-minute demonstration

1. Click **Create project memory**. The Server allocates an opaque Scope ID and stores a stable
   project binding. Repeating this action resolves the same project; reading or recalling never
   creates a Scope. An explicitly configured Scope ID must already exist.
2. Review the prefilled **Project Phoenix** decision and click **Save decision**. You should see
   the saved text and its immutable entry citation. A failed write is reported as unconfirmed.
3. Click **New conversation**, then **Try release question** and **Send**. The question mentions
   Project Phoenix without repeating its decisions. Expand **Context supplied to this model call**
   to inspect the actual historical text sent to the model and the UTF-8 byte count.
4. Turn **Recall project memory** off and ask the same question. Changing the switch creates a new
   thread so a previous answer cannot supply the supposedly withheld facts. The disabled run should
   report unknown project decisions; it still has the generic release checklist. Model wording varies.
5. Turn recall back on, or restart the application and refresh Memory. The same project decisions
   remain available from the Server. Try the 512-byte budget as well: a smaller budget may omit
   entries or yield `empty`. The server keeps the whole Memory entry; it does not truncate durable data.

The default full-text search needs matching terms such as `Project Phoenix` and `release`. Semantic
paraphrase retrieval requires PowerContext vector configuration. Current instructions override historical
notes, so you can also try: “For this exercise, plan Project Phoenix for Friday instead of Tuesday.”

## What the page proves

| Observation | Capability |
| --- | --- |
| A new thread recalls a saved project decision | Memory is separate from chat history |
| Reopening the app resolves the same Scope | Server-owned durable project binding |
| Context expands to show its actual text and byte count | Inspectable, bounded per-call recall |
| Turning recall off creates a clean comparison thread | A run can proceed without historical context |
| Stopping PowerContext produces `unavailable`, then the agent continues | Recall has a three-second operation deadline and fails open |
| Saving shows an entry citation and version | Durable writes return inspectable evidence |

`empty` means no matching content fit the request; `unavailable` means recall failed. Neither means
that the agent has recovered missing facts. Prepared context is untrusted historical evidence, carried
in a retrieval ToolMessage for this model call only. It is not added to persisted conversation state.
The UI displays the actual prepared text, which can include project information; use it within the
same trusted local development boundary as the project.

Only clicking **Save decision** writes Memory. There is no automatic transcript capture or model-driven
write tool. Correct or retire old decisions through PowerContext's own interfaces. Handoff, Work Contract,
Experience review, and Task Outcome are separate PowerContext workflows, not features of this template.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `POWERCONTEXT_URL` | `http://127.0.0.1:8000` | Matching PowerContext Server |
| `POWERCONTEXT_PROJECT_KEY` | `{{ cookiecutter.project_slug }}` | Stable binding identity; use distinct values for independent projects |
| `POWERCONTEXT_SCOPE_ID` | empty | Optional existing Server-owned Scope ID, overriding the binding |
| `POWERCONTEXT_TOKEN` | empty | Bare bearer token, read only by the backend |
| `POWERCONTEXT_MAX_BYTES` | `8000` | Server request budget, 512–32768 UTF-8 bytes; the UI can lower it |
| `AGENTSEEK_MODEL_PROVIDER` | `{{ cookiecutter.default_model_provider }}` | `openai`, `anthropic`, or `google_genai` |
| `AGENTSEEK_MODEL` | `{{ cookiecutter.default_model }}` | Agent model identifier |

Use `OPENAI_API_BASE` for an OpenAI-compatible gateway. The browser never supplies a PowerContext
URL, token, or Scope ID. A project key is a data boundary, not an authentication mechanism. This is
a local development template; shared deployment needs application authentication and authorization
in front of both stream and Memory routes.

The client is pinned to PowerContext commit `04b780cd51b603736a83d4ce6bc43d27eb6e01a4`, matching the
Scope/Memory API used here. The earlier `0.1.0` package does not expose the Scope binding API.

## Runtime and verification

The custom route uses Deep Agents `0.6.12`, `langgraph dev`, and the documented v3 projections.
The researcher calls `release_checklist`, a deterministic local checklist that contains no saved
Phoenix decisions. Both agents have recall middleware. Protocol and state details remain available
behind **Show protocol and state details**.

Conversation history uses an in-process checkpointer and is lost on backend restart. Project Memory
persists in the separate PowerContext Server's configured database. Restarting with a different or
empty database cannot recover previous Memory.

Direct callers of `POST /custom/stream` must supply a nonblank `thread_id`. Reuse it for follow-up
messages and choose a new ID for a fresh conversation. The browser manages these IDs automatically;
missing, null, empty, or whitespace-only IDs return HTTP 422 before a run starts.

```bash
uv sync --extra dev
uv run pytest
npm test --prefix frontend
npm run build --prefix frontend
# Optional real Server tests; creates isolated test Scopes in this Server:
POWERCONTEXT_TEST_URL=http://127.0.0.1:8000 uv run pytest tests/test_project_memory_live.py
```

See [PowerContext](https://github.com/oceanbase/powercontext) and
[Deep Agents event streaming](https://docs.langchain.com/oss/python/deepagents/event-streaming).
