# Reproducible Deep Agents 0.7 course

This project pins `deepagents==0.7.8` and `agentseek-api[embedded]==0.2.3`.
`uv.lock` pins transitive dependencies and hashes for Python 3.12/3.13.
Use `uv sync --frozen --dev` (also `agentseek task sync`) and retain the lock;
do not use `uv lock --upgrade` during a cohort. Frontend dependencies are
separate; archive the generated frontend/package-lock.json for the cohort.

## Record the cohort environment

In the template repository, record `git rev-parse HEAD` and use that full
commit when scaffolding with AgentSeek's `--template-repo` and
`--checkout` options. Use the same project/config inputs throughout
the cohort. Preserve the CLI-generated source metadata under `.agentseek/`.
Use the reviewed CLI `uvx agentseek==0.1.2` for lifecycle commands.

From the generated project, record these commands in your course notes:

```bash
uv --version
uvx agentseek==0.1.2 --version
uv run --frozen python -c "import sys, importlib.metadata as m; print(sys.version); print({n: m.version(n) for n in ['deepagents', 'agentseek-api', 'langchain', 'langchain-core', 'langgraph', 'langgraph-sdk']})"
uv lock --check
```

Keep the template SHA, scaffold inputs, OS/architecture, Python version,
model/provider id, CLI version and uv.lock together. Credentials stay in .env.
Model responses can differ; the scripted tests below prove mechanisms.

## Planning (v0.7 is opt-in)

`src/{{ cookiecutter.project_slug }}/agent.py:build_graph` explicitly supplies
`middleware=[TodoListMiddleware()]`. This registers `write_todos` and the
`todos` state. The existing React frontend reads `stream.values.todos`.
Ask the agent to plan actual work steps, do the work, verify outputs, then
update the plan. Do not make updating the plan itself a todo. Call write_todos
at most once per model response. Saving, reading back, and marking complete
are dependent operations: wait for a successful tool result between them.
Mark all successful steps completed before the final answer; leave failed
steps incomplete. A completed todo alone is not evidence of a completed report.

Run `agentseek task course-check` or:

```bash
uv run --frozen pytest tests -q
```

The chat model is scripted; the actual Deep Agents graph invokes
write_todos. Tests check in_progress/completed values in the stream and
checkpoint state. API stream verification also checks the values events
consumed by the frontend. No model credentials are used for those checks.

## Default model connection

The template defaults to `deepseek-ai/DeepSeek-V3.2` through SiliconFlow's
OpenAI-compatible API. `AGENTSEEK_MODEL_PROVIDER=openai` selects the adapter;
`.env.example` pre-fills `OPENAI_API_BASE=https://api.siliconflow.cn/v1` and
`AGENTSEEK_PARALLEL_TOOL_CALLS=false`. Copy it to `.env` and fill
`OPENAI_API_KEY` with your SiliconFlow key. No credential is included.

To use official OpenAI, change the model and key and clear the pre-filled
`OPENAI_API_BASE`. For Anthropic or Gemini, change the provider and model and
fill the corresponding key/base-URL block. Blank base URLs use official
endpoints. The sequential setting applies only to the OpenAI adapter; remove
it when the endpoint does not support the parameter or when testing parallel
research.

The DeepSeek default was exercised with real model calls. Research artifacts
still required source review and manual correction of unsupported claims.
Treat the default as a rehearsed configuration and verify every saved output,
actual tool result and final state before accepting a run.

## Rehearse with the cohort's real model

The scripted checks establish graph and API behavior. Also run the exercise
with the exact provider/model chosen for the cohort. Record its model ID,
actual tool calls, in_progress/completed values and final thread state;
inspect the saved artifact and successful readback. A textual claim that a
step is complete is not a state update. Reject a run that leaves a todo
unfinished, combines dependent write/read calls before receiving results,
or produces unsupported claims.

The default `.env.example` sets `AGENTSEEK_PARALLEL_TOOL_CALLS=false` to
request one tool call per model response from a supporting OpenAI-compatible
provider. This setting is shared with subagent models; it also disables
parallel delegation, so enable it for the sequential course exercise rather
than a parallel-research benchmark. Leave it unset for gateways that do not
support the parameter. Confirm actual behavior in the tool trace.

Smaller models can omit tool calls or issue conflicting parallel updates.
A staged exercise can demonstrate the mechanism: ask only for one
write_todos update with in_progress, wait for the actual tool result, then
continue the work and request completed only after verifying its artifact.
Record this as staged verification rather than autonomous workflow success.
For content-builder, also verify the synthetic-material label, learned
preferences in a fresh thread, and both publication approval decisions.

## Local text workflow

Set `CONTENT_MODE=text` (the default). Configure only a chat model and its
credential in .env; leave Tavily and image services disabled. Start via
`agentseek dev` and submit this fixed input:

```text
Use blog-post in pure text mode. Read planning.md, files.md and memory.md
with read_source. Write a course report with a title, Context, Findings,
Practical steps and Sources. Cite all three local filenames. Save it using
save_report(slug="course", content=...). Read it back with read_report.
Plan with write_todos, and mark complete only after checking the saved file.
Do not search the web or generate images.
```

Expected file: `blogs/course/post.md`. Check its headings and Sources section
with `read_report` or your editor. Four synthetic notes are under sources/;
they are fixed exercise inputs, not claims about external research.

To add web research, set CONTENT_MODE=full, CONTENT_ENABLE_SEARCH=true and
TAVILY_API_KEY. To add images, set CONTENT_ENABLE_IMAGES=true and GOOGLE_API_KEY
as well; images run only when requested. A Gemini chat key by itself does not
enable images. Restart after changing capabilities. Missing enabled-service
credentials fail at startup instead of exposing unusable tools.

## Preferences across new conversations

In the UI, ask: "Remember language=Chinese using save_preference".
Read `memory/preferences.md`: it must contain `language: Chinese`.
Open a new conversation/thread without old messages and ask the agent to
state its saved language. `memory=["/AGENTS.md", "/memory/preferences.md"]`
loads fixed guidance and learned preferences separately from FilesystemBackend.
The custom MemoryMiddleware prompt replaces implicit SDK memory-write guidance
with the explicit-request-only save_preference protocol.
The scripted test verifies the new model prompt contains the written
preference and does not contain the old user message.

Files persist only in this project directory; all local users of this copy
share them. Checkpoints are separate: the server owns its embedded SeekDB
checkpointer. StoreBackend plus a user namespace is an advanced extension,
not part of this single-user filesystem exercise.

## Local publication approval (SDK)

The browser does not implement approve/reject. The default UI graph therefore
does not register publish_report. Use the SDK example with the same graph
factory and FilesystemBackend:

```bash
uv run --frozen python -m {{ cookiecutter.project_slug }}.approval_demo --decision approve
uv run --frozen python -m {{ cookiecutter.project_slug }}.approval_demo --decision reject
```

`approval_demo.py` saves a fixed report, compiles with InMemorySaver and
`interrupt_on={"publish_report": {"allowed_decisions": ["approve", "reject"]}}`,
prints and checks `__interrupt__`, and resumes the same thread with
`Command(resume={"decisions": [{"type": decision}]})`. The log is
`reports/publications.jsonl`. Approve adds exactly one line; reject adds none.
The example compares counts with any prior records, so it can be rerun.
This records a local test publication only. The SDK checkpoint survives only
for that process; server runs use the server checkpointer instead. The tests
exercise both decisions without relying on the final model reply.
