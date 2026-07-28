from __future__ import annotations

import argparse
from pathlib import Path

from agentseek.cli.lifecycle import normalize_lifecycle
from agentseek.cli.lifecycle.authored import LifecycleSpecV2
from agentseek.cli.lifecycle.spec import read_lifecycle_spec


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_root", type=Path)
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    spec = read_lifecycle_spec(project_root / ".agentseek" / "lifecycle.toml", project_root=project_root)
    assert isinstance(spec, LifecycleSpecV2)
    normalized = normalize_lifecycle(spec, project_root=project_root)
    assert normalized.lifecycle_version == 2
    assert normalized.metadata_complete is True
    assert not normalized.warnings


if __name__ == "__main__":
    main()
