# AgentSeek Templates

This repository is the authoritative, versioned lifecycle-v2 template catalog
for [AgentSeek](https://github.com/ob-labs/agentseek). Catalog releases are
immutable inputs to AgentSeek releases: the CLI resolves an exact catalog
commit, never a mutable branch.

## Use the catalog

AgentSeek 0.1.x uses a reviewed release of this repository as its bundled
default catalog. To inspect or create from another reviewed catalog commit,
select the repository and full commit SHA explicitly:

```bash
agentseek create --list-templates \
  --template-repo https://github.com/agentseek-ai/agentseek-templates.git \
  --checkout <40-character-commit-sha>

agentseek create bub/default \
  --template-repo https://github.com/agentseek-ai/agentseek-templates.git \
  --checkout <40-character-commit-sha>
```

The repository URL and commit form one coordinate for listing, describing, and
creating templates. AgentSeek does not fall back when that explicit coordinate
is unavailable or invalid.

## Repository contract

- `templates/index.json` is the registry source of truth.
- Every registered `templates/<type>/<name>` subtree is self-contained and
  renders a strict lifecycle-v2 project.
- `catalog-origin.json` records the immutable core source commit, registry
  digest, imported templates, and intentional exclusions.
- Generated Git dependencies point to the core AgentSeek repository at an exact
  commit; they never point back to this catalog repository.
- The legacy lifecycle-v1 mirror remains in the core repository for AgentSeek
  0.0.x compatibility. New catalog changes belong in this repository.

See [CONTRIBUTING.md](CONTRIBUTING.md) before changing the registry or a
template.

## License

Apache License 2.0. See [LICENSE](LICENSE).
