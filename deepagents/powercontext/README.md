# Deep Agents PowerContext

Visual evidence for [PR #29](https://github.com/agentseek-ai/agentseek-templates/pull/29), captured on 2026-09-19 from code commit `a630f1f1682a1a03bf9e69935a70660c1c4df725`.

The template ran with PowerContext 1.0.0 on embedded seekdb and SiliconFlow `deepseek-ai/DeepSeek-V4-Flash`. The recall comparison asked the same question in two fresh threads after restarting PowerContext. These are actual browser captures and real model responses.

| Image | What it shows |
| --- | --- |
| [Saved project memory](memory-saved.png) | The explicit Project Phoenix save and returned entry version |
| [Recall enabled](recall-on.png) | The answer recovers the four saved release constraints and treats them as historical evidence |
| [Recall disabled](recall-off.png) | The independent answer marks project-specific decisions as unknown |

The PR description contains the validation details. These images demonstrate the tested configuration; they are not a performance benchmark.
