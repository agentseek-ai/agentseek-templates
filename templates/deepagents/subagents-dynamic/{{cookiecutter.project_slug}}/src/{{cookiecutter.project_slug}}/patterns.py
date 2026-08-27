"""Six focused Dynamic Subagents scenarios from the official pattern guide."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SubagentSpec:
    """One specialist made available to a pattern coordinator."""

    name: str
    description: str
    system_prompt: str


@dataclass(frozen=True)
class PatternSpec:
    """Configuration that keeps one teaching pattern isolated from the others."""

    assistant_id: str
    title: str
    example_prompt: str
    coordinator_prompt: str
    subagents: tuple[SubagentSpec, ...]
    fixture_directory: str | None = None


PATTERNS: dict[str, PatternSpec] = {
    "classify_and_act": PatternSpec(
        assistant_id="classify_and_act",
        title="Classify and act",
        example_prompt="""Run a workflow to classify and handle every customer request below.

- C-101: Since yesterday, signing in with a correct password returns an unexpected 500 error.
- C-102: We need a scheduled bulk export to our warehouse in Parquet format.
- C-103: Does the annual plan include refunds for unused seats after a team member leaves?

Return a concise triage table with the category, recommended action, and next step for each request.""",
        coordinator_prompt=(
            "You coordinate customer-request triage. Handle every request exactly once. "
            "Determine whether each request is a bug, feature request, or support question, then "
            "send it to the specialist whose expertise matches that category. Preserve the request "
            "ID in every handoff and in the final table. The work is complete only when every "
            "request has a category, a specialist result, and a concrete next step."
        ),
        subagents=(
            SubagentSpec(
                name="bug-fixer",
                description="Investigates bug reports and provides reproduction and mitigation steps.",
                system_prompt=(
                    "You are a bug triage specialist. Investigate the supplied report, identify the "
                    "likely failure boundary, and provide reproducible checks plus a safe next action."
                ),
            ),
            SubagentSpec(
                name="feature-analyst",
                description="Evaluates feature requests for feasibility, effort, and product impact.",
                system_prompt=(
                    "You are a product analyst. Evaluate the supplied request for feasibility, "
                    "dependencies, delivery effort, user value, and the next discovery question."
                ),
            ),
            SubagentSpec(
                name="support-agent",
                description="Answers customer policy and product-usage questions clearly.",
                system_prompt=(
                    "You are a support specialist. Answer carefully and distinguish what can be "
                    "answered now from policy details that require confirmation."
                ),
            ),
        ),
    ),
    "fan_out_and_synthesize": PatternSpec(
        assistant_id="fan_out_and_synthesize",
        title="Fan-out and synthesize",
        example_prompt=(
            "Run a workflow to review every route in the bundled checkout-service sample for "
            "authentication or authorization risks. Summarize and deduplicate the most important "
            "issues, citing the affected route and line evidence."
        ),
        coordinator_prompt=(
            "You coordinate a complete route-security sweep. Discover the bundled Python inputs "
            "by calling glob with the exact relative pattern `**/*.py`, then dispatch exactly one "
            "reviewer task per discovered path in a single first-pass batch so every discovered "
            "route is covered. Hand off each path "
            "exactly as glob returned it. Accept an empty finding list as a valid review; do not "
            "repeat, deepen, or independently verify a completed path. Combine the returned "
            "findings, remove duplicates "
            "and order the final risks by severity. Report coverage as reviewed routes over "
            "discovered routes; never describe an unread or failed route as reviewed."
        ),
        subagents=(
            SubagentSpec(
                name="reviewer",
                description="Reviews one route for authentication and authorization defects.",
                system_prompt=(
                    "You are a security-focused code reviewer. The assigned Python path is already "
                    "fixture-relative; pass that path unchanged to read_file. Report only concrete "
                    "authentication or authorization issues with file, line, severity, and evidence. "
                    "An empty result is valid."
                ),
            ),
        ),
        fixture_directory="routes",
    ),
    "adversarial_verification": PatternSpec(
        assistant_id="adversarial_verification",
        title="Adversarial verification",
        example_prompt=(
            "Run a workflow to audit the bundled payment module. Treat initial findings as "
            "unconfirmed and report only vulnerabilities that survive an independent skeptical "
            "review, with source evidence."
        ),
        coordinator_prompt=(
            "You coordinate a high-confidence payment audit. Discover the bundled Python inputs "
            "by calling glob with the exact relative pattern `**/*.py`. "
            "First obtain candidate vulnerabilities from a security audit. Then have each candidate "
            "independently challenged against the source. Only independently confirmed findings may "
            "appear in the final report. Show candidate, confirmed, and refuted counts, and include "
            "the verifier's source-based reason for every decision."
        ),
        subagents=(
            SubagentSpec(
                name="reviewer",
                description="Finds potential vulnerabilities in the supplied payment code.",
                system_prompt=(
                    "You are a payment security auditor. Use read_file for every assigned path. "
                    "Return candidate vulnerabilities with a stable ID, file, line, severity, and "
                    "concrete evidence."
                ),
            ),
            SubagentSpec(
                name="verifier",
                description="Independently attempts to disprove a candidate vulnerability.",
                system_prompt=(
                    "You are a skeptical security verifier. Use read_file to inspect the cited source "
                    "in context. Try to disprove the candidate and confirm it only when the exploit "
                    "condition is present. Give a boolean verdict and a source-based reason."
                ),
            ),
        ),
        fixture_directory="payments",
    ),
    "generate_and_filter": PatternSpec(
        assistant_id="generate_and_filter",
        title="Generate and filter",
        example_prompt=(
            "Run a workflow to design an order data model for high-volume ordering, partial "
            "fulfillment, refunds, and immutable audit history. Produce several independent "
            "candidates, assess them against those requirements, and recommend the strongest result."
        ),
        coordinator_prompt=(
            "You coordinate order-schema design. Obtain three independent designs that make "
            "meaningfully different modeling choices. Compare them against throughput, partial "
            "fulfillment, refund correctness, auditability, and migration cost. Select one result "
            "only after the comparison. The final answer must show all three candidate summaries, "
            "the evaluation dimensions, the ranking, and the recommended schema with its main tradeoff."
        ),
        subagents=(
            SubagentSpec(
                name="architect",
                description="Proposes an order schema with tradeoffs and migration considerations.",
                system_prompt=(
                    "You are a database architect. Produce an independent schema proposal for the "
                    "supplied requirements. Include entities, key invariants, scaling approach, "
                    "tradeoffs, and migration considerations."
                ),
            ),
        ),
    ),
    "tournament": PatternSpec(
        assistant_id="tournament",
        title="Tournament",
        example_prompt="""Run a workflow to produce five competing readability rewrites of this function,
