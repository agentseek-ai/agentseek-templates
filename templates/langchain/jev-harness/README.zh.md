# langchain/jev-harness

[English](README.md) | 简体中文

基于 LangChain `create_agent` 的实验模板，演示
[Building a Harness with Jev](https://www.langchain.com/blog/building-a-harness-with-jev)
中的两个决策点：运行前选择对话模型，执行工具前检查风险与授权。
前端展示实际选择、候选概率、路由 confidence、工具判断及最终解释。

默认运行时为 **`agentseek-api[embedded]==0.3.2`**，前端支持中文和英文。
默认决策模型为 **SiliconFlow SemIf**，另可选择 Kev-4B、DiffusionGemma 和官方 Jev；同一次运行的路由与工具检查使用同一个所选决策模型。
候选对话模型默认是 DeepSeek V4 Flash / Pro，也可替换成其他 OpenAI 兼容模型。

「上下文对照实验」在不同授权上下文中使用固定的重启、备份清理等提案，实际判定由上游
Auto Mode 中间件给出。风险分数来自同一次真实分类，无论放行或拦截都会保留原始返回值。
Noul 没有独立的 confidence 字段，路由的 Choice confidence 单独展示。

「Arena · 双模型 PK」让两个不同决策模型并发处理同一初始任务和提案序列，左右固定展示，
会话相互独立；一侧失败不会影响另一侧。概率高低不能直接作为胜负或质量排名。
后端启动命令已配置 `--no-browser`。

DiffusionGemma 曾出现 HTTP 503；2026-09-26 中英文及并发复测的 36 次真实分类请求全部成功，
因此恢复选项。生成项目的说明保留详细记录；短期样本不代表长期可用性或判断质量保证。

## 从本仓库生成项目

```bash
uv run cookiecutter templates/langchain/jev-harness --no-input --output-dir /tmp/jev-render
cd /tmp/jev-render/jev_harness_lab
cp .env.example .env
uv sync --group test
npm install --prefix frontend
```

需要 Python 3.12 或 3.13、Node.js 24 及以上、npm 11 及以上。
默认配置只需在 `.env` 中填写硅基流动中国站的 `OPENAI_API_KEY`。
使用官方 Jev 时另填 `TYPESAFE_API_KEY`；对话使用其他服务商时，硅基流动决策密钥需要单独填入
`SILICONFLOW_API_KEY`。不要把密钥放入前端环境文件。

生成项目的 [中文版使用说明]({{cookiecutter.project_slug}}/README.zh.md) 包含完整配置、
启动命令、场景说明、Arena、原始分数含义和验证方法。填好配置后运行 `agentseek dev`，
手动打开前端地址；不要给 AgentSeek core 的这个命令追加不支持的 `--no-browser`。

## 模板参数

| 参数 | 默认值 | 用途 |
| --- | --- | --- |
| `project_name` | Jev Harness Lab | 页面标题 |
| `project_slug` | 根据名称生成 | 项目目录和 Python 包名 |
| `author` | Your Name | 作者 |
| `fast_model` | deepseek-ai/DeepSeek-V4-Flash | 简单任务候选模型 |
| `powerful_model` | deepseek-ai/DeepSeek-V4-Pro | 复杂推理候选模型 |
| `chat_api_base` | https://api.siliconflow.cn/v1 | 对话接口 |
| `langgraph_port` | 2024 | AgentSeek API 端口 |
| `frontend_port` | 5176 | 前端端口 |

两个候选对话模型共用对话密钥和接口。生成后可在 `.env` 修改模型 ID，必须使用服务商实际支持的型号。
切换服务商时需要一起修改密钥、接口、模型 ID 和附加 JSON 参数；`.env.example` 提供中英文说明。
路由标签不代表已经验证的质量、延迟或价格排名。

## 实现边界与资料

模板固定使用 `langchain-typesafe[experimental]==0.0.1a2`、`langchain==1.3.15`、
`langgraph==1.2.11`。中间件为实验接口，构造适配器复用固定版本的私有配置类型；升级后需重新验证。
模型路由读取最新用户消息并在一次运行内保留选择；工具检查使用最近 30 条消息，风险概率达到 0.5
时拦截。所有暴露的工具都在受检查列表中，分类错误会传播，不会静默放行或切换模型。

所有工具只返回模拟数据，没有文件、Shell、网络或真实生产操作。
Auto Mode 不提供人工审批，也不是沙箱或风险判断正确性的保证。
实验策略按所代表的真实操作判断，因此会把删除生产备份视为高风险。

- [SiliconFlow System One API](https://api-docs.siliconflow.cn/docs/api/systemone-post)：Alpha 分类接口与托管模型。
- [LangChain 文章](https://www.langchain.com/blog/building-a-harness-with-jev)及 [TypeSafe 集成](https://docs.langchain.com/oss/python/integrations/providers/typesafe)。
- [TypeSafe 快速开始](https://docs.typesafe.ai/introduction/quickstart)、[状态](https://docs.typesafe.ai/concepts/state)、[confidence](https://docs.typesafe.ai/confidence)。
- [固定版本集成包](https://pypi.org/project/langchain-typesafe/0.0.1a2/)：实现与行为核查依据。
