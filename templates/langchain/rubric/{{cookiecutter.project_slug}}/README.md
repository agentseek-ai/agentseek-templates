# {{ cookiecutter.project_name }}

An evidence-backed rubric revision lab built with LangChain `create_agent` and
`RubricMiddleware`. Guided Demo uses fixed deterministic evidence; Live Model
uses the provider and models configured in `.env`.

## Setup

```bash
cp .env.example .env
agentseek task sync
agentseek task frontend

agentseek info
agentseek doctor
agentseek dev --dry-run
```

Run `agentseek task frontend` before `agentseek doctor`; that task creates the
required `frontend/node_modules` path.

## Keyless Guided Demo

The Guided Demo is a fixed teaching task, so its evidence, grader feedback, and
revision comparison stay reproducible. Run the deterministic backend loop
without a model credential:

```bash
agentseek task rubric-smoke
```

## Live Model

Set `RUBRIC_API_KEY` in `.env`, then select `RUBRIC_PROVIDER` and optionally
override `RUBRIC_API_BASE`, `RUBRIC_WORKER_MODEL`, and `RUBRIC_GRADER_MODEL`.
Start the API and frontend together:

```bash
agentseek dev
```

The frontend is served at `http://127.0.0.1:{{ cookiecutter.frontend_port }}`
and the LangGraph API at `http://127.0.0.1:{{ cookiecutter.langgraph_port }}`.
You can also inspect the backend with LangGraph Studio through `agentseek info`.

## Status and security boundary

This template is Beta and tested against the dependency versions in
`pyproject.toml` and `frontend/package.json`. It is not a sandbox: Live Model
traffic goes to the configured provider, and the generated project does not
isolate model output, local files, tools, or network access from the host.
