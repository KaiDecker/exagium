from __future__ import annotations

from collections.abc import Mapping

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
        task: TaskManifest,
        *,
        keep_workspace: bool = False,
        timeout_seconds: int | None = None,
    ) -> ExperimentOutcome:
        missing = sorted({variant.agent for variant in experiment.variants} - self.adapters.keys())
        if missing:
            raise ExagiumError(f"Unsupported experiment agent(s): {', '.join(missing)}")

        self.settings.ensure_directories()
        self.storage.initialize()
        self.storage.register_task(task)
        self.storage.register_experiment(experiment, task.id)

        outcomes_by_variant: list[tuple[ExperimentVariant, list[RunOutcome]]] = []
        for variant in experiment.variants:
            outcomes: list[RunOutcome] = []
            adapter = self.adapters[variant.agent]
            for _ in range(variant.repeat):
                service = RunService(
                    settings=self.settings,
                    storage=self.storage,
                    adapter=adapter,
                )
                outcomes.append(
                    await service.execute(
                        task,
                        keep_workspace=keep_workspace,
                        timeout_seconds=timeout_seconds,
                        experiment_id=experiment.id,
                        variant_id=variant.id,
                    )
                )
            outcomes_by_variant.append((variant, outcomes))

        return summarize_experiment(experiment, task.id, outcomes_by_variant)
