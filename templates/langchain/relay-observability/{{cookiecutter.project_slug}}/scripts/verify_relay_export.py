"""Validate that the Relay ATOF archive contains JSONL events."""

from __future__ import annotations

import json
from pathlib import Path


path = Path(".nemo-relay/atof/events.jsonl")
if not path.is_file():
    raise SystemExit(f"Relay ATOF archive not found: {path}")

lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
if not lines:
    raise SystemExit(f"Relay ATOF archive is empty: {path}")
for index, line in enumerate(lines, start=1):
    try:
        json.loads(line)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid Relay ATOF JSONL at line {index}: {exc}") from exc
print(f"Validated {len(lines)} Relay ATOF event(s) in {path}")