compare them head to head, and return the clearest result with the comparison reasons.

```python
def processOrder(order, inventory, gateway):
    if order and order.get("status") == "new":
        if inventory.get(order["sku"], 0) >= order["quantity"]:
            if gateway.charge(order["customer_id"], order["total"]):
                inventory[order["sku"]] -= order["quantity"]
                order["status"] = "paid"
                return True
    return False
```""",
        coordinator_prompt=(
            "You coordinate a readability tournament. Produce exactly five distinct rewrites, then "
            "compare candidates head to head using explicit criteria: naming, control-flow depth, "
            "side-effect clarity, and behavior preservation. Advance winners through a 5 → 3 → 2 → 1 "
            "bracket, which requires four judgments. The final answer must show the bracket, each "
            "judgment reason, the champion implementation, and why its behavior matches the original."
        ),
        subagents=(
            SubagentSpec(
                name="writer",
                description="Rewrites a function to maximize readability while preserving behavior.",
                system_prompt=(
                    "You are an expert clean-code programmer. Produce one distinctive rewrite of the "
                    "supplied function. Preserve behavior and explain the readability strategy."
                ),
            ),
            SubagentSpec(
                name="judge",
                description="Compares two implementations and selects the more readable one.",
                system_prompt=(
                    "You are a code-quality judge. Compare exactly two supplied implementations using "
                    "naming, control-flow depth, side-effect clarity, and behavior preservation. Pick "
                    "A or B and give a specific reason."
                ),
            ),
        ),
    ),
    "loop_until_done": PatternSpec(
        assistant_id="loop_until_done",
        title="Loop until done",
        example_prompt=(
            "Run a workflow to find dead code in the bundled sample package. Continue checking while "
            "a pass adds new evidence, deduplicate the findings, and stop when another pass adds nothing."
        ),
        coordinator_prompt=(
            "You coordinate exhaustive dead-code discovery. Discover the bundled Python inputs by "
            "calling glob with the exact relative pattern `**/*.py`, then "
            "run repeated analysis rounds. Each round must receive the already-seen finding IDs, add "
            "only genuinely new evidence, and report its new-item count. Stop when a round adds zero "
            "items. Use a safety guard of no more than four rounds; if that guard is reached before "
            "convergence, say so explicitly. The final answer must show per-round counts, unique "
            "findings, and whether the workflow converged."
        ),
        subagents=(
            SubagentSpec(
                name="analyzer",
                description="Finds unused exports, unreachable functions, and orphaned modules.",
                system_prompt=(
                    "You are a dead-code analyst. Use read_file on the supplied package paths. Return "
                    "only findings not present in the supplied seen-ID list, with a stable ID, file, "
                    "line, kind, and reference evidence. An empty items list is the convergence signal."
                ),
            ),
        ),
        fixture_directory="dead-code-package",
    ),
}
