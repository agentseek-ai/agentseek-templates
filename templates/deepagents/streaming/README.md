# DeepAgents — streaming template

Scaffolds a DeepAgents Event Streaming v3 showcase. It uses a coordinator and
one `researcher` sub-agent, then presents the official event-streaming
projections in a browser UI:

- sub-agent lifecycle and nested paths;
- coordinator and sub-agent messages;
- tool execution lifecycle, inputs, output deltas, final output, and errors;
- state snapshots and final output;
- a raw protocol/debug view with sequence, method, namespace, and payload.

The backend uses the documented `graph.astream_events(input, version="v3")`
API and converts typed projections into a small application event protocol.
The React UI only consumes that application protocol, so protocol details stay
out of components.

## Feature tour

The demo is an event-streaming observability surface rather than a single
answer box. Each request produces a timeline that makes the execution tree and
the final result visible:

| Projection | What it represents | What the UI shows |
| --- | --- | --- |
| `messages` | Coordinator and sub-agent text | Source, text, and path |
| `subagents` | Delegated agent lifecycle | Name, path, phase, and status |
| `tool_calls` | Tool execution | Input, output deltas, result, and errors |
| `values` | State snapshots during the run | Expandable state/debug payload |
| `output` | Final run state/result | Expandable final output |
| raw protocol | Ordered transport events | Sequence, method, namespace, and data |

The coordinator is instructed to delegate to `researcher`, and the researcher
uses the local `inspect_streaming_topic` tool. This makes delegation and tool
events observable without requiring a search provider. The UI also keeps a
stable `thread_id`, updates projection counters as events arrive, and renders
provider or stream failures as structured error cards.
The custom route keeps thread history in memory for the current backend
process; restarting `langgraph dev` starts a new session.

The backend consumes the official v3 projections concurrently through the
LangGraph development server. The raw stream
preserves the protocol envelope (`seq`, `method`, `params.namespace`, and
`params.data`) while the adapter converts typed projections into a small,
frontend-safe event protocol. This first version intentionally keeps the
runtime on `langgraph dev` so the v3 projection behavior can be exercised
without depending on AgentSeek API projection support. AgentSeek API migration
can be added after the projection contract is stable.

## Quickstart

```bash
cp .env.example .env
cp frontend/.env.example frontend/.env
$EDITOR .env

uv sync
npm install --prefix frontend
uv run langgraph dev --port 2024 --no-browser
# In another terminal:
npm run dev --prefix frontend
```

Open `http://127.0.0.1:{{ cookiecutter.frontend_port }}` and try:

```text
Explain how Event Streaming v3 separates coordinator messages, sub-agent work, and tool calls.
```

The demo prompt asks the coordinator to delegate to `researcher`, which makes
the lifecycle visible without relying on an accidental model decision.

## Environment

`AGENTSEEK_MODEL_PROVIDER` selects `openai`, `anthropic`, or `google_genai`.
`AGENTSEEK_MODEL` selects the model. Fill the matching provider credential in
`.env`; a blank provider base URL uses that provider's official endpoint.

The template defaults to `openai` and `gpt-4.1-mini`. OpenAI-compatible gateways
can be used with `OPENAI_API_BASE` and a model served by that gateway.

## What the UI demonstrates

The backend follows the official Deep Agents event-streaming projections:

```text
stream.subagents  -> delegation cards and lifecycle
stream.messages   -> coordinator/sub-agent message rows
stream.tool_calls -> tool input, deltas, completion, and errors
stream.values     -> state snapshot panel
stream.output     -> final run output
for event in stream -> raw protocol debug panel
```

`name` is a display label. `path` is used as the stable branch key. The UI does
not treat `completed` as success for tools until `error` is also checked.

## Version boundary

The generated project pins `deepagents==0.6.12`, the first DeepAgents release
used by the sibling MCP template for the v3-era runtime surface. Do not copy
the raw event adapter into unrelated components; if the protocol changes,
update the adapter and its tests first.

## Lifecycle

The generated project declares lifecycle version 2 in `.agentseek/lifecycle.toml`.
The backend is served by `langgraph dev`, and the frontend uses Vite.

## References

- [Deep Agents Event Streaming](https://docs.langchain.com/oss/python/deepagents/event-streaming)
- [LangChain Event Streaming](https://docs.langchain.com/oss/python/langchain/event-streaming)
- [LangGraph Event Streaming](https://docs.langchain.com/oss/python/langgraph/event-streaming)
- [PR #99](https://github.com/datawhalechina/deepagents-in-action/pull/99)
