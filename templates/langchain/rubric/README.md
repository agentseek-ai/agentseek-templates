# langchain/rubric

Scaffold an evidence-backed rubric revision lab for LangChain. A first-time
evaluator can run the complete Guided Demo without a model key. An application
developer can then configure the same fixed task for provider-backed grading.

## Why this template is under `langchain/`

`RubricMiddleware` is a generic LangChain `AgentMiddleware`. The generated
application places it in the middleware list passed to `create_agent`.
`create_deep_agent` would add planning, filesystem, and sub-agent concepts that
are unrelated to the rubric lesson.

The generated project pins `deepagents==0.7.1`, `langchain==1.3.14`, and
`langgraph==1.2.10`. `RubricMiddleware` is **Beta**. Before changing any exact
pin, maintainers must rerun the generated characterization suite, keyless smoke,
frontend tests and build, and lifecycle validation.

## Learning modes

- **Guided Demo** uses one fixed task, fixed rubric, positive iteration cap,
  deterministic candidates, and recorded Evidence. It needs no model key.
- **Live Model** keeps the task fixed. You can edit only the rubric and positive
  iteration cap. Provider and model settings stay on the LangGraph server.

Each Run starts a fresh LangGraph thread. Reports from Guided Demo and Live
Model remain isolated. Acceptance requires terminal `satisfied` plus passing
Evidence for the exact current candidate.

## Generated setup contract

The generated first-run guide copies `.env.example` to `.env` before
`agentseek info`, `agentseek doctor`, or `agentseek dev`. The lifecycle requires
that server environment file, but Guided Demo needs no credential.

For Live Model, run `$EDITOR .env`, set `AGENTSEEK_MODEL_PROVIDER`,
`AGENTSEEK_MODEL`, and `RUBRIC_GRADER_MODEL`, then fill exactly one
provider-native credential/base block: `OPENAI_API_KEY` with optional
`OPENAI_API_BASE`, `ANTHROPIC_API_KEY` with optional `ANTHROPIC_API_URL`, or
`GOOGLE_API_KEY` with optional `GOOGLE_API_BASE`. Leave the other provider
blocks empty. These are LangGraph server settings, never browser configuration
and never values for `frontend/.env`.

## Security boundary

The fixed child-process profile strips inherited environment values, uses a
timeout and output cap, and restricts Python built-ins. It is not a sandbox and
does not isolate filesystem, network, or system calls from the host.

## Reviewed teaching source

The exact reviewed course source is
[DeepAgents in Action, Chapter 13](https://github.com/datawhalechina/deepagents-in-action/blob/6fcef2294bc1ae19e97054426c1355923b50493a/content/ch13-grading-rubrics.md).

## Inputs

| Variable | Description |
| --- | --- |
| `project_name` | Human-readable project name. Defaults to "Rubric Lab". |
| `project_slug` | Python package and generated directory name. |
| `author` | Project author. |
| `default_provider` | Live provider: `openai`, `anthropic`, or `google`. |
| `worker_model` | Model that drafts and revises candidate code. |
| `grader_model` | Model that grades Evidence against the rubric. |
| `langgraph_port` | Port for the LangGraph development API. |
| `frontend_port` | Port for the Vite application. |
