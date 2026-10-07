from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from scripted_model import ScriptedModel, call

from {{ cookiecutter.project_slug }}.agent_factory import build_pattern_graph
from {{ cookiecutter.project_slug }}.patterns import PATTERNS

EXAMPLES_ROOT = Path(__file__).resolve().parents[1] / "examples"


@pytest.mark.parametrize(
    ("pattern", "specialist"),
    [
        ("classify_and_act", "bug-fixer"),
        ("fan_out_and_synthesize", "reviewer"),
        ("adversarial_verification", "verifier"),
        ("generate_and_filter", "architect"),
        ("tournament", "judge"),
        ("loop_until_done", "analyzer"),
    ],
)
def test_each_pattern_dispatches_its_specialist_through_real_quickjs(pattern, specialist):
    code = 'await task({description: "Return the specialist evidence.", subagentType: "' + specialist + '"})'
    model = ScriptedModel(
        replies=[
            call("eval", {"code": code}, "dispatch"),
            AIMessage(content=f"{specialist} evidence"),
            AIMessage(content="Coordinator complete."),
        ]
    )
    graph = build_pattern_graph(model, PATTERNS[pattern], EXAMPLES_ROOT, "openai")

    result = graph.invoke({"messages": [{"role": "user", "content": "Dispatch the specialist."}]})

    assert result["messages"][-1].content == "Coordinator complete."
    dispatches = [
        message for message in result["messages"] if isinstance(message, ToolMessage) and message.name == "eval"
    ]
    assert len(dispatches) == 1
    assert f"{specialist} evidence" in dispatches[0].content


def test_pattern_does_not_dispatch_another_patterns_specialist():
    model = ScriptedModel(
        replies=[
            call(
                "eval", {"code": 'await task({description: "Judge a candidate.", subagentType: "judge"})'}, "dispatch"
            ),
            AIMessage(content="Unknown specialist was rejected."),
        ]
    )
    graph = build_pattern_graph(model, PATTERNS["generate_and_filter"], EXAMPLES_ROOT, "openai")

    result = graph.invoke({"messages": [{"role": "user", "content": "Dispatch the unavailable judge."}]})

    dispatch = next(
        message for message in result["messages"] if isinstance(message, ToolMessage) and message.name == "eval"
    )
    assert "judge" in dispatch.content
    assert "architect" in dispatch.content
    assert result["messages"][-1].content == "Unknown specialist was rejected."
