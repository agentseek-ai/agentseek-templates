# Context Lab Compare / 上下文工程对照实验台

Self-contained bilingual Deep Agents application for comparing two user-selected models with the same task, material, output language, approved-memory snapshot and context policy. Each side runs an independent graph and exposes its own answer, actual events, files, usage and status.

服务端使用所选 OpenAI / Anthropic SDK 的 `models.list` 读取真实目录，也支持手填精确模型 ID。目录与推理端点可分别配置；读取失败不会伪造列表或替换推理路径。两侧默认顺序执行，一侧失败仍保留另一侧结果。离线示例明确不是性能测试。

The generated project serves a static browser UI from one local FastAPI process, with no Node build or separate database. It includes `langchain-querit`, approved persistent memory, optional LangSmith tracing and lifecycle version 2. See its README for setup, Compare API, context mechanisms and offline tests.
