# LangChain Relay Observability

LangChain `create_agent` + CopilotKit + Bub/AG-UI with NeMo Relay, bounded Tavily research tools, Phoenix, and OceanBase SeekDB.

## Why this template promotes NeMo Relay

An agent can return the right final answer while still being difficult to operate: a tool may have been called with the wrong arguments, a model may have taken an unexpected branch, or latency and token usage may have increased without an obvious error. NeMo Relay provides the observability layer that turns those hidden agent steps into structured events and traces.

Relay is not another chat UI and it is not Phoenix. It runs with the application, instruments agent execution, and can send the same run to multiple sinks. This template enables two sinks:

- ATOF JSONL: a local, append-only audit/debug archive for inspecting the raw event stream.
- OpenInference over OTLP: a standard trace export for Phoenix, where spans can be searched and visualized. OpenInference is an AI-oriented span format; OTLP is the OpenTelemetry protocol used to transport it.

Phoenix is an AI observability and trace analysis platform. It does not execute the Agent. Phoenix receives OpenInference traces over OTLP, stores them for the local stack, and displays and analyzes Agent, LLM, Tool, and related spans. A span is one timed unit of work inside a trace, such as a model call or tool call. Phoenix helps developers inspect latency, errors, inputs, outputs, token usage, and parent-child execution relationships.

The roles are:

```text
NeMo Relay = runtime instrumentation and event export
Phoenix     = trace ingestion, storage, visualization, and analysis
```

The relationship and data flow are:

```text
LangChain Agent
      ↓
NeMo Relay execution scopes and lifecycle events
      ├─ ATOF JSONL → local raw event and audit archive
      └─ OpenInference over OTLP → Phoenix → OceanBase SeekDB
```

ATOF JSONL is the local raw event and audit path. OpenInference over OTLP is the trace export path. Phoenix is the developer-facing analysis UI and trace backend, while OceanBase SeekDB provides persistence for the local Phoenix stack.

## How instrumentation works

Instrumentation means observing structured execution boundaries, not merely printing application logs. The LangChain integration attaches Agent, Tool, and LLM call boundaries to Relay execution scopes:

```text
LangChain Agent
      ↓
Relay execution scope
      ↓
Tool / LLM / child-agent boundary
      ↓
start and end lifecycle events
      ↓
duration, status, input, output, metadata, and parent-child context
```

Relay can emit structured lifecycle events containing start and end times, duration, status, inputs and outputs, captured tool arguments and results, model metadata, token usage when available, parent-child relationships, and error information. Instrumentation is not ordinary application logging: it records what execution boundary ran, how it was related to other work, and how it completed.

With the provided LangChain integration, common Agent, Tool, and LLM boundaries are instrumented through Relay middleware and callback integration, so developers do not need to add ad hoc logging to every call. Custom Agent or Tool implementations may require Relay-managed helpers, explicit scopes, or manual lifecycle APIs, depending on how they are integrated.

In this template, `NemoRelayMiddleware()` is attached to the demo agents, while a request-scoped `NemoRelayCallbackHandler()` is added to the LangChain configuration. Together they connect LangChain lifecycle callbacks and execution boundaries to Relay scopes and its configured sinks.

### Observability architecture

![AI Agent observability data flow](./assets/ai-agent-observability-architecture.png)

### NeMo Relay runtime role

![NeMo Relay runtime control plane and lifecycle event hub](./assets/nemo-relay-runtime-control-plane.png)

Use Relay when you need consistent visibility across model calls, tool calls, middleware, and multi-agent steps; use Phoenix to inspect that data during development and operations. Keeping these roles separate also lets you retain a local raw archive without running Phoenix, or replace the trace backend later without rewriting the agent.

### Beginner glossary

- **Lifecycle event:** a structured record such as “tool started” or “tool ended,” including timing and context.
- **Instrumentation:** code that observes and records execution boundaries.
- **Trace:** the complete journey of one request or agent run.
- **Span:** one timed operation within a trace, connected to its parent and children.
- **OpenInference:** a convention for describing AI operations such as Agents, LLMs, and Tools.
- **OpenTelemetry:** the broader observability framework used by OpenInference integrations.
- **OTLP:** OpenTelemetry Protocol, which transports trace data to a backend such as Phoenix.
- **Trace backend:** the service that receives, stores, queries, and presents traces; Phoenix is the backend and UI in this local stack.

This template is based on `langchain/default`; it preserves the default middleware and frontend lifecycle. Relay is the only observability chain. Verified dependencies: `nemo-relay==0.6.0`, `tavily-python==0.7.27`, and `markdownify==1.2.3`.

Create it with Cookiecutter, copy `.env.example` to `.env`, set `BUB_API_KEY` and the required `TAVILY_API_KEY`, then run `agentseek dev`. The first start downloads Python/Node dependencies and Phoenix/SeekDB images and may take several minutes.

See the generated project's README for the full architecture, privacy, troubleshooting, and persistence guide.
