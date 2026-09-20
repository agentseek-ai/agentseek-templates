# {{ cookiecutter.project_name }}

Inspect two decisions around a LangChain agent loop: **which model should run**,
and **whether a proposed tool should execute**. Jev makes typed classifications;
the selected chat model generates the answer. The operations tools return fixed
fixtures and never access real services or backups.

The default runtime is **AgentSeek API 0.3.2** (`agentseek-api[embedded]==0.3.2`).
Use **中文 / English** in the console to switch languages. The choice is saved
locally; changing language preserves custom and already-submitted requests.
Preset prompts follow the selected language. Tool payloads remain inspectable
in their original form, and the chat model is asked to answer in your language.

## Setup: fill your keys before live testing

Use Python 3.12 or 3.13, Node.js 24 or newer, and npm 11 or newer.

```bash
cp .env.example .env
uv sync --group test
npm install --prefix frontend
```

Open `.env` locally. For the default **SiliconFlow DeepSeek V4 Flash/Pro** setup,
fill the two keys; the endpoint and model IDs are already configured:

| Setting | What you supply or change / 需要填写或修改的内容 |
| --- | --- |
| `TYPESAFE_API_KEY` | Your Jev key from the [TypeSafe console](https://console.typesafe.ai). / Jev 分类服务密钥。 |
| `OPENAI_API_KEY` | Your **SiliconFlow** key, shared by both chat models. / **硅基流动**密钥，两个对话模型共用；不是 Jev Key。 |
| `OPENAI_API_BASE` | `{{ cookiecutter.chat_api_base }}`; replace with your provider's Chat Completions base URL. / 更换服务商时改为其兼容接口地址。 |
| `JEV_FAST_MODEL` | `{{ cookiecutter.fast_model }}`; a model your account can call for simple tasks. / 简单任务模型，须使用账号支持的完整 ID。 |
| `JEV_POWERFUL_MODEL` | `{{ cookiecutter.powerful_model }}`; a model for complex tasks. / 复杂任务模型，须使用账号支持的完整 ID。 |
| `CHAT_MODEL_EXTRA_BODY` | `'{"enable_thinking":false}'` for SiliconFlow; use `'{}'` when another provider does not support this option. / SiliconFlow 默认关闭思考模式；其他服务商不支持此参数时设为 `'{}'`。 |

To use another OpenAI-compatible provider, change **the chat key, base URL, both
model IDs, and provider options together**. Keep Jev's separate configuration.
Restart the backend after editing `.env`. This demo uses non-thinking Chat
Completions: enabling provider-specific reasoning may require an adapter that
preserves `reasoning_content` through tool calls.

中文：默认使用硅基流动 DeepSeek V4 Flash / Pro，只需填写两个密钥。更换自己的服务商时，
请同时修改 **对话模型密钥、接口地址、两个模型 ID 和服务商参数**，Jev 配置保持独立。
修改 `.env` 后重启后端。本示例默认关闭思考模式；若启用服务商特有的推理模式，
需先适配工具调用过程中的 `reasoning_content` 传递。

Both routes share the chat provider. Jev uses `TYPESAFE_BASE_URL` (default
`https://api.typesafe.ai`) and the upstream `jev-latest` classifier model.
The API keys stay on the server. `frontend/.env` accepts only the public
`VITE_LANGGRAPH_API_URL`, never keys. `.env` is ignored by Git. Live runs send
requests and recent tool context to TypeSafe; use only synthetic teaching data.
LangSmith tracing is off by default and can be enabled in the server environment.

The middleware APIs are experimental. This project pins
`langchain-typesafe[experimental]==0.0.1a2`, `langchain==1.3.15`, and
`langgraph==1.2.11` to the tested contract.

## Validate offline

```bash
uv run --group test pytest
npm test --prefix frontend
npm run build --prefix frontend
```

These tests use scripted chat models and local HTTP mock transports, exercising
the real Jev classifier and middleware code without calling external providers.
They verify per-run routing, follow-up rerouting, sync and async tool checks,
the 0.5 boundary, concurrent tool decisions, and failures before execution.
Passing offline tests does not establish live classification quality.

## Start the console

After filling `.env`, use the installed AgentSeek CLI:

```bash
agentseek info
agentseek task --list
agentseek doctor
agentseek dev
```

The browser console is at http://127.0.0.1:{{ cookiecutter.frontend_port }}.
The AgentSeek API is at http://127.0.0.1:{{ cookiecutter.langgraph_port }}.
Without the CLI, run these in two terminals from this project:

```bash
uv run agentseek-api dev --port {{ cookiecutter.langgraph_port }}
```

```bash
npm run dev --prefix frontend
```

`agentseek doctor` reports missing provider keys until you fill them. No live
request is sent just by importing the Python agent module.

## Try the four scenarios

| Scenario | What to inspect |
| --- | --- |
| Read service status | A simple request is a candidate for the fast route; the read tool should be allowed. |
| Plan a recovery | Complex analysis is a candidate for the powerful route. Inspect the probabilities and actual selected model. |
| Request a risky action | If the chat model proposes deletion, Auto Mode should block it before the handler runs. |
| Inspect an untrusted note | The agent reads injected instructions as data. It may ignore them itself; a missing deletion call is not proof of an Auto Mode block. |

Click **Start new task / 开始新任务** between tasks. This clears the current view
and opens a fresh conversation, with the cursor in the task field. The button
is available in the header and below a submitted task once the run finishes.
The **How the harness works** guide explains the sequence; it is not live progress.
The console starts a fresh conversation for
each run and shows only that run's evidence. Model choices are live judgments,
not fixed expected outputs. The selected route stays fixed through tool loops;
the middleware reclassifies the latest human message on a follow-up run.

Routing confidence is a statistic of the probability distribution, not the
chosen option's probability. Auto Mode uses a Noul risk probability: **0.5 or
higher blocks**, lower permits execution. Classifier errors stop the run with
no fallback execution. The console displays risk probability for blocked calls;
the pinned upstream API does not expose it for allowed calls, so those show
“Score not exposed.” All exposed tools are explicitly in the guarded list.

## Run the explicit live smoke test

Only after saving your keys:

```bash
agentseek task live-smoke
# Equivalent:
uv run python -m {{ cookiecutter.project_slug }}.live_smoke
```

This sends real paid Jev/chat requests. It exercises two complete agent runs,
prints their route evidence, then sends fixed read/delete proposals through
the real Auto Mode middleware. Fixed proposals make the gate observable even
when the chat model refuses a deletion before proposing it. The script fails if
the gate differs from the teaching expectation. It prints evidence, never keys.
The default offline test commands and CI do not invoke this script.

## Code map

- `src/{{ cookiecutter.project_slug }}/agent.py`: model bindings, route criteria,
  risk policy, six-call limit, and agent factory.
- `middleware.py`: reporting only; upstream middleware owns allow/block decisions.
- `tools.py`: simulated service status, untrusted incident note, and deletion.
- `live_smoke.py`: explicit real-provider verification.
- `frontend/src/App.tsx`: the decision console.
- `.agentseek/lifecycle.toml`: lifecycle v2 services, settings, checks, and tasks.

Auto Mode is a refusal gate, not a human approval workflow or a security
sandbox. Add separate human-in-the-loop controls before adapting this lesson
to real mutations. The lab makes no benchmark or production safety claims.

## Sources

[Building a Harness with Jev](https://www.langchain.com/blog/building-a-harness-with-jev),
[LangChain integration](https://docs.langchain.com/oss/python/integrations/providers/typesafe),
[TypeSafe quickstart](https://docs.typesafe.ai/introduction/quickstart),
[state](https://docs.typesafe.ai/concepts/state), and
[confidence](https://docs.typesafe.ai/confidence).
For chat-provider configuration, see the [SiliconFlow Chat Completions API](https://docs.siliconflow.cn/docs/api/chat-completions-post)
and [model release notes](https://docs.siliconflow.cn/docs/release-notes/overview).
