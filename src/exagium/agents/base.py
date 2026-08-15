from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

from exagium.core.events import EventDraft
from exagium.core.models import (
    AgentDoctorResult,
    AgentMetadata,
    AgentRunRequest,
    AgentRunResult,
)

EventEmitter = Callable[[EventDraft], Awaitable[None]]


class AgentAdapter(Protocol):
    name: str

    async def doctor(self) -> AgentDoctorResult: ...

    async def metadata(self) -> AgentMetadata: ...

    async def run(self, request: AgentRunRequest, emit: EventEmitter) -> AgentRunResult: ...

    async def cancel(self, run_id: str) -> None: ...
