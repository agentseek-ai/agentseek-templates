# DeepAgents — content-builder template

Scaffolds a `deepagents.create_deep_agent(...)` content writing agent with
brand memory, skills, local text sources, optional research/images, and an AgentSeek lifecycle
spec. The generated project runs through `agentseek info`, `agentseek doctor`,
`agentseek dev`, and `agentseek task`.

## Lifecycle

```text
agentseek dev
  -> .agentseek/lifecycle.toml
    -> uv run agentseek-api dev --port {{ langgraph_port }}
    -> npm run dev (frontend/)
```

Two long-running processes start in development:

| Process | Default port | Role |
| --- | --- | --- |
| `uv run agentseek-api dev --port {{ langgraph_port }}` | `{{ langgraph_port }}` | Serves the DeepAgents graph and image routes. |
| `npm run dev` | `{{ frontend_port }}` | Serves the Vite + React frontend. |

Project setup tasks are declared in `.agentseek/lifecycle.toml` and exposed
through `agentseek task --list`.

## Inputs

| Variable | Description |
| --- | --- |
| `project_name` | Human-readable project name. |
| `project_slug` | Python package / directory name (auto-derived). |
| `author` | Project author. |
| `default_model_provider` | Default `init_chat_model(..., model_provider=...)` provider. Ships as `openai`. |
| `default_model` | Default model id. Ships as `deepseek-ai/DeepSeek-V3.2` through the `openai` adapter and SiliconFlow endpoint. |
| `google_image_model` | Gemini model for image generation. Ships as `gemini-3.1-flash-image-preview`. |
| `tavily_max_results` | Default `web_search` result limit. |
| `tavily_topic` | Tavily topic filter (`general` or `news`). |
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
  README.md
  pyproject.toml
  uv.lock
  COURSE.md
  sources/
  memory/preferences.md
  tests/
  .agentseek/lifecycle.toml
  langgraph.json
  .env.example
  .gitignore
  AGENTS.md
  subagents.yaml
  skills/
    blog-post/
      SKILL.md
    social-media/
      SKILL.md
  src/{{ project_slug }}/
    __init__.py
    agent.py
    tools.py
    lesson_tools.py
    approval_demo.py
    webapp.py
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
      App.test.tsx
      TodoList.tsx
      ToolCallCard.tsx
      ToolCallCard.test.tsx
      ThinkingBlock.tsx
      ImageCard.tsx
      main.tsx
      styles.css
      vite-env.d.ts
```

## What's Adapted From Upstream

- Mirrors the upstream DeepAgents `content-builder-agent` example structure:
  AGENTS.md for brand voice, skills for blog/social workflows, subagents.yaml
  for a researcher with Tavily search, and image generation tools.
- Uses provider-first runtime config: generated apps select `openai`,
  `anthropic`, or `google_genai` in `.env`, then fill only the matching
  credential block.
- Treats blank provider base URLs as "use the official endpoint", while still
  allowing custom compatible gateways per provider.
- Lets generated apps override the scaffold-time model via `AGENTSEEK_MODEL`
  (plus `DEEPAGENTS_MODEL` / `BUB_MODEL` compatibility aliases) in `.env`.
- Image generation defaults to Google Gemini but supports custom endpoints via
  `GOOGLE_IMAGE_MODEL` and `GOOGLE_API_KEY` env vars.
- Adds a custom `/images/{path}` route via FastAPI so the frontend can display
  generated cover and social images inline.
- Adds a frontend for streamed tool/sub-agent visibility with an image preview
  component; upstream ships only the backend example.
- Surfaces DeepAgents `todos` state as a first-class progress panel instead of
  leaving planning updates buried in generic tool-call JSON.
- Declares local development processes and project tasks in
  `.agentseek/lifecycle.toml`.

## Deep Agents 0.7 course

The main agent explicitly opts into TodoListMiddleware on deepagents==0.7.8.
Generated projects ship uv.lock, COURSE.md and model-free graph checks.
Run agentseek task sync (uv sync --frozen), then agentseek task course-check.
Record the full template commit and use CLI 0.1.2 for the cohort.

The default CONTENT_MODE=text reads four fixed sources, saves and reads back
text without search/image credentials. Full mode uses explicit search/image
opt-ins. COURSE.md includes durable preference and SDK approve/reject
exercises with observable local files and a publication log.
