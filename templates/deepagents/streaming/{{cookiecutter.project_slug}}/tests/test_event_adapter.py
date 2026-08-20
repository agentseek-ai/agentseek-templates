from __future__ import annotations

from {{ cookiecutter.project_slug }}.event_adapter import (
    error_event,
    message_event,
    output_event,
    raw_event,
    subagent_event,
    tool_event,
    values_event,
)


def test_message_event_keeps_source_and_path() -> None:
    event = message_event(source="subagent", path=("researcher:abc",), text="hello")
    assert event == {
        "kind": "message",
        "source": "subagent",
        "path": ["researcher:abc"],
        "text": "hello",
        "final": False,
    }


def test_tool_event_distinguishes_delta_completion_and_error() -> None:
    delta = tool_event(
        phase="delta",
        source="subagent",
        path=("researcher:abc",),
        name="inspect_streaming_topic",
        delta={"part": 1},
    )
    failure = tool_event(
        phase="failed",
        source="subagent",
        path=("researcher:abc",),
        name="inspect_streaming_topic",
        error="offline",
    )
    assert delta["delta"] == {"part": 1}
    assert delta["phase"] == "delta"
    assert failure["phase"] == "failed"
    assert failure["error"] == "offline"


def test_subagent_values_output_and_raw_events_have_stable_kinds() -> None:
    assert subagent_event(phase="started", name="researcher", path=(), status="started")["kind"] == "subagent"
    assert values_event(snapshot={"messages": []})["kind"] == "values"
    assert output_event(output={"messages": []})["kind"] == "output"
    assert output_event(phase="failed", error="offline") == {
        "kind": "output",
        "output": None,
        "phase": "failed",
        "error": "offline",
    }
    assert raw_event(sequence=4, method="messages", namespace=(), data=[])["kind"] == "raw"
    assert error_event(message="offline") == {"kind": "error", "message": "offline"}
