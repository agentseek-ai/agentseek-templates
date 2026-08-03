# langchain/rubric

Scaffolds a LangChain `create_agent` teaching application for designing and
revising evidence-backed grading rubrics. The template lives under LangChain
because its runnable boundary is `RubricMiddleware` around `create_agent`;
DeepAgents in Action Chapter 13 is the teaching source, not a required runtime
wrapper.

## Learning modes

- **Guided Demo** runs one fixed rubric-revision task with deterministic,
  pre-recorded evidence so the complete loop is inspectable without a model
  credential.
- **Live Model** runs the same teaching flow with the configured worker and
  grader models. It requires a provider credential and may produce different
  revisions between runs.

The generated `rubric-smoke` lifecycle task exercises the keyless path. The
fixed Guided Demo task is deliberately not user-editable: it keeps the evidence,
grader feedback, and revision comparison stable for teaching and regression
checks.

## Source and status

This template is derived from
`datawhalechina/deepagents-in-action/content/ch13-grading-rubrics.md` at exact
commit `6fcef2294bc1ae19e97054426c1355923b50493a`.

The application is **Beta**. Its tested dependency versions are pinned in the
generated Python and frontend manifests; later LangChain, LangGraph, or
`@langchain/react` releases may change middleware or streaming contracts.

The template is not a sandbox. Guided Demo avoids model calls, but Live Model
uses the network endpoint and credentials you configure. It does not isolate
model output, tools, local files, or network access from the host environment.

## Inputs

| Variable | Description |
| --- | --- |
| `project_name` | Human-readable project name. Defaults to "Rubric Lab". |
| `project_slug` | Python package and generated directory name. |
| `author` | Project author. |
| `default_provider` | Live Model provider: `openai`, `anthropic`, or `google`. |
| `worker_model` | Model used to draft and revise rubric content. |
| `grader_model` | Model used to grade draft evidence against the rubric. |
| `langgraph_port` | Port for the LangGraph development API. |
| `frontend_port` | Port for the Vite application. |
