# langchain/jev-harness

A LangChain `create_agent` lab for the two harness decisions in
[Building a Harness with Jev](https://www.langchain.com/blog/building-a-harness-with-jev):
select a chat model before the run, and evaluate proposed tools before execution.
The generated browser console shows the selected model, route probabilities,
confidence, tool outcomes, and final response. A context-experiment mode compares
fixed restart/cleanup proposals under different authorization contexts. The
console uses the actual upstream Auto Mode gate and reports risk probability for allowed and
blocked calls. Noul does not return a separate confidence value.

The default runtime is `agentseek-api[embedded]==0.3.2`. The console supports
Chinese and English, with a persisted language switch and localized scenarios.

The template uses the official `ModelRouterMiddleware` and `AutoModeMiddleware`
from `langchain-typesafe[experimental]==0.0.1a2`, with `langchain==1.3.15` and
`langgraph==1.2.11`. The middleware is experimental. Revalidate the generated
tests and live behavior when upgrading. Jev is a classifier; a separate
OpenAI-compatible chat model generates the answer. Defaults are SiliconFlow's
DeepSeek V4 Flash and Pro, with thinking disabled for this tool-calling demo.

## Run locally from this catalog checkout

```bash
uv run cookiecutter templates/langchain/jev-harness --no-input --output-dir /tmp/jev-render
cd /tmp/jev-render/jev_harness_lab
cp .env.example .env
uv sync --group test
npm install --prefix frontend
```

Fill `TYPESAFE_API_KEY` and the chat-provider settings in `.env` before any live
test. Follow the generated README for lifecycle commands, offline validation,
the explicit live smoke test, and the context experiments. Never put
provider credentials in the frontend environment.

## Inputs

| Input | Default | Purpose |
| --- | --- | --- |
| `project_name` | Jev Harness Lab | App title |
| `project_slug` | Derived from name | Python package and directory |
| `author` | Your Name | Project author |
| `fast_model` | deepseek-ai/DeepSeek-V4-Flash | Straightforward tasks |
| `powerful_model` | deepseek-ai/DeepSeek-V4-Pro | Complex reasoning |
| `chat_api_base` | https://api.siliconflow.cn/v1 | Chat Completions endpoint |
| `langgraph_port` | 2024 | AgentSeek API port |
| `frontend_port` | 5176 | Vite console port |

The routes share one chat-provider key and base URL. Model IDs can be
overridden after rendering; use IDs supported by your provider. No claim about
relative quality, latency, or cost is inferred from the route labels.
The generated `.env.example` explains each setting in English and Chinese,
including the key, endpoint, model IDs, and provider-specific JSON options to
change when using your own provider.

## Reviewed sources and boundaries

- [LangChain article](https://www.langchain.com/blog/building-a-harness-with-jev)
  motivates the two decision points; the implementation follows the package API.
- [LangChain TypeSafe integration](https://docs.langchain.com/oss/python/integrations/providers/typesafe)
  documents the experimental extra, per-run routing, and pre-execution checks.
- [TypeSafe quickstart](https://docs.typesafe.ai/introduction/quickstart) describes
  the API endpoint, key, `jev-latest`, and typed answers.
- [State](https://docs.typesafe.ai/concepts/state) explains text/JSON inputs and
  why untrusted incident content belongs in state rather than instructions.
- [Confidence](https://docs.typesafe.ai/confidence) distinguishes route confidence
  from option probability. A Noul answer has a probability, not confidence.
- [Released integration source](https://pypi.org/project/langchain-typesafe/0.0.1a2/)
  was inspected for hook behavior: latest human message only, route retained
  throughout the run, fixed risk threshold of 0.5, last 30 messages for tool
  context, unlisted tools bypassed, and classifier errors propagated.

All exposed tools are guarded. Operations tools are fixtures with no filesystem,
shell, network, or production side effects. Auto Mode refuses tools; it does not
ask a person for approval and is not a sandbox or a guarantee of correct risk
classification. The lab's explicit policy treats represented backup deletion as
risky even though the actual handler is simulated.
