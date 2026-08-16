from __future__ import annotations

from collections.abc import Mapping, Sequence

from exagium.agents.base import AgentAdapter
from exagium.config import Settings
from exagium.core.errors import ExagiumError
from exagium.core.models import (
    ExperimentManifest,
    ExperimentOutcome,
    ExperimentVariant,
    RunOutcome,
    TaskManifest,
)
from exagium.experiments.allocation import build_allocation_plan
from exagium.experiments.metrics import summarize_experiment
from exagium.runner.run_service import RunService
from exagium.storage.repositories import Storage


class ExperimentService:
    def __init__(
        self,
        *,
        settings: Settings,
        storage: Storage,
        adapters: Mapping[str, AgentAdapter],
    ) -> None:
        self.settings = settings
        self.storage = storage
        self.adapters = adapters

    async def execute(
        self,
        experiment: ExperimentManifest,
        tasks: TaskManifest | Sequence[TaskManifest],
        *,
        keep_workspace: bool = False,
        timeout_seconds: int | None = None,
    ) -> ExperimentOutcome:
        missing = sorted({variant.agent for variant in experiment.variants} - self.adapters.keys())
        if missing:
            raise ExagiumError(f"Unsupported experiment agent(s): {', '.join(missing)}")

        task_list = [tasks] if isinstance(tasks, TaskManifest) else list(tasks)
        if not task_list:
            raise ExagiumError("Experiment requires at least one task")
        task_by_id = {task.id: task for task in task_list}
        if len(task_by_id) != len(task_list):
            raise ExagiumError("Experiment task ids must be unique")

        self.settings.ensure_directories()
        self.storage.initialize()
        for task in task_list:
            self.storage.register_task(task)
        allocation_plan = build_allocation_plan(experiment, task_list)
        self.storage.register_experiment(
            experiment,
            task_list[0].id,
            task_ids=[task.id for task in task_list],
            allocation=[item.model_dump() for item in allocation_plan],
        )

        variant_by_id = {variant.id: variant for variant in experiment.variants}
        outcomes = {variant.id: [] for variant in experiment.variants}
        for allocation in allocation_plan:
            variant = variant_by_id[allocation.variant_id]
            service = RunService(
                settings=self.settings,
                storage=self.storage,
                adapter=self.adapters[variant.agent],
            )
            outcomes[variant.id].append(
                await service.execute(
                    task_by_id[allocation.task_id],
                    keep_workspace=keep_workspace,
                    timeout_seconds=timeout_seconds,
                    experiment_id=experiment.id,
                    variant_id=variant.id,
                )
            )

        outcomes_by_variant: list[tuple[ExperimentVariant, list[RunOutcome]]] = [
            (variant, outcomes[variant.id]) for variant in experiment.variants
        ]

        return summarize_experiment(
            experiment,
            [task.id for task in task_list],
            outcomes_by_variant,
        )
