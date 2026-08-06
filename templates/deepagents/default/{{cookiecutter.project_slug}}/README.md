# {{ cookiecutter.project_name }}

A DeepAgents-based agent project, scaffolded with `agentseek create deepagents`.
This template is intentionally minimal and does not include a frontend.
Default system prompt: Answer in the same language as the user's question.

The binding export is:

```text
{{ cookiecutter.project_slug }}.demo_binding:build_spec
```

## Quickstart

```bash
cp .env.example .env
$EDITOR .env

uvx agentseek info
uvx agentseek doctor
uvx agentseek task --list
uvx agentseek task sync

uvx agentseek dev
```

The gateway is declared in `.agentseek/lifecycle.toml` and defaults to
`http://127.0.0.1:{{ cookiecutter._gateway_port }}/agent`. AgentSeek is used as
the external lifecycle tool; the generated runtime is the project dependency
set in `pyproject.toml`.

## Environment

Copy `.env.example` to `.env` before running lifecycle checks. The generated
settings read `BUB_MODEL`, `BUB_API_KEY`, and optional `BUB_API_BASE`, with
`AGENTSEEK_*` and OpenAI-compatible aliases accepted where noted in the file.
`BUB_LANGCHAIN_SPEC` points the gateway at this package's `build_spec()`, and
`BUB_AG_UI_PORT` must match the service URLs declared in the lifecycle spec.

## DeepAgents profiles

DeepAgents profiles are named configuration layers that DeepAgents applies when
it builds an agent. They let an application customize a provider or the agent
harness without replacing `create_deep_agent()` or copying its internal
defaults. A profile must be registered before the agent is built, and
DeepAgents selects it from the provider or model specification being resolved.

There are two different profile scopes:

- `HarnessProfile` changes agent runtime behavior, such as prompts, middleware,
  tool visibility, and default subagent settings. It answers: "how should this
  agent behave?"
- `ProviderProfile` changes model construction and initialization arguments
  while a `provider:model` string is resolved into a chat model. It answers:
  "how should this provider's model be initialized?"

This template uses a `ProviderProfile`, not a `HarnessProfile`, because the
model-construction option `use_responses_api=False` must be applied while
DeepAgents resolves an `openai:<model>` string into a chat model.

For example, the generated binding registers:

```python
register_provider_profile(
    "openai",
    ProviderProfile(init_kwargs={"use_responses_api": False}),
)
```

This makes `openai:<model>` specifications use the Chat Completions API. It
is useful for OpenAI-compatible endpoints that support Chat Completions but do
not implement the OpenAI Responses API. This is a short-term compatibility
workaround: because the profile is registered for the `openai` provider, every
`openai:<model>` specification in this generated binding is forced to use Chat
Completions, including models that may also support the Responses API.

Learn more in the official [DeepAgents profiles documentation](https://docs.langchain.com/oss/python/deepagents/profiles),
[model documentation](https://docs.langchain.com/oss/python/deepagents/models),
and [DeepAgents overview](https://docs.langchain.com/oss/python/deepagents/overview).

## Files

| File | Purpose |
| --- | --- |
| `.agentseek/lifecycle.toml` | Declares AgentSeek `info`, `doctor`, `dev`, and `task` behavior. |
| `.env.example` | Documents runtime model, provider, LangChain binding, and AG-UI port variables. |
| `src/{{ cookiecutter.project_slug }}/demo_binding.py` | Builds the DeepAgents runnable and exports `build_spec()`. |
| `src/{{ cookiecutter.project_slug }}/settings.py` | Reads env vars; bridges `AGENTSEEK_*` into `OPENAI_*` when needed. |
| `requirements.txt` | Extra Python dependencies. |

Author: {{ cookiecutter.author }}
