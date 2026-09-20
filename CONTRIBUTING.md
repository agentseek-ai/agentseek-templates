# Contributing

Template changes must preserve the catalog as an immutable-release input.

1. Add or update a self-contained directory under `templates/<type>/<name>`.
2. Keep `templates/index.json` synchronized with every published template.
3. Author `.agentseek/lifecycle.toml` as strict lifecycle version 2 with one
   visible primary service when services exist.
4. Keep generated core dependencies pinned by both repository URL and full
   commit SHA.
5. For templates with a frontend, set a literal, nonblank `displayName` in
   `{{cookiecutter.project_slug}}/frontend/package.json`. Preserve brand spelling
   and capitalization; do not use Cookiecutter expressions or surrounding
   whitespace. Keep the package `name` as the generated package identifier.
6. Run `make check` before opening a pull request.

Do not add credentials, mutable core dependency branches, escaping symlinks, or
references to files outside a template subtree. A catalog release tag is never
moved or reused.
