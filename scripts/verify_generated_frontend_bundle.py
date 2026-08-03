from __future__ import annotations

import argparse
import sys
from pathlib import Path

FORBIDDEN_PROVIDER_CREDENTIAL_NAMES = (
    "RUBRIC_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
)


def find_forbidden_names(bundle_root: Path) -> list[tuple[Path, str]]:
    matches: list[tuple[Path, str]] = []
    encoded_names = tuple((name, name.encode("ascii")) for name in FORBIDDEN_PROVIDER_CREDENTIAL_NAMES)
    for path in sorted(candidate for candidate in bundle_root.rglob("*") if candidate.is_file()):
        contents = path.read_bytes()
        matches.extend((path, name) for name, encoded in encoded_names if encoded in contents)
    return matches


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reject provider credential names from a generated frontend bundle.")
    parser.add_argument("bundle_root", type=Path)
    args = parser.parse_args(argv)

    bundle_root = args.bundle_root
    if not bundle_root.is_dir():
        print(f"generated frontend bundle does not exist: {bundle_root}", file=sys.stderr)
        return 2

    matches = find_forbidden_names(bundle_root)
    if matches:
        for path, name in matches:
            print(f"{path}: forbidden provider credential name: {name}", file=sys.stderr)
        return 1

    print(f"Generated frontend bundle contains no provider credential names: {bundle_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
