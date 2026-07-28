from __future__ import annotations

import argparse
import json
import tomllib
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, urlunsplit

EXPECTED_PACKAGES = {
    "agentseek-ag-ui": "contrib/agentseek-ag-ui",
    "agentseek-langchain": "contrib/agentseek-langchain",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("lock", type=Path)
    args = parser.parse_args()

    repository_root = Path(__file__).resolve().parents[1]
    release = json.loads((repository_root / "catalog-release.json").read_text(encoding="utf-8"))
    lock = tomllib.loads(args.lock.read_text(encoding="utf-8"))
    packages = {package["name"]: package for package in lock["package"]}

    for package_name, subdirectory in EXPECTED_PACKAGES.items():
        source = packages[package_name]["source"]["git"]
        parsed = urlsplit(source)
        repository = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
        query = parse_qs(parsed.query)
        assert repository == release["core_repository"]
        assert query == {"rev": [release["core_commit"]], "subdirectory": [subdirectory]}
        assert parsed.fragment == release["core_commit"]


if __name__ == "__main__":
    main()
