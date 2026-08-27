# DeepAgents — subagents-dynamic template

Scaffolds a browser-based Pattern Lab for all six official Dynamic Subagents
patterns. One lifecycle-v2 project registers six independent LangGraph
assistants so learners can choose and validate each scenario without carrying
state or specialist roles across patterns.

The generated lab includes:

- Classify and act for mixed customer requests;
- Fan-out and synthesize for a complete route-security sweep;
- Adversarial verification for a high-confidence payment audit;
- Generate and filter for order-schema selection;
- Tournament for a five-candidate readability bracket;
- Loop until done for convergence-based dead-code discovery.

Each prepared user prompt expresses only a natural goal and includes the
`workflow` trigger. The UI marks Dynamic orchestration only after observing
the interpreter call, then uses real subagent streams for dispatch activity.
QuickJS and interpreter output remain available in a collapsed evidence panel;
the main surface does not expose fixture inventories or middleware allowlists.

The generated project pins `deepagents==0.7.8` and
`langchain-quickjs==0.3.5`. Its teaching fixtures are accessed through narrow,
read-only tools, and the implicit general-purpose subagent is disabled.

## Lifecycle

The generated project declares AgentSeek lifecycle version 2. `agentseek dev`
starts the six-assistant LangGraph API and the Vite Pattern Lab. Setup, tests,
and frontend installation are exposed through `agentseek task --list`.

## References

- [Deep Agents Dynamic Subagents](https://docs.langchain.com/oss/python/deepagents/dynamic-subagents)
- [Course Chapter 15 PR](https://github.com/datawhalechina/deepagents-in-action/pull/101)
- [Course Chapter 16 PR](https://github.com/datawhalechina/deepagents-in-action/pull/102)
