"""Run a single local publication approval in the generated app's SDK graph."""
from __future__ import annotations

import argparse
import json
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from .agent import EXAMPLE_DIR, build_graph, model
from .lesson_tools import save_report


def run(decision: str) -> None:
    save_report.invoke({"slug": "approval-demo", "content": "# Test publication\n\nLocal course artifact.\n"})
    log = EXAMPLE_DIR / "reports/publications.jsonl"
    before = len(log.read_text().splitlines()) if log.exists() else 0
    graph = build_graph(model, checkpointer=InMemorySaver(), approvals=True)
    config = {"configurable": {"thread_id": str(uuid4())}}
    paused = graph.invoke({"messages": [{"role": "user", "content":
        "Call publish_report(slug='approval-demo') exactly once. This is a local test. "
        "After it returns, stop; do not retry rejected publication or write the log yourself."
    }]}, config)
    if not paused.get("__interrupt__"):
        raise RuntimeError("No publication interrupt; inspect the model's tool calls")
    request = paused["__interrupt__"][0].value
    actions = request["action_requests"]
    if len(actions) != 1 or actions[0]["name"] != "publish_report" or actions[0]["args"] != {"slug": "approval-demo"}:
        raise RuntimeError(f"Unexpected approval actions: {actions}")
    print(json.dumps(request, ensure_ascii=False, indent=2))
    current = len(log.read_text().splitlines()) if log.exists() else 0
    if current != before:
        raise RuntimeError("Publication executed before approval")
    resumed = graph.invoke(Command(resume={"decisions": [{"type": decision}]}), config)
    after = len(log.read_text().splitlines()) if log.exists() else 0
    expected = before + (decision == "approve")
    if resumed.get("__interrupt__") or after != expected:
        raise RuntimeError(f"Approval did not finish as expected: before={before}, after={after}")
    print(f"{decision}: records before={before}, after={after}; checked {log}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--decision", choices=["approve", "reject"], required=True)
    run(parser.parse_args().decision)


if __name__ == "__main__":
    main()
