# DeepAgents — default template

Scaffolds a local `create_deep_agent(...)` runnable with an AgentSeek lifecycle
spec and an `agentseek-langchain` binding. This template is intentionally
minimal and does not include a frontend.

## Architecture

```text
uvx agentseek dev
  -> .agentseek/lifecycle.toml
    -> uv run bub gateway --enable-channel ag-ui
      -> agentseek-langchain
    -> messages_spec(...)
      -> create_deep_agent(...)
```

The binding export is `{{ project_slug }}.demo_binding:build_spec`.

For `openai:` model specifications, the generated binding registers a
DeepAgents provider profile that uses the Chat Completions API. This keeps the
template compatible with OpenAI-compatible endpoints that do not implement
the Responses API. Other providers retain their normal DeepAgents behavior.

## DeepAgents profiles

DeepAgents profiles are named configuration layers that DeepAgents applies
when it builds an agent. They let an application customize a provider or the
agent harness without replacing `create_deep_agent()` or copying its internal
defaults. A profile is registered before the agent is built and is selected
from the provider or model specification being resolved.

There are two different profile scopes:

- `HarnessProfile` changes agent runtime behavior, such as prompts,
  middleware, tool visibility, and default subagent settings. It answers
  "how should this agent behave?"
- `ProviderProfile` changes model construction and initialization arguments.
  It is applied while a `provider:model` string is resolved into a chat model.
  It answers "how should this provider's model be initialized?"

This template uses a `ProviderProfile`, not a `HarnessProfile`, because
`use_responses_api=False` must be applied during model construction for
`openai:<model>` specifications. This is a short-term compatibility
workaround: every `openai:<model>` specification in the generated binding is
forced to use Chat Completions, including models that may also support the
Responses API.

See the official [DeepAgents profiles documentation](https://docs.langchain.com/oss/python/deepagents/profiles),
[model documentation](https://docs.langchain.com/oss/python/deepagents/models),
and [DeepAgents overview](https://docs.langchain.com/oss/python/deepagents/overview)
for more information.

## Inputs

| Variable | Description |
| --- | --- |
| `project_name` | Human-readable project name. |
| `project_slug` | Python package / directory name (auto-derived). |
| `author` | Project author. |
| `system_prompt` | System prompt baked into the agent. |
| `default_model` | Default `BUB_MODEL` value used by `settings.py`. |

## Generated layout

```
{{ project_slug }}/
  README.md
  pyproject.toml
  requirements.txt
  Dockerfile
  .env.example
  .agentseek/
    lifecycle.toml
  src/{{ project_slug }}/
    __init__.py
    demo_binding.py
    settings.py
```

## Lifecycle

The generated project exposes the standard AgentSeek lifecycle surface:

```bash
agentseek info
agentseek doctor
agentseek dev --dry-run
agentseek task --list
```

Readiness checks, service URLs, the gateway process, and the AG-UI health
check endpoint are declared in `.agentseek/lifecycle.toml`.

## Key code patterns

The core binding is two layers — build the DeepAgents runnable, then wrap it
with `messages_spec`:

```python
from agentseek_langchain import messages_spec
from deepagents import ProviderProfile, create_deep_agent, register_provider_profile

def build_agent():
    register_provider_profile(
        "openai",
        ProviderProfile(init_kwargs={"use_responses_api": False}),
    )
    return create_deep_agent(
        model=settings.require_model(),
        tools=[outline_answer],
        system_prompt="You are a pragmatic engineering assistant. Answer in the same language as the user's question.",
    )

def build_spec():
    return messages_spec(build_agent(), include_agents_md=True)
```
