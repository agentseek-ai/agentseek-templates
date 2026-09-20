# Repository image assets

`image-assets` is the long-lived image store for pull requests, issues, and documentation in `agentseek-ai/agentseek-templates`.

This branch has its own history and is maintained separately from application code. Keep it available when cleaning up feature branches; do not merge it into `main`.

## Layout

| Directory | Use |
| --- | --- |
| `<category>/<template>/` | Template images; mirrors the template registry path, for example `deepagents/powercontext/` |
| `shared/<topic>/` | Images shared across templates or documentation |

Use descriptive, lowercase filenames with hyphens, such as `memory-saved.png`. Organize by template or topic, not PR number. Add a short README beside each image set identifying its purpose and source PR or document. For runtime evidence, include the tested code commit and capture date.

## Add images

Work in a separate checkout of this branch:

```bash
git clone --single-branch --branch image-assets \
  https://github.com/agentseek-ai/agentseek-templates.git image-assets
cd image-assets
mkdir -p deepagents/powercontext
cp /path/to/screenshot.png deepagents/powercontext/feature.png
# Update deepagents/powercontext/README.md to describe the evidence.
git add deepagents/powercontext
git commit -m "docs: add PowerContext screenshots"
git push origin HEAD:image-assets
git rev-parse HEAD
```

Keep images reasonably sized and publish only material intended for public viewing. PNG is suitable for text-heavy screenshots; WebP or JPEG can reduce the size of photographic images.

## Embed permanent links

Use the full commit SHA printed after publishing, rather than the branch name:

```markdown
![Describe what the image demonstrates](https://raw.githubusercontent.com/agentseek-ai/agentseek-templates/<full-commit-sha>/deepagents/powercontext/feature.png)
```

Verify that each URL loads and that the image renders in its destination before considering the upload complete. For revised evidence, add a new commit and update the destination explicitly. Preserve this branch's history: do not force-push or delete it, because published links refer to earlier commits.

## Image sets

| Set | Description |
| --- | --- |
| [Deep Agents PowerContext](deepagents/powercontext/README.md) | Saved Memory and real-provider recall on/off comparison |
| [Jev Harness Lab](langchain/jev-harness/README.md) | Bilingual routing and context-sensitive Auto Mode allow/block evidence |
