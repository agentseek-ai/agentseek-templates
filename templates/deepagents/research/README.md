# DeepAgents — research template

Scaffolds a pure `deepagents.create_deep_agent(...)` research project with a
LangGraph backend and a Vite + React frontend that streams tool calls,
sub-agent delegation, a live DeepAgents todo panel, and the final markdown
report.

## Inputs

| Variable | Description |
| --- | --- |
| `project_name` | Human-readable project name. |
| `project_slug` | Python package / directory name (auto-derived). |
| `author` | Project author. |
| `default_model_provider` | Default `init_chat_model(..., model_provider=...)` provider. Ships as `openai`. |
| `default_model` | Default model id. Ships as `deepseek-ai/DeepSeek-V3.2` through the `openai` adapter and SiliconFlow endpoint. |
| `tavily_max_results` | Default `tavily_search` result limit. |
| `tavily_topic` | Tavily topic filter (`general`, `news`, or `finance`). |
| `max_concurrent_research_units` | Max sub-agent tasks the orchestrator may queue concurrently. |
| `max_researcher_iterations` | Max search/reflection loops per research unit. |
| `langgraph_port` | Default backend port for `agentseek-api dev`. |
| `frontend_port` | Default Vite dev-server port. |

## Default model connection

The default model is `deepseek-ai/DeepSeek-V3.2`, served by SiliconFlow's
OpenAI-compatible API. The `openai` provider value selects the LangChain
adapter; `.env.example` pre-fills `OPENAI_API_BASE=https://api.siliconflow.cn/v1`.
Copy it to `.env` and put your SiliconFlow key in `OPENAI_API_KEY`. Credentials
are left blank in the template. `AGENTSEEK_PARALLEL_TOOL_CALLS=false` requests
sequential tool calls for the course exercise.

To use official OpenAI, choose a model served by OpenAI, replace the key, and
clear the pre-filled `OPENAI_API_BASE`. For Anthropic or Gemini, change
`AGENTSEEK_MODEL_PROVIDER` and `AGENTSEEK_MODEL`, then fill the matching key
and base-URL variables. Blank provider base URLs use official endpoints.

The default was exercised with real model calls. Check actual tool results,
saved artifacts and final todos for each run; model choice does not guarantee
correctness. Research artifacts required source review and manual correction
of unsupported claims during rehearsal.

## Generated layout

```text
{{ project_slug }}/
  .agentseek/
    lifecycle.toml
  README.md
  pyproject.toml
  uv.lock
  COURSE.md
  tests/
  langgraph.json
  .env.example
  .gitignore
  src/{{ project_slug }}/
    __init__.py
    agent.py
    prompts.py
    tools.py
  frontend/
    package.json
    .env.example
    .gitignore
    index.html
    vite.config.ts
    tsconfig.json
    tsconfig.node.json
    src/
      App.tsx
      TodoList.tsx
      ToolCallCard.tsx
      main.tsx
      styles.css
      vite-env.d.ts
```

## What's Adapted From Upstream

- Mirrors the upstream DeepAgents `deep_research` prompt structure and Tavily +
  `think_tool` workflow.
- Uses provider-first runtime config: generated apps select `openai`,
  `anthropic`, or `google_genai` in `.env`, then fill only the matching
  credential block.
- Declares AgentSeek dev lifecycle v2 in `.agentseek/lifecycle.toml`, including
  `info`, `doctor`, `dev`, and `task` entry points for local development.
- Treats blank provider base URLs as "use the official endpoint", while still
  allowing custom compatible gateways per provider.
- Lets generated apps override the scaffold-time model via `AGENTSEEK_MODEL`
  (plus `DEEPAGENTS_MODEL` / `BUB_MODEL` compatibility aliases) in `.env`.
- Defaults to provider `openai` with `deepseek-ai/DeepSeek-V3.2` and the
  SiliconFlow endpoint pre-filled in `.env.example`.
- Supports official OpenAI and other compatible gateways by changing the
  model, credential and `OPENAI_API_BASE` together.
- Adds a frontend for streamed tool/sub-agent visibility; upstream ships only
  the backend example.
- Surfaces DeepAgents `todos` state as a first-class progress panel instead of
  leaving planning updates buried in generic tool-call JSON.

## Deep Agents 0.7 course

The main agent explicitly opts into TodoListMiddleware on deepagents==0.7.8.
Generated projects ship uv.lock, COURSE.md and model-free graph checks.
Run agentseek task sync (uv sync --frozen), then agentseek task course-check.
Record the full template commit and use CLI 0.1.2 for the cohort.
