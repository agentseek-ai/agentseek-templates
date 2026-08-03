# LangChain Relay Observability

LangChain `create_agent` + CopilotKit + Bub/AG-UI with NeMo Relay, bounded Tavily research tools, Phoenix, and OceanBase SeekDB.

This template is based on `langchain/default`; it preserves the default middleware and frontend lifecycle. Relay is the only observability chain. Verified dependencies: `nemo-relay==0.6.0`, `tavily-python==0.7.27`, and `markdownify==1.2.3`.

Create it with Cookiecutter, copy `.env.example` to `.env`, set `BUB_API_KEY` and the required `TAVILY_API_KEY`, then run `agentseek dev`. The first start downloads Python/Node dependencies and Phoenix/SeekDB images and may take several minutes.

See the generated project's README for the full architecture, privacy, troubleshooting, and persistence guide.
