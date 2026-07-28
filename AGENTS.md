# Agent Instructions

- Treat `templates/index.json` as the published registry.
- Every registered template must render and load as lifecycle version 2.
- Keep template subtrees self-contained; do not add escaping paths or symlinks.
- Pin generated dependencies on AgentSeek core with the full reviewed commit.
- Do not modify `catalog-origin.json` unless importing source material from a
  different core commit.
- Run `make check` before completion.
