from __future__ import annotations

import secrets
from dataclasses import asdict, dataclass
from random import Random
from typing import Any

from exagium.core.models import ExperimentManifest, ExperimentVariant, TaskManifest


@dataclass(frozen=True, slots=True)
class RunAllocation:
    """一条可执行且可持久化的实验运行分配。"""

    index: int
    task_id: str
    variant_id: str
    agent: str
    repeat_index: int
    block_id: str | None = None

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


def ensure_allocation_seed(experiment: ExperimentManifest) -> int | None:
    """为随机实验生成一次种子，并写回配置以便之后完整复现。"""

    if not experiment.design.randomize_order:
        return experiment.design.allocation_seed
    if experiment.design.allocation_seed is None:
        experiment.design.allocation_seed = secrets.randbelow(2**63)
    return experiment.design.allocation_seed


def _draft(
    task: TaskManifest,
    variant: ExperimentVariant,
    repeat_index: int,
    *,
    block_id: str | None,
) -> RunAllocation:
    return RunAllocation(
        index=-1,
        task_id=task.id,
        variant_id=variant.id,
        agent=variant.agent,
        repeat_index=repeat_index,
        block_id=block_id,
    )


def build_allocation_plan(
    experiment: ExperimentManifest,
    tasks: list[TaskManifest],
) -> list[RunAllocation]:
    """生成可复现的执行顺序，并在按 Task 阻断时保持局部平衡。"""

    task_ids = [task.id for task in tasks]
    if len(task_ids) != len(set(task_ids)):
        raise ValueError("task ids must be unique within an experiment")
    if not tasks:
        raise ValueError("at least one task is required")

    seed = ensure_allocation_seed(experiment)
    randomizer = Random(seed)
    allocations: list[RunAllocation] = []

    if "task" in experiment.design.block_by:
        blocks: list[list[RunAllocation]] = []
        max_repeats = max(experiment.repeats_for(variant) for variant in experiment.variants)
        for task in tasks:
            for repeat_index in range(max_repeats):
                block_id = f"task:{task.id}:repeat:{repeat_index + 1}"
                block = [
                    _draft(task, variant, repeat_index + 1, block_id=block_id)
                    for variant in experiment.variants
                    if repeat_index < experiment.repeats_for(variant)
                ]
                if experiment.design.randomize_order:
                    randomizer.shuffle(block)
                blocks.append(block)
        if experiment.design.randomize_order:
            randomizer.shuffle(blocks)
        allocations = [allocation for block in blocks for allocation in block]
    else:
        allocations = [
            _draft(task, variant, repeat_index + 1, block_id=None)
            for task in tasks
            for variant in experiment.variants
            for repeat_index in range(experiment.repeats_for(variant))
        ]
        if experiment.design.randomize_order:
            randomizer.shuffle(allocations)

    return [
        RunAllocation(
            index=index,
            task_id=allocation.task_id,
            variant_id=allocation.variant_id,
            agent=allocation.agent,
            repeat_index=allocation.repeat_index,
            block_id=allocation.block_id,
        )
        for index, allocation in enumerate(allocations, start=1)
    ]
