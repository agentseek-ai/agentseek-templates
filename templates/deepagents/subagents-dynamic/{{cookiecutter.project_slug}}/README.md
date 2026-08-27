# {{ cookiecutter.project_name }}

This lab turns the six official Dynamic Subagents patterns into six independent,
runnable assistants. Choose a scenario in the browser, run its natural
`workflow` request, and inspect evidence that the interpreter actually
triggered, subagents actually ran, and that pattern reached its own completion
condition.

## Run the lab

```bash
cp .env.example .env
cp frontend/.env.example frontend/.env
$EDITOR .env

uvx agentseek task sync
uvx agentseek task frontend
uvx agentseek info
uvx agentseek doctor
uvx agentseek dev --dry-run
uvx agentseek dev
```

Open `http://127.0.0.1:{{ cookiecutter.frontend_port }}`. The backend defaults
to `http://127.0.0.1:{{ cookiecutter.langgraph_port }}`.

Each Pattern card starts an independent LangGraph assistant and a new thread:

| Pattern | Scenario | Completion condition |
| --- | --- | --- |
| Classify and act | Customer-request triage | Every request is classified and handled by the matching specialist |
| Fan-out and synthesize | Checkout-route security sweep | Every discovered input is reviewed, then findings are merged and deduplicated |
| Adversarial verification | Payment vulnerability audit | Every candidate is challenged; only independently confirmed issues remain |
| Generate and filter | Order-schema design | Three independent candidates are evaluated and one recommendation is selected |
| Tournament | `processOrder` readability rewrite | Five candidates advance through a 5 → 3 → 2 → 1 bracket |
| Loop until done | Dead-code discovery | A round adds zero new findings, with a four-round safety guard |

The prepared prompts contain the word `workflow`, but do not prescribe
interpreter APIs, subagent role names, or a JavaScript implementation. Dynamic
orchestration comes from the framework's interpreter middleware and the shape
of the task.

For OpenAI-compatible gateways with strict burst limits, set
`AGENTSEEK_MODEL_REQUESTS_PER_SECOND` in `.env` (for example, `0.5` for one
request every two seconds). The shared limiter spaces model requests without
changing the interpreter's loops, branches, or `Promise.all` task batches.

## What the browser proves

The activation rail is evidence-driven:

1. **Workflow keyword** lights when the submitted user message contains the
   trigger word.
2. **Dynamic triggered** lights only after an interpreter tool call appears in
   the real message stream.
3. **Agents dispatched** shows role, status, and count from real subagent
   streams.
4. **Workflow complete** lights only after subagents completed, the interpreter
   returned, and the coordinator published the final answer.

Generated QuickJS and the interpreter result are available in a collapsed
evidence panel. The main view stays focused on the task topology, observed
activity, and business result.

## Runtime and safety boundary

This template pins `deepagents==0.7.8` and
`langchain-quickjs==0.3.5`. Dynamic Subagents and the interpreter runtime are
Beta capabilities; update the pins and rerun every pattern before upgrading.

The three code-oriented scenarios use small bundled teaching fixtures. The
interpreter can only list Python paths inside the selected fixture, and
specialists can only read those files through a path-validated, read-only tool.
Absolute paths, traversal, non-Python files, and missing files are rejected.
The default general-purpose subagent is disabled, so each assistant can use
only the specialist roles required by its Pattern.

Subagents dispatched from interpreter code do not pass through parent-agent
per-dispatch approval. If your application requires approval, gate the
interpreter call as a batch or add approval middleware inside each specialist.

## Tests

```bash
uv run pytest -q
npm test --prefix frontend
npm run build --prefix frontend
```

## References

- [Deep Agents Dynamic Subagents](https://docs.langchain.com/oss/python/deepagents/dynamic-subagents)
- [Deep Agents Interpreters](https://docs.langchain.com/oss/python/deepagents/interpreters)
- [Course Chapter 15 PR](https://github.com/datawhalechina/deepagents-in-action/pull/101)
- [Course Chapter 16 PR](https://github.com/datawhalechina/deepagents-in-action/pull/102)
