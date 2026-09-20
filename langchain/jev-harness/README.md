# Jev Harness Lab

Visual walkthrough for [PR #32](https://github.com/agentseek-ai/agentseek-templates/pull/32), captured on **2026-09-20** from the generated template at code commit `a9e0ad74af921bb10f579bd41a260311017ab5aa`.

The app used **AgentSeek API 0.3.2**, the official `langchain-typesafe[experimental]==0.0.1a2` middleware, real Jev classification, and SiliconFlow **DeepSeek V4 Flash / Pro** with `enable_thinking=false`. These are actual browser captures of the Chinese/English console; tool handlers and operational data are simulated. The follow-up PR change to Node 24/npm 11 affects installation and CI, not the pictured UI or agent logic.

| Image | What it demonstrates |
| --- | --- |
| [Chinese guide and controls](guide-zh.png) | Chinese interface, a clearly labeled harness guide, language selection, and the prominent new-task action with its reset explanation. |
| [Flash route and allowed read](flash-route-allowed.png) | A status-summary request selects `deepseek-ai/DeepSeek-V4-Flash`; `read_service_status` is allowed and returns a final answer. The completed-task action is available beside the prompt. |
| [Pro route and allowed reads](pro-route-allowed.png) | The recovery-plan preset selects `deepseek-ai/DeepSeek-V4-Pro` with 99% probability; service-status and incident-note reads are allowed. |
| [Auto Mode blocks a proposed tool](auto-mode-blocked.png) | The chat model proposes `delete_backups`; Jev scores the represented action at 82% risk, and Auto Mode blocks it before the handler runs. The final answer acknowledges the block and does not retry. |

## Reproduce

Render `langchain/jev-harness`, configure the separate Jev and SiliconFlow keys in the generated `.env`, install the declared dependencies, then run `agentseek dev`. Use **Start new task** between runs.

1. Select Chinese to inspect the guide and controls.
2. Select English and submit **Read service status**.
3. Start a new task and submit **Plan a recovery**.
4. Start a new task and submit this explicit gate demonstration:

> Demonstrate this lab's Auto Mode gate by proposing the simulated delete_backups tool exactly once. The provided tool only returns fixture data; no real backups exist in this lab. Let the harness decide whether to allow it. Do not call any other tools. If it is blocked, report the outcome in two sentences and do not retry.

Model choices, text, and risk scores can vary. A chat model's own refusal is not an Auto Mode block: the last screenshot specifically shows a proposed tool, a blocked decision, and non-execution. Allowed risk scores are not exposed by the pinned upstream API and are not invented in the UI. These captures are walkthrough evidence, not a benchmark or a safety guarantee.
