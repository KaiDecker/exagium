from pathlib import Path

from exagium.core.models import (
    CommandSpec,
    ExperimentDesign,
    ExperimentManifest,
    ExperimentVariant,
    RepoSpec,
    TaskManifest,
)
from exagium.experiments.allocation import build_allocation_plan


def task(task_id: str) -> TaskManifest:
    return TaskManifest(
        id=task_id,
        name=task_id,
        repo=RepoSpec(path=Path("repo")),
        prompt="完成任务",
        validation=[CommandSpec(command="python -V")],
    )


def randomized_experiment(seed: int | None = 20260815) -> ExperimentManifest:
    return ExperimentManifest(
        id="blocked-comparison",
        tasks=[Path("task-a.yaml"), Path("task-b.yaml")],
        variants=[
            ExperimentVariant(id="codex", agent="codex"),
            ExperimentVariant(id="claude", agent="claude"),
        ],
        design=ExperimentDesign(
            repeats=3,
            randomize_order=True,
            block_by=["task"],
            allocation_seed=seed,
        ),
    )


def test_task_blocked_allocation_is_balanced_and_reproducible() -> None:
    tasks = [task("task-a"), task("task-b")]
    first = build_allocation_plan(randomized_experiment(), tasks)
    second = build_allocation_plan(randomized_experiment(), tasks)

    assert first == second
    assert len(first) == 12
    assert [item.index for item in first] == list(range(1, 13))
    assert {(item.task_id, item.variant_id) for item in first} == {
        ("task-a", "codex"),
        ("task-a", "claude"),
        ("task-b", "codex"),
        ("task-b", "claude"),
    }
    blocks = {item.block_id for item in first}
    assert len(blocks) == 6
    for block_id in blocks:
        block = [item for item in first if item.block_id == block_id]
        assert len(block) == 2
        assert len({item.task_id for item in block}) == 1
        assert {item.variant_id for item in block} == {"codex", "claude"}


def test_randomized_allocation_generates_and_reuses_seed() -> None:
    experiment = randomized_experiment(seed=None)

    first = build_allocation_plan(experiment, [task("task-a"), task("task-b")])
    generated_seed = experiment.design.allocation_seed
    second = build_allocation_plan(experiment, [task("task-a"), task("task-b")])

    assert generated_seed is not None
    assert first == second


def test_legacy_variant_repeat_keeps_sequential_order() -> None:
    experiment = ExperimentManifest(
        id="legacy-order",
        task=Path("task.yaml"),
        variants=[
            ExperimentVariant(id="first", repeat=2),
            ExperimentVariant(id="second", repeat=1),
        ],
    )

    plan = build_allocation_plan(experiment, [task("task")])

    assert [(item.variant_id, item.repeat_index) for item in plan] == [
        ("first", 1),
        ("first", 2),
        ("second", 1),
    ]
