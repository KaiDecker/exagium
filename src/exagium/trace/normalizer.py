from __future__ import annotations

from typing import Any

from exagium.core.events import EventDraft, EventType


def _item(raw: dict[str, Any]) -> dict[str, Any]:
    value = raw.get("item")
    return value if isinstance(value, dict) else {}


def _payload_without_raw(raw: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in raw.items() if key not in {"type", "item"}}


def normalize_codex_event(raw: dict[str, Any] | str) -> EventDraft:
    if isinstance(raw, str):
        return EventDraft(
            type=EventType.SYSTEM_NOTE,
            source="codex",
            payload={"message": "Codex emitted a non-JSON stdout line", "line": raw},
            raw_event=raw,
        )

    source_type = str(raw.get("type") or "unknown")
    item = _item(raw)
    item_type = str(item.get("type") or "")
    payload: dict[str, Any] = {**_payload_without_raw(raw), **item}

    if item_type == "agent_message":
        event_type = EventType.AGENT_MESSAGE
    elif item_type in {"command_execution", "command"}:
        if source_type.endswith("started"):
            event_type = EventType.COMMAND_STARTED
        elif item.get("exit_code") not in {None, 0} or item.get("status") == "failed":
            event_type = EventType.COMMAND_FAILED
        else:
            event_type = EventType.COMMAND_COMPLETED
    elif item_type in {"file_change", "file_changed"}:
        event_type = EventType.FILE_CHANGED
    elif item_type in {"mcp_tool_call", "tool_call"}:
        if source_type.endswith("started"):
            event_type = EventType.TOOL_STARTED
        elif item.get("status") == "failed" or item.get("error"):
            event_type = EventType.TOOL_FAILED
        else:
            event_type = EventType.TOOL_COMPLETED
    elif source_type in {"usage", "usage.reported"} or "usage" in raw:
        event_type = EventType.USAGE_REPORTED
        payload = raw.get("usage") if isinstance(raw.get("usage"), dict) else payload
    elif source_type in {"run.started", "run.completed", "run.failed"}:
        event_type = {
            "run.started": EventType.RUN_STARTED,
            "run.completed": EventType.RUN_FINISHED,
            "run.failed": EventType.RUN_FAILED,
        }[source_type]
    else:
        event_type = EventType.SYSTEM_NOTE
        payload = {"message": "Unrecognized Codex event", **payload}

    return EventDraft(
        type=event_type,
        source="codex",
        source_event_type=source_type,
        payload=payload,
        raw_event=raw,
    )
