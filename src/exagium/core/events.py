from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EventType(StrEnum):
    RUN_STARTED = "RUN_STARTED"
    RUN_FINISHED = "RUN_FINISHED"
    RUN_FAILED = "RUN_FAILED"
    AGENT_MESSAGE = "AGENT_MESSAGE"
    TOOL_STARTED = "TOOL_STARTED"
    TOOL_COMPLETED = "TOOL_COMPLETED"
    TOOL_FAILED = "TOOL_FAILED"
    COMMAND_STARTED = "COMMAND_STARTED"
    COMMAND_COMPLETED = "COMMAND_COMPLETED"
    COMMAND_FAILED = "COMMAND_FAILED"
    FILE_CHANGED = "FILE_CHANGED"
    USAGE_REPORTED = "USAGE_REPORTED"
    VALIDATION_STARTED = "VALIDATION_STARTED"
    VALIDATION_COMPLETED = "VALIDATION_COMPLETED"
    # 不认识的事件
    SYSTEM_NOTE = "SYSTEM_NOTE"


class EventDraft(BaseModel):
    type: EventType
    source: str
    source_event_type: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    raw_event: dict[str, Any] | str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AgentEvent(EventDraft):
    id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    seq: int = Field(ge=1)
