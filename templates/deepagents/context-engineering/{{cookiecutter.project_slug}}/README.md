# {{ cookiecutter.project_name }} Compare

中文 / English · Two independently selected models, one frozen set of inputs, inspectable Deep Agents context engineering.

## 启动 / Start

```bash
uv sync --frozen
uv run --frozen python -m {{ cookiecutter.project_slug }}.setup
uv run --frozen python -m {{ cookiecutter.project_slug }}.server
```

Open `http://127.0.0.1:{{ cookiecutter.port }}`. AgentSeek users may run `agentseek task sync`, `agentseek task setup`, then `agentseek dev`. One FastAPI process serves both the API and static browser UI. Markdown rendering uses the bundled local `markdown-it==15.0.2`; no Node build or runtime CDN is required. `frontend/package.json` is metadata only.

Setup asks for the protocol, its base URL, its hidden key and the hidden Querit key. It preserves the other protocol's configuration and custom variables. Secrets are stored only in local `.env` with owner-only permissions, ignored by Git and never returned to the browser. Restart after changing configuration. There are no model presets: choose both model IDs in the UI for each comparison.

终端配置仅要求所选模型协议的密钥与 `QUERIT_API_KEY`。输入不回显，不进入 shell 历史。离线示例不需要任何密钥，也不会请求模型或搜索服务。启动服务或执行 setup 不会发起推理请求；读取模型目录由用户点击“刷新可用模型”触发。

## 通用连接 / Generic connections

| Protocol | Selected key | Canonical base | Accepted alias |
| --- | --- | --- | --- |
| `AGENTSEEK_MODEL_PROVIDER=openai` | `OPENAI_API_KEY` | `OPENAI_BASE_URL` | `OPENAI_API_BASE` |
| `AGENTSEEK_MODEL_PROVIDER=anthropic` | `ANTHROPIC_API_KEY` | `ANTHROPIC_BASE_URL` | `ANTHROPIC_API_URL` |

Canonical values take precedence over aliases. Defaults are the official provider bases `https://api.openai.com/v1` and `https://api.anthropic.com`. The UI shows the configured inference and model-catalog endpoints directly. `ChatOpenAI` uses Chat Completions (`use_responses_api=False`); `ChatAnthropic` uses the Anthropic Messages protocol. Compatible HTTPS endpoints and HTTP loopback endpoints (`localhost`, `127.0.0.1`, `[::1]`) can be configured with matching credentials and callable model IDs. For a local server that does not authenticate, use a non-secret placeholder key such as `local`; the SDK requires a non-empty key.

`AGENTSEEK_MODELS_BASE_URL` optionally separates the model directory base from the inference base. Leave it blank to reuse the selected protocol's inference base. The server calls the selected SDK's `models.list()` with the same selected key, a 15-second overall timeout and no automatic retry. Pagination is bounded to 10 pages / approximately 500 IDs; a partial list is labeled as such. The directory is not filtered by guessed capabilities: it can include embedding, OCR or models unavailable to the account. A catalog ID does not guarantee chat or tool-call support.

目录不存在、404、未授权或临时不可用时，界面会诚实说明，并继续支持手填精确 ID；没有截图列表作为隐藏替代，也不会自动改写推理端点。点击“刷新可用模型”才读取目录，不在后台轮询。

For a local OpenAI-compatible server, for example:

```dotenv
AGENTSEEK_MODEL_PROVIDER=openai
OPENAI_BASE_URL=http://127.0.0.1:8000/v1
OPENAI_API_KEY=local
```

For another compatible gateway, set its documented base and account key. The same rules apply to `ANTHROPIC_BASE_URL` when selecting the Anthropic protocol. Model catalog and inference routes remain independently configurable.

## 比较流程 / Compare workflow

