# LangChain Relay Observability Template Design

## Goal

Add `templates/langchain/relay-observability` as an independent lifecycle-v2 Cookiecutter template based only on `langchain/default`, with NeMo Relay as the sole tracing chain, bounded Tavily research tools, Phoenix visualization, and OceanBase SeekDB persistence.

## Architecture

The generated app keeps `create_agent`, AgentSeek `messages_spec`, Bub/AG-UI, CopilotKit middleware, context normalization, structured output handling, frontend, and Compose lifecycle from `langchain/default`. A Relay adapter owns configuration and lifecycle. It exports raw ATOF JSONL locally and OpenInference over OTLP to Phoenix when enabled; the old LangChain auto-instrumentor is removed from the new template.

Research tools are ordinary LangChain tools: `tavily_search` discovers up to three results and safely fetches bounded Markdown content, while `think_tool` records a short action-oriented summary without exposing hidden reasoning. Tool errors are returned as bounded user-visible tool results rather than aborting the whole search.

## Configuration and data flow

Defaults are `RELAY_ENABLED=true`, `RELAY_ATOF_ENABLED=true`, and `RELAY_PHOENIX_ENABLED=true`. ATOF writes to `.nemo-relay/atof/events.jsonl`; OTLP HTTP targets `http://phoenix:6006/v1/traces`; Phoenix uses `mysql://root@seekdb:2881/phoenix`; SeekDB data is mounted at `.seekdb-data`; Phoenix data is mounted at `.phoenix-data`. Relay-disabled mode creates no middleware, callback, exporter, or scope. Phoenix-disabled mode leaves ATOF export independent.

The exact Relay integration and exporter APIs will be taken only from the dependency version resolved by `uv` and its installed source/type documentation. The implementation will use the actual `messages_spec` invocation boundary to preserve one request-scoped root trace per request, with nested LLM and Tool spans.

## Testing

Template rendering tests verify lifecycle v2, no Jinja residue, registry membership, and generated file structure. Generated Python tests cover Relay disabled, ATOF-only, default dual export, Phoenix exporter suppression, missing Tavily key, bounded/error-tolerant search output, preserved default middleware, and absence of the old instrumentor. Optional integration tests run only when Docker, network, model credentials, and Tavily credentials are available.

## Constraints

- Never modify `templates/langchain/default`.
- Do not import DeepAgents runtime or sub-agent orchestration.
- Do not send ATOF/ATIF directly to Phoenix.
- Do not commit credentials or sensitive fetched content.
- Pin the resolved Relay dependency and preserve the reviewed AgentSeek commit.
