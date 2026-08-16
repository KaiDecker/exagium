from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from exagium.core.status import RunStatus


class SemanticSignature(StrEnum):
    SEARCH = "SEARCH"
    READ = "READ"
    EDIT = "EDIT"
    TEST = "TEST"
    COMMAND = "COMMAND"
    TOOL = "TOOL"
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


class SemanticStep(BaseModel):
    step: int
    signature: SemanticSignature
    detail: str | None = None
    event_seq: int | None = None
    event_type: str | None = None
    outcome: str | None = None


_TEST_COMMAND = re.compile(
    r"(?:^|[\s;&|])(?:pytest|py\.test|unittest|tox|nox|jest|vitest|go\s+test|"
    r"cargo\s+test|npm\s+(?:run\s+)?test|pnpm\s+(?:run\s+)?test|"
    r"yarn\s+(?:run\s+)?test|bun\s+test)(?:[\s;&|]|$)",
    re.IGNORECASE,
)
_SEARCH_COMMAND = re.compile(
    r"(?:^|[\s;&|])(?:rg|grep|findstr|select-string|fd)(?:[\s;&|]|$)",
    re.IGNORECASE,
)
_READ_COMMAND = re.compile(
    r"(?:^|[\s;&|])(?:cat|type|get-content|head|tail|less|more)(?:[\s;&|]|$)",
    re.IGNORECASE,
)
_EDIT_COMMAND = re.compile(
    r"(?:^|[\s;&|])(?:apply_patch|set-content|add-content)(?:[\s;&|]|$)",
    re.IGNORECASE,
)


def _text(value: Any) -> str | None:
    if isinstance(value, str):
        return " ".join(value.split()) or None
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        rendered = " ".join(str(item) for item in value)
        return " ".join(rendered.split()) or None
    return None


def classify_command(command: str | None) -> SemanticSignature:
    if not command:
        return SemanticSignature.COMMAND
    if _SEARCH_COMMAND.search(command):
        return SemanticSignature.SEARCH
    if _TEST_COMMAND.search(command):
        return SemanticSignature.TEST
    if _READ_COMMAND.search(command):
        return SemanticSignature.READ
    if _EDIT_COMMAND.search(command):
        return SemanticSignature.EDIT
    return SemanticSignature.COMMAND


def classify_tool(name: str | None) -> SemanticSignature:
    normalized = (name or "").lower()
    if any(token in normalized for token in ("search", "grep", "ripgrep", "find_files")):
        return SemanticSignature.SEARCH
    if any(token in normalized for token in ("read", "get_file", "view_file")):
        return SemanticSignature.READ
    if any(token in normalized for token in ("edit", "write", "patch")):
        return SemanticSignature.EDIT
    if "test" in normalized:
        return SemanticSignature.TEST
    return SemanticSignature.TOOL


def _operation_key(payload: Mapping[str, Any], detail: str | None) -> str:
    for key in ("id", "item_id", "call_id", "tool_call_id", "tool_use_id"):
        if value := payload.get(key):
            return str(value)
    return detail or "unknown"


def _outcome(event_type: str, payload: Mapping[str, Any]) -> str | None:
    if event_type.endswith("FAILED"):
        return "FAILED"
    exit_code = payload.get("exit_code")
    if isinstance(exit_code, int):
        return "PASSED" if exit_code == 0 else "FAILED"
    if event_type.endswith("COMPLETED"):
        return "COMPLETED"
    return None


def normalize_event_sequence(
    events: Sequence[Mapping[str, Any]],
    run_status: RunStatus | str | None = None,
) -> list[SemanticStep]:
    steps: list[SemanticStep] = []
    pending: dict[tuple[str, str], int] = {}

    for event in sorted(events, key=lambda item: int(item.get("seq", 0))):
        event_type = str(event.get("type") or "")
        payload_value = event.get("payload")
        payload = payload_value if isinstance(payload_value, Mapping) else {}
        signature: SemanticSignature | None = None
        detail: str | None = None
        operation_group: str | None = None

        if event_type.startswith("COMMAND_"):
            detail = _text(payload.get("command"))
            signature = classify_command(detail)
            operation_group = "COMMAND"
        elif event_type.startswith("TOOL_"):
            detail = _text(
                payload.get("name")
                or payload.get("tool")
                or payload.get("tool_name")
                or payload.get("command")
            )
            signature = classify_tool(detail)
            operation_group = "TOOL"
        elif event_type == "FILE_CHANGED":
            detail = _text(payload.get("path") or payload.get("file") or payload.get("name"))
            signature = SemanticSignature.EDIT

        if signature is None:
            continue

        outcome = _outcome(event_type, payload)
        if operation_group:
            key = (operation_group, _operation_key(payload, detail))
            if event_type.endswith("STARTED"):
                pending[key] = len(steps)
            elif key in pending:
                index = pending.pop(key)
                steps[index] = steps[index].model_copy(
                    update={"event_type": event_type, "outcome": outcome}
                )
                continue

        steps.append(
            SemanticStep(
                step=len(steps) + 1,
                signature=signature,
                detail=detail,
                event_seq=int(event["seq"]) if event.get("seq") is not None else None,
                event_type=event_type,
                outcome=outcome,
            )
        )

    terminal = {
        RunStatus.PASSED: SemanticSignature.PASS,
        RunStatus.FAILED: SemanticSignature.FAIL,
        RunStatus.ERROR: SemanticSignature.ERROR,
        RunStatus.CANCELLED: SemanticSignature.CANCELLED,
    }.get(RunStatus(run_status) if run_status else None)
    if terminal:
        steps.append(SemanticStep(step=len(steps) + 1, signature=terminal))
    return steps
