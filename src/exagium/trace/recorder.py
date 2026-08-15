from __future__ import annotations

from uuid import UUID

from exagium.core.events import AgentEvent, EventDraft
from exagium.core.redaction import redact
from exagium.storage.repositories import Storage


class TraceRecorder:
    def __init__(self, storage: Storage, run_id: UUID) -> None:
        self._storage = storage
        self._run_id = run_id
        self._seq = 0

    async def emit(self, draft: EventDraft) -> None:
        self._seq += 1
        data = draft.model_dump()
        data["payload"] = redact(data["payload"])
        data["raw_event"] = redact(data["raw_event"])
        event = AgentEvent(run_id=self._run_id, seq=self._seq, **data)
        self._storage.add_event(event)
