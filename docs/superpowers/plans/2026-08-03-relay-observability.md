# Relay Observability Template Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a lifecycle-v2 LangChain Relay observability template with bounded Tavily research tools, Phoenix, and SeekDB.

**Architecture:** Clone the default LangChain template into a new subtree, then replace only its observability module with a verified Relay adapter and add isolated research tools/tests. Register the template and keep all existing default files untouched.

**Tech Stack:** Cookiecutter, AgentSeek LangChain, LangChain `create_agent`, NeMo Relay, OpenInference/OTLP, Tavily, httpx, markdownify, Docker Compose, Phoenix, OceanBase SeekDB, pytest.

## Global Constraints

- `templates/langchain/default` must not change.
- Every registered template must render lifecycle version 2.
- Relay must be the only application observability chain.
- ATOF is raw archive; OpenInference/OTLP is Phoenix input; Phoenix persists to SeekDB.
- Tavily output is bounded to 3 results, 4000 characters per page, and 10000 characters total.
- `make check` is required before completion.
- Dependency installation is user-run; provide exact commands and directories.

### Task 1: Verify dependency APIs and baselines

**Files:** none.

- [ ] Provide the user commands to run in `/Users/chuixuue/code/agentseek-templates` using `uv` to resolve/install the requested Relay/Tavily/Markdownify dependencies in a temporary verification project.
- [ ] Ask the user to return the resolved version and import/source inspection output.
- [ ] Use that evidence to bind exact Relay APIs in the implementation.

### Task 2: Scaffold the new template

**Files:** Create `templates/langchain/relay-observability/**` by copying the default template; modify cookiecutter, lifecycle, env, gitignore, Compose, README, and Python dependency manifests.

- [ ] Preserve the default runtime and use non-conflicting template ports.
- [ ] Add required Relay, Tavily, Phoenix, and SeekDB variables and mounts.
- [ ] Pin resolved dependencies and retain the reviewed AgentSeek source ref.

### Task 3: Add failing generated-app tests

**Files:** Create generated `tests/test_relay.py`, `tests/test_tools.py`, and any test support files.

- [ ] Assert disabled Relay creates no registration.
- [ ] Assert ATOF-only and default dual-export modes.
- [ ] Assert Phoenix disabled suppresses only Phoenix export.
- [ ] Assert missing Tavily key gives a clear error.
- [ ] Assert truncation, partial fetch failure, and tool inclusion alongside default middleware.
- [ ] Run the focused tests and observe the expected failures before implementation.

### Task 4: Implement Relay adapter and research tools

**Files:** Create generated `src/{{cookiecutter.project_slug}}/relay.py` and `tools.py`; modify `demo_binding.py`, `settings.py`, and prompts/docs as needed.

- [ ] Implement only the verified Relay imports/configuration/exporter/lifecycle APIs.
- [ ] Attach request-scoped callbacks/runtime hooks at the verified `messages_spec` boundary.
- [ ] Keep default middleware and add `tavily_search` plus `think_tool` to `create_agent`.
- [ ] Ensure secrets, headers, cookies, and hidden reasoning are not logged.
- [ ] Run focused tests to green, then refactor without changing behavior.

### Task 5: Register, document, and validate rendering

**Files:** Modify `templates/index.json`, README indexes, and `tests/test_render.py`; modify new template READMEs.

- [ ] Document architecture, startup, configuration switches, troubleshooting, privacy, and persistence.
- [ ] Add the template to all registry/render lists.
- [ ] Render with Cookiecutter and scan for unresolved Jinja placeholders.

### Task 6: Run checks and optional smoke tests

**Files:** none unless fixes are needed.

- [ ] Run formatter, linter, focused tests, full tests, and `make check`.
- [ ] If the user provides Docker/network/keys, run Phoenix + SeekDB and two request trace smoke tests; otherwise report them as unverified.
- [ ] Report exact commands, results, resolved Relay version/API, and remaining risks.
