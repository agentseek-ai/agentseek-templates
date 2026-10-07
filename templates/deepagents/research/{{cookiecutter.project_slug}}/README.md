# {{ cookiecutter.project_name }}

Pure DeepAgents research agent scaffolded with `agentseek create deepagents/research`.

The backend serves a `create_deep_agent(...)` graph through `agentseek-api dev`.
The frontend streams user messages, tool calls, optional sub-agent delegation,
DeepAgents todos, and the final markdown answer. AgentSeek is only used as an
external template and lifecycle tool; this project declares local behavior in
`.agentseek/lifecycle.toml`.

## Course

See [COURSE.md](COURSE.md) for the locked 0.7.8 environment and scripted
planning checks. The DeepSeek default was exercised with real model calls,
including planning and research artifact readback. Research artifacts required
source review and manual correction of unsupported claims during rehearsal;
verify saved output and final state for each run.

## Quickstart

```bash
cp .env.example .env
cp frontend/.env.example frontend/.env
$EDITOR .env

uvx agentseek task sync
uvx agentseek task frontend

uvx agentseek info
uvx agentseek doctor
uvx agentseek dev --dry-run
uvx agentseek dev
```

Use `uvx agentseek task --list` to see the one-shot setup tasks exposed by the
lifecycle spec. After `uvx agentseek dev` starts both processes, run
`uvx agentseek doctor --live` from another terminal to check the declared local
service endpoints.

The LangGraph backend defaults to `http://127.0.0.1:{{ cookiecutter.langgraph_port }}`.
The frontend defaults to `http://127.0.0.1:{{ cookiecutter.frontend_port }}`.

## Environment

The template defaults to `deepseek-ai/DeepSeek-V3.2` through SiliconFlow's
OpenAI-compatible API. `AGENTSEEK_MODEL_PROVIDER=openai` selects the LangChain
adapter; `.env.example` pre-fills
`OPENAI_API_BASE=https://api.siliconflow.cn/v1`. Put your SiliconFlow key in
`OPENAI_API_KEY`; credentials are left blank in the template.
`AGENTSEEK_PARALLEL_TOOL_CALLS=false` requests sequential tool calls for the
course exercise, including subagents. Leave it unset for a parallel-research
benchmark or an endpoint that does not support the parameter.

`agent.py` also supports native Anthropic and Gemini integrations. Change
`AGENTSEEK_MODEL_PROVIDER` and `AGENTSEEK_MODEL` together, then fill the
selected provider's key and base-URL block. For official OpenAI, choose an
OpenAI model, replace the key and clear the pre-filled `OPENAI_API_BASE`.
Blank provider base URLs use official endpoints. `AGENTSEEK_MODEL` can also
be supplied through `DEEPAGENTS_MODEL` or `BUB_MODEL`.

`TAVILY_API_KEY` is required for the `tavily_search` tool. The lifecycle spec
checks that one provider API key exists through `OPENAI_API_KEY` plus the
`ANTHROPIC_API_KEY` and `GOOGLE_API_KEY` aliases; it does not validate that the
key matches the selected provider.

`frontend/.env` only controls the browser app's LangGraph URL and Vite port.

## Smoke test

Open `http://127.0.0.1:{{ cookiecutter.frontend_port }}` and ask:

```text
Research what LangGraph 1.0 added vs 0.x. Cite sources.
```

Expected behavior:

- A live **Research plan** todo panel appears when the agent writes todos.
- Tool cards appear for `tavily_search` and, when the model delegates,
  `task` as a "Sub-agent: research-agent" card.
- Each card expands while running, then collapses after its result lands.
- The final assistant response renders as markdown with linked citations.
