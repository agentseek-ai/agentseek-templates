# Contributing

Template changes must preserve the catalog as an immutable-release input.

1. Add or update a self-contained directory under `templates/<type>/<name>`.
2. Keep `templates/index.json` synchronized with every published template.
3. Author `.agentseek/lifecycle.toml` as strict lifecycle version 2 with one
   visible primary service when services exist.
4. Keep generated core dependencies pinned by both repository URL and full
   commit SHA.
5. Run `make check` before opening a pull request.

Do not add credentials, mutable core dependency branches, escaping symlinks, or
references to files outside a template subtree. A catalog release tag is never
moved or reused.

## Upgrade a template's AgentSeek API runtime

`deepagents/powercontext` is the reference upgrade from
`agentseek-api[embedded]==0.2.3` to `0.3.2`. Upgrade and validate one template
at a time before applying the same process to the remaining templates.

The generated project's `pyproject.toml` declares its exact installable runtime.
`scripts/template_runtime_versions.py` records the reviewed API version for
each API-based template. Render tests and the runtime smoke runner share that
policy; `templates/index.json` remains the published template registry. The
policy stays in this repository and is not a generated-project dependency.

1. Verify the target release is published on PyPI and review its Python,
   dependency, persistence, and API compatibility requirements.
2. Update the selected template's `agentseek-api[embedded]==...` dependency
   and its entry in `AGENTSEEK_API_VERSIONS` together. If the template also
   ships `requirements.txt` (such as `langchain/cli-remote`), update that pin
   too. Keep exact pins and the embedded extra. Preserve other templates'
   reviewed versions until their own upgrade is validated.
3. Render a fresh project, install its declared dependencies, and run its
   backend tests plus any frontend tests/build and template-specific
   integration checks. For PowerContext, the `Deep Agents PowerContext`
   workflow additionally exercises Memory against a real embedded seekdb
   Server. Check the generated `uv.lock`; the catalog's root lockfile does
   not lock generated-project dependencies.
4. Run `make check` and the generated lifecycle proof with Python 3.12,
   Node 24, and output paths outside the checkout. PowerContext's example:

   ```sh
   uv run python scripts/generated_runtime_smoke.py \
     --template deepagents/powercontext \
     --catalog-mode source \
     --agentseek-version 0.1.2 \
     --agentseek-api-version 0.3.2 \
     --database-mode embedded \
     --output-root /private/tmp/pc-proof \
     --proof-output /private/tmp/pc-proof.json
   ```

   These short paths suit macOS embedded seekdb socket limits. On Linux, use
   `/tmp/pc-proof` and `/tmp/pc-proof.json`. Embedded mode requires a supported
   native platform; use the template's existing Windows/SQLite matrix entry
   where applicable rather than treating SQLite as embedded seekdb evidence.
   The proof checks the published wheel hash, installed import, generated
   lockfile, readiness, and assistant/thread/run lifecycle. It uses a local
   test provider, so it does not prove live-provider behavior.
5. Verify the PR's hosted checks and uploaded runtime proof at its latest
   commit before merging. An upgrade is not validated by editing version
   assertions alone. Record any skipped or platform-specific validation.

The main CI matrix omits `--agentseek-api-version` and automatically selects
the template's reviewed version. Supplying the flag, as above, asserts that
version; it cannot override the reviewed policy. A future upgrade normally
changes the template pin and policy entry without editing CI's shared command
or adding another hard-coded version guard. Add or extend a smoke profile and
workflow entry when a template needs runtime coverage; a policy entry alone
does not supply that coverage.

Do not change the core dependency commit or `catalog-origin.json` for an API
package upgrade. Publishing a new default catalog through AgentSeek remains
a separate catalog/core release step.
