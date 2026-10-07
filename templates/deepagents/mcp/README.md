# DeepAgents MCP template

This template scaffolds a DeepAgents application around a strict MCP Tools
boundary. It includes local calculator MCP servers over stdio and Streamable
HTTP, model-free smoke coverage, a streamed React UI, and an AgentSeek lifecycle
specification.

## Architecture

The generated application keeps four responsibilities separate:

- `.mcp.json` declares the MCP servers and transport settings.
- `config.py` validates the complete file before interpolating environment values.
- `mcp_tools.py` discovers every server and adds stable server-name prefixes.
- `agent.py` builds and caches one DeepAgents graph for the process lifetime.

The frontend renders streamed messages, tool calls, results, and errors. It is a
chat client, not a browser-based MCP configuration editor.

### Connection contract

The `mcpServers` object must contain at least one server. Server names may use
letters, numbers, `_`, and `-`. They become the prefix for exposed tool names.

A `stdio` server has this shape:

```json
{
  "mcpServers": {
    "calculator": {
      "transport": "stdio",
      "command": "${PYTHON_EXECUTABLE}",
      "args": ["-m", "mcp_deepagent.calculator_server"],
      "env": {"SERVICE_TOKEN": "${SERVICE_TOKEN}"}
    }
  }
}
```

A Streamable HTTP server uses the adapter's `http` transport value:

```json
{
  "mcpServers": {
    "billing": {
      "transport": "http",
      "url": "${BILLING_MCP_URL}",
      "headers": {"Authorization": "Bearer ${BILLING_MCP_TOKEN}"}
    }
  }
}
```

The generated default config declares `calculator` over stdio and
`calculator_http` at `http://127.0.0.1:8765/mcp`. Its AgentSeek lifecycle starts
the HTTP server and checks `http://127.0.0.1:8765/health`.

`${ENV_VAR}` references are interpolated in commands, arguments, environment
values, URLs, and headers. Every reference must resolve.
`${PYTHON_EXECUTABLE}` is reserved and always resolves to the current Python
interpreter. An environment variable named `PYTHON_EXECUTABLE` cannot override
it.

Configuration and discovery are all-or-nothing. Every configured server must
connect and expose at least one tool. If any server fails or returns no tools,
graph creation fails without a partial tool set. `tool_name_prefix=True`
exposes tools as `<server>_<tool>`, such as `calculator_add`,
`calculator_http_multiply`, or `billing_charge_card`. Final names must be unique and cannot replace registered DeepAgents built-ins:
`write_todos`, `delete`, `ls`, `read_file`, `write_file`, `edit_file`, `glob`,
`grep`, or `execute`. The default StateBackend hides `execute` from the model
but still registers it in ToolNode, so its name remains reserved. The `task`
tool is disabled by this template's HarnessProfile and is not reserved.

The graph is cached after the first successful build. Restart the AgentSeek
development processes after changing `.mcp.json`, model settings, or server
credentials. MCP tool calls are stateless and do not retain persistent MCP
client sessions between calls.

## Adapt the template

This template pins DeepAgents to `0.7.8` and includes `uv.lock`. Python 3.12
and 3.13 use the same reviewed dependency resolution. The lifecycle uses
`uv sync --frozen` and `uv run --frozen` to preserve it. TodoListMiddleware is
explicit because 0.7 no longer installs todo planning automatically. The
generated runtime tests characterize the real ToolNode, collision guard,
todo state, and disabled general-purpose subagent profile together.

The smoke task starts or reuses the local HTTP server, checks the complete
discovered tool-name tuple, and performs a real calculator invocation through
both stdio and Streamable HTTP. It stops the HTTP server when it started that
process itself. Adding, removing, or replacing any server changes the complete
discovered tool-name tuple, so update the calculator smoke contract at the same
time.

The template defaults to `Qwen/Qwen2.5-7B-Instruct` through SiliconFlow's
OpenAI-compatible API. `AGENTSEEK_MODEL_PROVIDER=openai` selects the adapter;
`.env.example` pre-fills `OPENAI_API_BASE=https://api.siliconflow.cn/v1`.
Copy it to `.env` and put your SiliconFlow key in `AGENTSEEK_MODEL_API_KEY`;
credentials are left blank. Real-model verification called both calculator
transports and checked local publication approve/reject log deltas. This
narrow calculator result does not establish accuracy for other tasks.

