# {{ cookiecutter.project_name }}

LangChain `create_agent` with the default AgentSeek middleware and CopilotKit/Bub/AG-UI runtime, plus NeMo Relay observability and Tavily web research.

## Architecture

```text
Browser → CopilotKit → Bub / AG-UI → research_then_present runnable
  ├─ Research Agent: Tavily + think_tool, without a structured-output constraint
  ├─ Presentation Agent: ordinary Markdown output, without web tools
  └─ shared request-scoped Relay callback
    ├─ ATOF JSONL: .nemo-relay/atof/events.jsonl
    └─ OpenInference over OTLP → Phoenix → OceanBase SeekDB
```

ATOF is the raw audit/debug archive. OpenInference over OTLP is Phoenix's input. Phoenix is the trace UI. SeekDB is Phoenix's default persistent database. The app uses `NemoRelayMiddleware`, not `LangChainInstrumentor`, so an LLM or Tool call is not double-instrumented. Models must support Tool Calling to show useful Tool Trace.

## Quick start

```bash
cp .env.example .env
# Set BUB_API_KEY and TAVILY_API_KEY in .env
agentseek dev
```

The browser is at `http://127.0.0.1:{{ cookiecutter.frontend_port }}`; Phoenix is at `http://127.0.0.1:6006`. Compose starts `langchain-app`, `frontend`, `phoenix`, and `seekdb`. First startup downloads Docker images plus Python and Node dependencies.

## Research example

```text
检索 NeMo Relay 和 OpenInference 的关系，给出两个来源并简要比较。
```

Search, current-information, and fact-verification requests run in a dedicated Research Agent. It must produce `tavily_search` evidence before the Presentation Agent receives bounded titles, URLs, and page excerpts. The Presentation Agent has no web tools: it renders only the completed research result as ordinary Markdown, preventing strict structured output from suppressing a required tool call. If research fails, the Presentation Agent renders the explicit failure instead of leaving a progress placeholder.

## End-to-end verification

Submit this message in the browser:

```text
请使用联网搜索工具搜索 NVIDIA NeMo Relay 官方文档，并列出前两个搜索结果的标题和 URL，不要凭记忆回答。
```

The final UI must show retrieved titles, URLs, and summaries rather than “正在搜索” or “请稍候”. The Presentation Agent uses ordinary Markdown instead of forcing LangChain `ProviderStrategy`, so the template remains compatible with Claude, DeepSeek, NVIDIA NIM, and other OpenAI-compatible models. This prioritizes cross-model compatibility for the search and observability path. If you enable structured UI output, confirm that the selected model and provider support `response_format`/JSON Schema. Then verify Relay and persistence:

```bash
wc -l .nemo-relay/atof/events.jsonl
grep -n 'tavily_search' .nemo-relay/atof/events.jsonl | tail
docker compose exec -T seekdb sh -lc "mysql -N -h127.0.0.1 -P2881 -uroot -e 'SELECT COUNT(*) FROM phoenix.traces; SELECT COUNT(*) FROM phoenix.spans;'"
```

The latest Phoenix trace should contain the root `agentseek` span, `research_agent`, `tavily_search`, and `presentation_agent` spans. ATOF is mounted at `.nemo-relay/atof/events.jsonl` on the generated project host.

## Configuration

Set `BUB_MODEL`, `BUB_API_KEY`, and optionally `BUB_API_BASE`. `TAVILY_API_KEY` is required by lifecycle/doctor. `TAVILY_MAX_RESULTS` is capped at 3 and `TAVILY_TOPIC` defaults to `general`.


To keep only the raw archive, set `RELAY_PHOENIX_ENABLED=false`; ATOF remains enabled. To disable all Relay registration and export, set `RELAY_ENABLED=false`. To change images, set `AGENTSEEK_PHOENIX_IMAGE` or `OCEANBASE_SEEKDB_IMAGE`. Do not put real keys in source control.

## Troubleshooting

- Missing Tavily key: set `TAVILY_API_KEY` in `.env`, then rerun `agentseek doctor`.
- Fetch failures: check the URL/network; the tool returns a bounded failure marker and continues.
- No Phoenix trace: verify `RELAY_ENABLED=true`, `RELAY_PHOENIX_ENABLED=true`, Phoenix is healthy, and the model supports Tool Calling. The OTLP endpoint inside Compose is `http://phoenix:6006/v1/traces`.
- Persistence: inspect `.seekdb-data` after shutdown/restart; Phoenix stores traces through `mysql://root@seekdb:2881/phoenix`.

ATOF events are available at `.nemo-relay/atof/events.jsonl`; Phoenix traces are available in the Phoenix UI and persist in SeekDB. Local directories `.nemo-relay/`, `.phoenix-data/`, and `.seekdb-data/` are ignored by Git.
