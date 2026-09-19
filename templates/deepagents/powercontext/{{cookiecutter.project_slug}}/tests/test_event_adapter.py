from __future__ import annotations

from {{ cookiecutter.project_slug }}.event_adapter import error_event, message_event, powercontext_event


def test_message_event_keeps_source_and_path() -> None:
    event = message_event(source="coordinator", path=(), text="hello")
    assert event == {
        "kind": "message",
        "source": "coordinator",
        "path": [],
        "text": "hello",
        "final": False,
    }


def test_powercontext_event_only_carries_recall_details() -> None:
    assert powercontext_event(status="disabled") == {
        "kind": "powercontext",
        "status": "disabled",
        "content_bytes": 0,
    }
    assert powercontext_event(
        status="ready",
        content_bytes=19,
        max_bytes=8000,
        scope_id="scope-1",
        content="retrieved reference",
    ) == {
        "kind": "powercontext",
        "status": "ready",
        "content_bytes": 19,
        "max_bytes": 8000,
        "scope_id": "scope-1",
        "content": "retrieved reference",
    }


def test_error_event_is_stable() -> None:
    assert error_event(message="offline") == {"kind": "error", "message": "offline"}
