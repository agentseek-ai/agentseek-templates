# {{ cookiecutter.project_name }}

This project demonstrates Deep Agents Event Streaming v3 with a coordinator,
the `researcher` sub-agent, tool execution, state snapshots, final output, and
raw protocol events.

## Run locally

```bash
cp .env.example .env
cp frontend/.env.example frontend/.env
uv sync
npm install --prefix frontend
```

Start the backend in terminal one:

```bash
uv run langgraph dev --port {{ cookiecutter.langgraph_port }} --no-browser
```

Start the browser UI in terminal two:

```bash
npm run dev --prefix frontend
```

Open `http://127.0.0.1:{{ cookiecutter.frontend_port }}` and try:

```text
Explain how Event Streaming v3 separates coordinator messages, sub-agent work, and tool calls.
```

The backend uses `await graph.astream_events(input, version="v3")` and exposes
the documented `subagents`, `messages`, `tool_calls`, `values`, `output`, and
raw protocol projections through the browser timeline.

## What you can observe

This is an execution timeline, so the UI exposes more than the final answer:

| Projection | Meaning | UI presentation |
| --- | --- | --- |
| `messages` | Coordinator and sub-agent text | Message cards with source/path |
| `subagents` | Delegation and completion lifecycle | Name, path, status, and phase |
| `tool_calls` | Tool input and execution output | Expandable input, deltas, result, or error |
| `values` | Intermediate graph state | Expandable state snapshot |
| `output` | Final run state/result | Expanded final output card |
| raw events | Ordered v3 protocol envelope | Sequence, method, namespace, and data |

The coordinator always delegates to the `researcher` sub-agent. The researcher
calls the local `inspect_streaming_topic` tool, so a normal request visibly
demonstrates coordinator messages, sub-agent messages, tool lifecycle events,
state snapshots, raw protocol events, and final output. The projection counter
strip updates while the stream is active, and stream failures appear as
structured error cards instead of silently ending the request.

The browser keeps a stable `thread_id` for follow-up requests. The custom
route keeps thread history in memory for the current backend process, so
restarting `langgraph dev` starts a new session. This first version
intentionally uses `langgraph dev` so the v3 projection behavior can be tested
directly; AgentSeek API runtime integration can be added later after its v3
projection support is stable.

Set `AGENTSEEK_MODEL_PROVIDER`, `AGENTSEEK_MODEL`, and the matching provider
API key in `.env`. OpenAI-compatible gateways can set `OPENAI_API_BASE`.

The generated project pins `deepagents==0.6.12` and declares
`langgraph-cli[inmem]>=0.4` for the development runtime.
