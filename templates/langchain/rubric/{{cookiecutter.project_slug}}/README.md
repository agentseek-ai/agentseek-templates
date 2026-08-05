# {{ cookiecutter.project_name }}

Learn how a LangChain agent revises a candidate against a rubric, records
candidate-bound Evidence, and fails closed at the final Acceptance Gate.
Guided Demo needs no model key. Live Model reads provider settings only from
server variables.

## Quick tutorial: run the keyless learning path

From the generated project directory, run these commands in order:

```bash
cp .env.example .env
uvx agentseek task sync
uvx agentseek task frontend
uvx agentseek task rubric-smoke
uvx agentseek info
uvx agentseek doctor
uvx agentseek dev --dry-run
uvx agentseek dev
```

The lifecycle reads server settings from `.env`, so the first command creates
that file from the safe example. Guided Demo still needs no credential. The
first two tasks install the Python and frontend dependencies. The smoke then
proves the fixed Guided Demo can move from a failing candidate to an accepted
candidate without a provider credential. `agentseek info` prints the service
URLs. `doctor` checks the installed tools and generated paths. `dev --dry-run`
previews both development processes before `dev` starts them.

After `dev` starts, open the primary frontend URL printed by `agentseek info`.
Keep that terminal open; stop both development processes with `Ctrl-C`.

In the browser:

1. Keep **Guided Demo** selected and run the grading loop.
2. Inspect candidate v1 and its failing Evidence.
3. Follow the Grader feedback to candidate v2.
4. Confirm candidate v2 has passing Evidence.
5. Read the **Accepted** gate and its exact-candidate reason.

The Guided Demo task is fixed: implement `find_duplicates(values)` as valid
Python source. Its rubric and positive iteration cap are also fixed. This makes
candidate v1, Evidence, feedback, candidate v2, and acceptance reproducible.

## How to configure and run Live Model

Run `$EDITOR .env`. Set `AGENTSEEK_MODEL_PROVIDER`, `AGENTSEEK_MODEL`, and
`RUBRIC_GRADER_MODEL`, then fill exactly one provider-native credential/base
block:

- OpenAI: `OPENAI_API_KEY` and optional `OPENAI_API_BASE`.
- Anthropic: `ANTHROPIC_API_KEY` and optional `ANTHROPIC_API_URL`.
- Google: `GOOGLE_API_KEY` and optional `GOOGLE_API_BASE`.

Leave the other two provider blocks empty. These variables are server
configuration read by the LangGraph process; they are never browser
configuration and must not be added to `frontend/.env`. Restart
`uvx agentseek dev` after changing them.

Provider aliases are:

| Canonical provider | Accepted aliases |
| --- | --- |
| `openai` | `openai` |
| `anthropic` | `anthropic` |
| `google` | `google`, `google_genai`, `google-genai`, `gemini` |

Before a real run, preflight the Grader model against your endpoint. The same
model must support tool calling and structured output in combination.
An OpenAI-compatible endpoint name alone does not prove this compatibility.

Select **Live Model** after the server restarts. The task stays fixed. Edit only
the rubric and positive iteration cap, then Run. Every Run starts a fresh
LangGraph thread; the UI shows its server thread ID and keeps Guided and Live
reports isolated.

To study a fail-closed result, tighten one rubric criterion or lower the cap,
then Run on a fresh thread. Inspect `max_iterations_reached`, `failed`, or
`grader_error` rather than treating a non-accepted report as a partial success.

After changing the rubric runtime, rerun the keyless checks:

```bash
uv run python -m pytest -q
uv run python -m {{ cookiecutter.project_slug }}.smoke
npm test --prefix frontend
npm run build --prefix frontend
```

## Reference: runtime and report contracts

### Graphs and lifecycle tasks

| Name | Contract |
| --- | --- |
| `rubric-demo` | Lazy Guided Demo graph factory; no model key required. |
| `rubric-live` | Lazy provider-backed graph factory; server settings resolved only when invoked. |
| `sync` | Installs generated Python dependencies with `uv sync`. |
| `frontend` | Installs frontend dependencies with `npm install`. |
| `rubric-smoke` | Runs the rendered package's deterministic Evidence loop. |

### Rubric results

| Result | Meaning | Acceptance |
| --- | --- | --- |
| `satisfied` | Terminal Grader result. | Necessary, but accepted only with passing Evidence for the exact final candidate. |
| `needs_revision` | Intermediate loop result requesting another candidate. | Never a terminal acceptance result. |
| `max_iterations_reached` | Terminal cap reached before satisfaction. | Rejected. |
| `failed` | Terminal rubric run failure. | Rejected. |
| `grader_error` | Terminal sanitized Grader failure. | Rejected. |

The public Acceptance Gate requires terminal `satisfied` plus passing Evidence
for the exact current candidate. A `satisfied` checkpoint without matching,
passing final-candidate Evidence is still rejected as
`current_evidence_missing`.

Candidate identity is calculated from normalized source. Candidates over 3,500
normalized characters fail closed because the characterized middleware
truncates longer transcript messages. The test request, Evidence record, final
Checkpoint, and public report must all refer to the same candidate identity.

## Explanation: why observation cannot control acceptance

The generated agent uses the pinned `RubricMiddleware` as a generic LangChain
`AgentMiddleware` in `create_agent`. It deliberately does not call
`create_deep_agent`, which would add unrelated planning, filesystem, and
sub-agent concepts. The middleware is **Beta** and is characterized at
`deepagents==0.7.1`, `langchain==1.3.14`, and `langgraph==1.2.10`. Rerun the
characterization suite before changing those exact pins.

Callbacks and custom events drive sanitized server logs and the provisional UI
timeline only. The final Checkpoint plus the per-run Evidence ledger drive the
public report and Acceptance Gate. `on_evaluation` cannot accept, reject, or
terminate a run.

The Evidence runner uses a fixed child process, strips inherited environment
values, enforces a timeout and output cap, and restricts Python built-ins. This
profile is not a sandbox. It does not isolate filesystem, network, or system
calls and must not be treated as a production code-execution boundary.

The exact reviewed teaching source is
[DeepAgents in Action, Chapter 13](https://github.com/datawhalechina/deepagents-in-action/blob/6fcef2294bc1ae19e97054426c1355923b50493a/content/ch13-grading-rubrics.md).

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `doctor` reports missing `frontend/node_modules` | Run `uvx agentseek task frontend`, then rerun `doctor`. |
| Guided Demo asks for provider setup | Confirm the UI is in Guided Demo and restart the generated development processes. |
| Live Model reports missing configuration | Set the server variables in `.env`, then restart `uvx agentseek dev`. |
| The provider rejects Grader requests | Verify the alias and model IDs, then preflight combined tool calling and structured output. |
| `satisfied` is not accepted | Inspect whether passing Evidence belongs to the exact final candidate. |
| Candidate fails before grading | Keep normalized candidate source at or below 3,500 characters. |
| A dependency pin needs to move | Rerun Python tests, middleware characterization, keyless smoke, frontend tests/build, and lifecycle validation. |