1. Enter one shared task and optionally paste source material. Choose 中文 or English for both UI and requested output language.
2. Click **刷新可用模型 / Refresh available models**, or manually enter exact IDs on the left and right. No ID is preselected.
3. Each side has its own optional reasoning level, initially blank / provider default. Blank omits an explicit override; the same default label does not mean different models have equal actual reasoning budgets. Different explicit levels compare both models and parameters, which the UI flags. Supported levels depend on the actual model/service. The parser allows `minimal`, `low`, `medium`, `high`, `max`, `none`, `xhigh`; the UI exposes the common `low`, `medium`, `high`, `max` choices. Anthropic requests never receive this OpenAI parameter. Changing a model requires reviewing its reasoning choice.
4. Click **开始比较 / Compare models**. The server freezes the task, full material, language and approved-memory snapshot once. It runs left, then right with the same budgets and context middleware. Each graph has independent messages and file state. A left-side error does not stop the right side; a completed right-side result is retained if the other side fails.
5. Inspect each side's answer, actual tool events, files, model/search calls, provider-reported tokens and elapsed time. File navigation opens the report by default when available; expand any trace event to inspect its exact recorded fields. A final `finish_reason=length` or `stop_reason=max_tokens` marks that side `incomplete`; partial evidence remains visible. Empty final messages do not fall back to older drafts.
6. After the pair finishes, change a side's model or reasoning level and click **重新执行 A / Rerun A** or **重新执行 B / Rerun B**. Only that side runs again using its current selection; the other side's result, files and trace stay unchanged. The original shared task, material, output language and approved memory remain frozen. Changed common task/material require a new comparison. Changing the UI language or saving memory does not change an existing snapshot. Offline pairs remain offline when rerun.
7. Click **导出比较 / Export comparison** to download `context-lab-compare-<short-id>.json`, including the original submitted inputs/candidate choices, shared hashes/policy, and each side's latest result/events/errors, candidate and run ID. A rerun replaces that side's displayed/exported attempt; the export is not an attempt history. The export contains user materials and approved memory when present, but no provider keys.
8. Edit a durable preference and click **批准并保存 / Approve and save**. A fresh comparison reads the new snapshot on both sides. A save during an active pair takes effect on the next pair; it cannot change the current pair's frozen memory.

推理档位默认不显式传参；两侧都显示“提供方默认”不代表实际推理预算相同。显式档位不同意味着同时比较模型与参数，界面会提示。单侧重跑使用本侧当前模型/档位，沿用原始共同输入与已批准记忆，只替换本侧结果；另一侧的回答、文件与轨迹不变。共同任务或材料改变后需开始新比较。每次执行都有新的 `run_id`。

比较快照仅保留在当前服务进程内，最多保留最近 16 组；重启服务或旧快照被淘汰后，需开始新比较。已展示的证据不会因此清空。 Snapshots are process-local and limited to the latest 16 comparisons. After a restart or eviction, start a new comparison; existing browser evidence remains available.

模型回答与 `.md` / `.markdown` 文件支持标题、表格、代码块和链接。原始 HTML 不执行，远程图片以链接显示；其他文件以纯文本显示。 Answers and Markdown files render headings, tables, code blocks and links with raw HTML disabled. Remote images appear as links; other files remain plain text.

两侧共享的是相同输入、批准记忆与上下文策略，不是模型行为或检索结果。它们各自决定搜索词与调用顺序，网络内容、缓存和时间也可能变化。因此这里是可检查的应用比较，不是受控性能排名；不要仅凭一次 Token 或耗时差异宣称模型优劣。默认顺序执行用于减少并发限流，也意味着两侧开始时间不同。

**离线示例 / Offline example** returns clearly labeled illustrative files and mechanisms for both sides without any model/search calls. It does not measure quality, cost, tokens or speed, and it does not assert the real harness ran. Every example path shown in its events can be inspected.

## 相同策略，独立状态 / Shared policy, independent state

| Policy applied independently to each side | Value |
| --- | --- |
| Output limit per model call (not per comparison) | 3,000 tokens |
| Querit search budget | 4 query attempts, 3 results each |
| Approximate summarization trigger | 6,000 tokens |
| Messages retained verbatim | latest 6 |
| Graph recursion limit | 32 |
| Model request timeout / transient retries | 60 seconds / 1 |
| Side execution timeout | 180 seconds |

- `StateBackend` gives each graph its own virtual filesystem, without host files or a shell. Shared pasted material is preserved in full at `/sources/user-material.md`; the initial task carries its path and a 300-character preview. This explicit source offload is distinct from native large-tool-result offloading.
- The original `/skills/research-brief/SKILL.md` supplies research procedure through Deep Agents' on-demand skill loading. `researcher` can isolate noisy research in a subagent. The model may choose not to delegate or load the skill; configuration alone is not evidence of execution.
- `langchain-querit==0.0.3` uses `langchain_websearch.WebSearchTool`. The per-side budget is shared by that side's main agent and subagents. Search errors mean unavailable evidence, not successful retrieval. `search_calls` counts attempts. Full tool results remain available to native offloading rather than being silently truncated.
- The real Deep Agents summarization middleware keeps originals recoverable under `/conversation_history/`. Large tool results can be preserved under `/large_tool_results/`. Short runs may trigger neither mechanism. Inspect state files and actual calls rather than inferring behavior from the capability strip.
- Approved memory is persisted separately at `.context-lab/memory.json`. The server snapshots it once per pair and seeds `/memories/AGENTS.md` in both graphs. Model writes to memory/skill files are denied. State/history from a completed graph is not automatically injected into the next comparison. Clear the memory textarea and approve-save to remove saved preferences.

