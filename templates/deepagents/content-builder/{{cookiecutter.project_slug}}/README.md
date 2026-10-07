# {{ cookiecutter.project_name }}

DeepAgents content builder scaffolded with
`agentseek create deepagents/content-builder`.

The backend serves a `create_deep_agent(...)` graph through `agentseek-api dev`
with brand-voice memory, content skills (blog-post, social-media), optional
research and image generation tools. The default pure text mode uses local
course sources without search or image services. The frontend streams user
messages, tool calls, sub-agent delegation, generated images, and the final
markdown output. AgentSeek is used as the external lifecycle tool for local
inspection, readiness checks, development, and project tasks.

## Course

See [COURSE.md](COURSE.md) for the locked 0.7.8 environment, planning checks,
and reproducible learning inputs. The DeepSeek default was exercised with real
model calls. Inspect each run's saved text, tool trace and final state; the
default does not remove the need for review. Research artifacts in rehearsal
required source review and manual correction of unsupported claims.

## Setup

```bash
cp .env.example .env
cp frontend/.env.example frontend/.env
$EDITOR .env

agentseek task --list
agentseek task sync
agentseek task frontend
agentseek info
agentseek doctor
agentseek dev
```

The template defaults to `deepseek-ai/DeepSeek-V3.2` through SiliconFlow's
OpenAI-compatible API. The `openai` value in `AGENTSEEK_MODEL_PROVIDER`
selects the LangChain adapter; `.env.example` pre-fills
`OPENAI_API_BASE=https://api.siliconflow.cn/v1`. Put your SiliconFlow key in
`OPENAI_API_KEY`; credentials are left blank in the template.
`AGENTSEEK_PARALLEL_TOOL_CALLS=false` requests sequential tool calls for this
course exercise. Check the actual tool trace when rehearsing with your model.

`agent.py` also supports native Anthropic and Gemini integrations. To switch,
change `AGENTSEEK_MODEL_PROVIDER` and `AGENTSEEK_MODEL`, then fill only the
matching provider's credential and base-URL block. To use official OpenAI,
choose an OpenAI model, replace the key and clear the pre-filled
`OPENAI_API_BASE`. Blank base URLs use the selected provider's official
endpoint. Model compatibility aliases `DEEPAGENTS_MODEL` / `BUB_MODEL` remain
available.

The researcher subagent shares the main provider and base URL. To use another
model for research, set `AGENTSEEK_SUBAGENT_MODEL` to a model name served by
that endpoint; no provider prefix is needed.

## Environment

The root `.env` is referenced by both `langgraph.json` and
`.agentseek/lifecycle.toml`. LangGraph loads it for the backend process;
AgentSeek reads it for `doctor` readiness checks. Shell environment variables
still take precedence when present.

The frontend has its own `frontend/.env`. It only needs changes when the
LangGraph URL or frontend port differs from the scaffold defaults.

For the default SiliconFlow connection, keep the generated model and endpoint
and fill `OPENAI_API_KEY` with your SiliconFlow key. `DEEPAGENTS_MODEL` or
`BUB_MODEL` can be used as model aliases, and `BUB_OPENAI_API_KEY` can be used
as an OpenAI-adapter key alias. A provider switch needs a matching model, key
and endpoint; clear the pre-filled base URL when targeting official OpenAI.

Search requires full mode, CONTENT_ENABLE_SEARCH=true and TAVILY_API_KEY.
Images require full mode, CONTENT_ENABLE_IMAGES=true and GOOGLE_API_KEY.
A Google key is also used for google_genai chat models; chat alone does not
enable image tools.

## Lifecycle

```bash
agentseek info
agentseek doctor
agentseek dev
agentseek task --list
```

By default the backend listens on
`http://127.0.0.1:{{ cookiecutter.langgraph_port }}` and the frontend on
`http://127.0.0.1:{{ cookiecutter.frontend_port }}`. Runtime processes and
project tasks are declared in `.agentseek/lifecycle.toml`.

After `agentseek dev` starts, open the frontend and ask:

```text
In pure text mode, read planning.md, files.md and memory.md with read_source.
Plan and write a report citing those files; save_report(slug="course") and
read_report before completing the todos.
```

Expected behavior:

- A live **Content plan** todo panel appears when the agent writes todos.
- Local source, save and read-back cards appear; blogs/course/post.md exists.
- In full mode, enabled research and requested image tools add their cards.
- Each tool card expands while running, then collapses after its result
  lands.
- The final assistant response renders as markdown.

## Customization

- Edit `AGENTS.md` to change brand voice and writing standards.
- Add or modify skills under `skills/<name>/SKILL.md` for new content types.
- Add subagents in `subagents.yaml` and register their tools in `agent.py`.
- Set `GOOGLE_IMAGE_MODEL` in `.env` to use a different Gemini model for images.
- Generated content is written to `blogs/`, `linkedin/`, `tweets/`, and
  `research/` directories under the project root.
