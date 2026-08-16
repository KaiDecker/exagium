from __future__ import annotations

from typing import Any

from exagium.core.events import EventDraft, EventType

_CLAUDE_COMMAND_TOOLS = {"Bash", "PowerShell"}
_CLAUDE_FILE_TOOLS = {"Edit", "Write", "NotebookEdit"}


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
        event_type = (
            EventType.SYSTEM_NOTE
            if source_type.endswith("started")
            else EventType.FILE_CHANGED
        )
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


class ClaudeEventNormalizer:
    def __init__(self) -> None:
        self._pending_tools: dict[str, dict[str, Any]] = {}

    def normalize(self, raw: dict[str, Any] | str) -> list[EventDraft]:
        if isinstance(raw, str):
            return [
                EventDraft(
                    type=EventType.SYSTEM_NOTE,
                    source="claude",
                    payload={"message": "Claude 输出了非 JSON 行", "line": raw},
                    raw_event=raw,
                )
            ]

        source_type = str(raw.get("type") or "unknown")
        if source_type == "assistant":
            return self._assistant_events(raw)
        if source_type == "user":
            return self._tool_result_events(raw)
        if source_type == "result":
            return self._result_events(raw)
        if source_type == "system" and raw.get("subtype") == "init":
            return [self._event(EventType.RUN_STARTED, source_type, raw, dict(raw))]

        return [
            self._event(
                EventType.SYSTEM_NOTE,
                source_type,
                raw,
                {"message": "无法识别的 Claude 事件", **raw},
            )
        ]

    def _assistant_events(self, raw: dict[str, Any]) -> list[EventDraft]:
        message = raw.get("message")
        message = message if isinstance(message, dict) else {}
        content = message.get("content")
        blocks = content if isinstance(content, list) else []
        events: list[EventDraft] = []

        for block in blocks:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type == "text":
                events.append(
                    self._event(
                        EventType.AGENT_MESSAGE,
                        "assistant",
                        raw,
                        {"text": block.get("text"), "model": message.get("model")},
                    )
                )
            elif block_type == "tool_use":
                events.append(self._tool_started(raw, block))

        usage = message.get("usage")
        if isinstance(usage, dict):
            events.append(self._usage_event(raw, usage))
        if events:
            return events
        return [
            self._event(
                EventType.SYSTEM_NOTE,
                "assistant",
                raw,
                {"message": "Claude assistant 事件不包含可识别内容"},
            )
        ]

    def _tool_started(self, raw: dict[str, Any], block: dict[str, Any]) -> EventDraft:
        tool_id = str(block.get("id") or "unknown")
        tool_name = str(block.get("name") or "unknown")
        tool_input = block.get("input")
        tool_input = tool_input if isinstance(tool_input, dict) else {}
        pending = {"id": tool_id, "name": tool_name, "input": tool_input}
        self._pending_tools[tool_id] = pending
        payload = {
            "tool_use_id": tool_id,
            "name": tool_name,
            "input": tool_input,
        }
        if tool_name in _CLAUDE_COMMAND_TOOLS:
            payload["command"] = tool_input.get("command")
            return self._event(EventType.COMMAND_STARTED, "assistant", raw, payload)
        return self._event(EventType.TOOL_STARTED, "assistant", raw, payload)

    def _tool_result_events(self, raw: dict[str, Any]) -> list[EventDraft]:
        message = raw.get("message")
        message = message if isinstance(message, dict) else {}
        content = message.get("content")
        blocks = content if isinstance(content, list) else []
        events: list[EventDraft] = []

        for block in blocks:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            tool_id = str(block.get("tool_use_id") or "unknown")
            pending = self._pending_tools.pop(tool_id, {})
            tool_name = str(pending.get("name") or "unknown")
            tool_input = pending.get("input")
            tool_input = tool_input if isinstance(tool_input, dict) else {}
            failed = bool(block.get("is_error"))
            payload = {
                "tool_use_id": tool_id,
                "name": tool_name,
                "input": tool_input,
                "content": block.get("content"),
            }
            if tool_name in _CLAUDE_COMMAND_TOOLS:
                payload["command"] = tool_input.get("command")
                event_type = EventType.COMMAND_FAILED if failed else EventType.COMMAND_COMPLETED
            else:
                event_type = EventType.TOOL_FAILED if failed else EventType.TOOL_COMPLETED
            events.append(self._event(event_type, "user", raw, payload))

            if not failed and tool_name in _CLAUDE_FILE_TOOLS:
                path = tool_input.get("file_path") or tool_input.get("notebook_path")
                events.append(
                    self._event(
                        EventType.FILE_CHANGED,
                        "user",
                        raw,
                        {"tool_use_id": tool_id, "name": tool_name, "path": path},
                    )
                )

        if events:
            return events
        return [
            self._event(
                EventType.SYSTEM_NOTE,
                "user",
                raw,
                {"message": "Claude user 事件不包含工具结果"},
            )
        ]

    def _result_events(self, raw: dict[str, Any]) -> list[EventDraft]:
        events: list[EventDraft] = []
        usage = raw.get("usage")
        if isinstance(usage, dict):
            payload = dict(usage)
            if raw.get("total_cost_usd") is not None:
                payload["cost"] = raw["total_cost_usd"]
            events.append(self._usage_event(raw, payload))
        failed = bool(raw.get("is_error")) or raw.get("subtype") not in {None, "success"}
        events.append(
            self._event(
                EventType.RUN_FAILED if failed else EventType.RUN_FINISHED,
                "result",
                raw,
                {
                    "subtype": raw.get("subtype"),
                    "result": raw.get("result"),
                    "duration_ms": raw.get("duration_ms"),
                    "num_turns": raw.get("num_turns"),
                },
            )
        )
        return events

    def _usage_event(self, raw: dict[str, Any], usage: dict[str, Any]) -> EventDraft:
        payload = dict(usage)
        if payload.get("total_tokens") is None:
            input_tokens = payload.get("input_tokens")
            output_tokens = payload.get("output_tokens")
            if isinstance(input_tokens, int) and isinstance(output_tokens, int):
                payload["total_tokens"] = input_tokens + output_tokens
        return self._event(EventType.USAGE_REPORTED, "usage", raw, payload)

    @staticmethod
    def _event(
        event_type: EventType,
        source_type: str,
        raw: dict[str, Any],
        payload: dict[str, Any],
    ) -> EventDraft:
        return EventDraft(
            type=event_type,
            source="claude",
            source_event_type=source_type,
            payload=payload,
            raw_event=raw,
        )