Actual token values are displayed only when the provider returns them. They do not compute plan billing or guaranteed savings. Model events include main-agent, subagent and summarization calls. Errors/timeouts/cancellation can still incur provider usage; completed evidence is not replaced with illustrative success data.

## LangSmith 可选追踪 / Optional tracing

```dotenv
LANGSMITH_TRACING=false
LANGSMITH_API_KEY=
LANGSMITH_ENDPOINT=https://apac.api.smith.langchain.com
LANGSMITH_PROJECT={{ cookiecutter.project_slug }}
```

The default explicitly disables LangSmith tracing. If enabled with the appropriate key, each side's graph traces carry `compare_id`, a fresh `run_id` for every attempt, `side`, `model_id`, language, execution mode, a `rerun` flag and shared-input hashes. Provider/search keys are never trace metadata. Task, model and tool content can be part of an enabled trace, as with ordinary LangSmith tracing; use the project intended for that content. Changing tracing configuration requires restarting the server.

## API

`GET /api/config` returns protocol, inference/catalog bases, key-readiness booleans, approved memory, policy and tracing status, never keys. `GET /api/models` returns real SDK IDs or `{available:false, models:[], manual_allowed:true, code:...}`. `PUT /api/memory` requires `{text, approved:true}`.

`POST /api/compare` accepts:

```json
{
  "execution": "live",
  "language": "en",
  "prompt": "Research the same question and write /reports/brief.md with source links.",
  "material": "Optional shared full source material",
  "left": {"model_id": "your-left-model", "reasoning_effort": ""},
  "right": {"model_id": "your-right-model", "reasoning_effort": "low"}
}
```

The response is newline-delimited JSON: `compare_start` with shared policy and SHA-256 hashes of the task, material and memory; `side_start`; side-specific `event`, `result` or `error`; `side_end` with its outcome; then `compare_end` with per-side outcomes. Every packet has `compare_id`; side packets also have `side=left|right` and the attempt's fresh `run_id`. Each final result includes its configured `model`, `provider`, `status`, `finish_reason`, actual metrics, state files, observed events and effective options. The app does not infer a provider alias's underlying model identity. The local HTTP surface enforces same-origin requests and loopback hostnames.

`POST /api/compare/{compare_id}/rerun/left` or `/rerun/right` accepts only the new candidate selection:

```json
{"model_id": "your-selected-model", "reasoning_effort": ""}
```

The server reuses its frozen snapshot; task, material, memory or language fields in a rerun body cannot replace it. The stream contains only that side's `side_start`, `event`/`result`/`error` and `side_end`, with the original `compare_id` and a new `run_id`. Only one pair or side can execute at a time (`409` when busy); a missing/evicted snapshot returns `404` and requires a new pair. 单侧重跑接口仅提交模型与档位，复用服务端快照；不会重跑另一侧。服务忙时返回 `409`，快照不存在时返回 `404`，需重新开始比较。

## 离线验证 / Offline tests

```bash
uv run --frozen --group test python -m pytest
```

Tests exercise the real Deep Agents harness using scripted local model/search adapters, including skills, delegated search, independent source files, denied memory writes, native recoverable summaries/offload and both protocols' truncation handling. SDK model discovery is tested without HTTP using fake SDK clients. Compare tests verify frozen memory/inputs, per-side options/metadata, independent reruns, fresh attempt IDs, snapshot expiry, busy/error isolation, UI evidence ownership and honest manual fallback. No test calls external models or Querit.

Sources: [Deep Agents context engineering article](https://www.langchain.com/blog/context-engineering-deep-agents-remember), [Deep Agents customization](https://docs.langchain.com/oss/python/deepagents/customization), [Querit integration](https://pypi.org/project/langchain-querit/). The shipped `uv.lock` pins the reviewed Deep Agents 0.7.8 runtime and supports renamed projects. After intentionally editing dependencies, run `uv lock` and repeat the offline tests. UI regression tests also run when Node is available; Node is not required to start the app.
