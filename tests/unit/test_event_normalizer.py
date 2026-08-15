from exagium.core.events import EventType
from exagium.trace.normalizer import normalize_codex_event


def test_normalizes_command_and_preserves_raw_event() -> None:
    raw = {
        "type": "item.completed",
        "item": {"type": "command_execution", "command": "pytest", "exit_code": 0},
    }

    event = normalize_codex_event(raw)

    assert event.type == EventType.COMMAND_COMPLETED
    assert event.payload["command"] == "pytest"
    assert event.raw_event == raw


def test_unknown_event_is_a_system_note_instead_of_crashing() -> None:
    raw = {"type": "future.event", "new_field": {"kept": True}}

    event = normalize_codex_event(raw)

    assert event.type == EventType.SYSTEM_NOTE
    assert event.source_event_type == "future.event"
    assert event.raw_event == raw


def test_invalid_json_line_is_preserved() -> None:
    event = normalize_codex_event("not json")

    assert event.type == EventType.SYSTEM_NOTE
    assert event.raw_event == "not json"