For official OpenAI, choose an OpenAI model, replace the key and clear the
pre-filled `OPENAI_API_BASE`. For native Anthropic or Gemini, change the
provider and model and fill the corresponding base-URL block. Keep
`AGENTSEEK_MODEL_API_KEY` as the selected provider's lifecycle credential.
Blank provider base URLs use official endpoints.

Set `AGENTSEEK_MODEL_PROVIDER` and `AGENTSEEK_MODEL` for the DeepAgents graph.
`DEEPAGENTS_MODEL` and `BUB_MODEL` are model-name compatibility aliases.
`AGENTSEEK_MODEL_API_KEY` is the lifecycle credential and is passed explicitly
to the selected provider adapter. Provider-native API keys remain direct-runtime
fallbacks; they do not satisfy `agentseek doctor`. Optional custom endpoints
continue to use the provider-native variables in `.env.example`. Optional
LangSmith tracing uses `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, and
`LANGSMITH_PROJECT`. Set `LANGSMITH_ENDPOINT` when your LangSmith API key
belongs to the APAC or another non-default region (for example
`https://apac.api.smith.langchain.com`); otherwise traces may fail to upload
to the cloud.

All three development processes bind to loopback by default. `LANGGRAPH_HOST`
controls the AgentSeek API bind address and `FRONTEND_HOST` controls Vite. Set
either in the launching shell or root `.env`; explicitly exported shell values
take precedence. The calculator HTTP server remains loopback-only.

The frontend derives `http://<browser-host>:2024` by default. For an HTTPS
frontend or a reverse proxy that changes the backend's public scheme, port, or
path, set `VITE_LANGGRAPH_API_URL` in `frontend/.env` to the public LangGraph
API URL. Keep MCP URLs, headers, and credentials out of Vite variables.

This v1 template exposes MCP Tools only. It does not expose MCP Resources or
Prompts, persistent MCP client sessions, interceptors, OAuth helpers, or a
browser-based MCP configuration editor.

## Security boundary

Treat every configured `stdio` command as trusted local code execution. Review
the executable, arguments, working environment, and package source before use.

Keep secrets in the process environment or the untracked `.env` file and
reference them from `.mcp.json` with `${ENV_VAR}`. The root `.env` file is loaded
by both `agentseek task mcp-smoke` and `agentseek dev`, while exported process
values take precedence. Never put secret literals in tracked `.mcp.json`,
commits, logs, error messages, shell output, or shared output, and never echo
them. Do not rely on the template to redact arbitrary MCP tool error content.

For Streamable HTTP, the template validates configuration shape and absolute
`http` or `https` URLs. TLS, network ACLs, and authentication or OAuth must be
enforced at the MCP server, gateway, or deployment boundary. This template does
not create that boundary.

MCP tool descriptions and annotations do not authorize calls. Enforce
authorization in the tool service. For explicit DeepAgents human-in-the-loop
policy, use the final prefixed tool name, for example:

```python
interrupt_on={
    "billing_charge_card": {"allowed_decisions": ["approve", "reject"]},
}
```

This example does not enable automatic HITL. An application contributor must add
and test the policy when assembling the graph.

## Locked runtime and approval experiment

The application and SDK experiments use **Deep Agents 0.7.8** with explicit
todo planning. The main UI graph does not enable `interrupt_on`, and the
frontend has no approve/reject controls. The SDK experiment below demonstrates
approval and resume with actual MCP tools and a local publication log.

Run `agentseek task mcp-smoke` to discover and call the bundled stdio and
Streamable HTTP calculators. Run `agentseek task mcp-approval-smoke` for the
model-free SDK approval experiment. No chat-provider credential is needed.
`approval_smoke.py` uses the same build_graph/Profile as the app, the actual
MCP discovery, a local publish_calculation tool and InMemorySaver. It checks
__interrupt__, resumes the same thread with Command(resume=...), and reads
the actual JSONL side effect: approve writes stdio=95/http=2146 once, reject
writes nothing. The temporary logs are inspected before cleanup; the printed
counts show the result. The SDK checkpoint lasts for this process only;
the application server owns its own configured checkpoint backend.

Run `agentseek task test` for the full generated Python suite. It writes
todo state through the actual graph, checks all nine registered built-in
names, rejects an external `delete` collision, calls both MCP transports,
and verifies the approve/reject publication log deltas. These checks do not
call a hosted model or require a chat-provider credential.
