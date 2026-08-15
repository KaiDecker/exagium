from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from pydantic import BaseModel

from exagium.core.errors import ExagiumError
from exagium.core.status import TERMINAL_STATUSES, RunStatus
from exagium.storage.repositories import Storage
from exagium.trace.signatures import SemanticStep, normalize_event_sequence


class ComparedRun(BaseModel):
    id: UUID
    task_id: str
    status: RunStatus
    agent_name: str
    variant_id: str | None = None
    steps: list[SemanticStep]


class FirstDivergence(BaseModel):
    step: int
    run_a: SemanticStep | None
    run_b: SemanticStep | None


class RunComparison(BaseModel):
    run_a: ComparedRun
    run_b: ComparedRun
    same_task: bool
    identical: bool
    first_divergence: FirstDivergence | None


def find_first_divergence(
    steps_a: Sequence[SemanticStep],
    steps_b: Sequence[SemanticStep],
) -> FirstDivergence | None:
    for index in range(max(len(steps_a), len(steps_b))):
        step_a = steps_a[index] if index < len(steps_a) else None
        step_b = steps_b[index] if index < len(steps_b) else None
        if step_a is None or step_b is None or step_a.signature != step_b.signature:
            return FirstDivergence(step=index + 1, run_a=step_a, run_b=step_b)
    return None


class CompareService:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def compare(self, run_a_id: UUID, run_b_id: UUID) -> RunComparison:
        if run_a_id == run_b_id:
            raise ExagiumError("Choose two different runs to compare")
        row_a = self.storage.get_run(run_a_id)
        row_b = self.storage.get_run(run_b_id)
        if row_a is None:
            raise ExagiumError(f"Run not found: {run_a_id}")
        if row_b is None:
            raise ExagiumError(f"Run not found: {run_b_id}")

        status_a = RunStatus(row_a["status"])
        status_b = RunStatus(row_b["status"])
        if status_a not in TERMINAL_STATUSES or status_b not in TERMINAL_STATUSES:
            raise ExagiumError("Only terminal runs can be compared")

        steps_a = normalize_event_sequence(self.storage.list_events(run_a_id), status_a)
        steps_b = normalize_event_sequence(self.storage.list_events(run_b_id), status_b)
        divergence = find_first_divergence(steps_a, steps_b)
        return RunComparison(
            run_a=ComparedRun(
                id=run_a_id,
                task_id=row_a["task_id"],
                status=status_a,
                agent_name=row_a["agent_name"],
                variant_id=row_a["variant_id"],
                steps=steps_a,
            ),
            run_b=ComparedRun(
                id=run_b_id,
                task_id=row_b["task_id"],
                status=status_b,
                agent_name=row_b["agent_name"],
                variant_id=row_b["variant_id"],
                steps=steps_b,
            ),
            same_task=row_a["task_id"] == row_b["task_id"],
            identical=divergence is None,
            first_divergence=divergence,
        )
