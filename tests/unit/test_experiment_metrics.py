from pathlib import Path
from uuid import uuid4

from exagium.core.models import (
    ExperimentManifest,
    ExperimentVariant,
    RunOutcome,
)
from exagium.core.status import RunStatus
from exagium.experiments.metrics import summarize_experiment


def outcome(status: RunStatus, duration_ms: int, tokens: int | None) -> RunOutcome:
    return RunOutcome(
        run_id=uuid4(),
        status=status,
        duration_ms=duration_ms,
        metrics={"tokens_total": tokens},
    )


def test_experiment_metrics_count_statuses_and_ignore_missing_usage() -> None:
    first = ExperimentVariant(id="first", agent="codex", repeat=2)
    second = ExperimentVariant(id="second", agent="codex", label="Second", repeat=1)
    experiment = ExperimentManifest(
        id="metrics",
        name="Metrics",
        task=Path("task.yaml"),
        variants=[first, second],
    )
    results = [
        (first, [outcome(RunStatus.PASSED, 100, 10), outcome(RunStatus.FAILED, 300, None)]),
        (second, [outcome(RunStatus.ERROR, 200, 30)]),
    ]

    summary = summarize_experiment(experiment, "task-1", results)

    assert summary.runs == 3
    assert summary.passed == 1
    assert summary.failed == 1
    assert summary.errors == 1
    assert summary.evaluable_runs == 2
    assert summary.success_rate == 50
    assert summary.success_interval is not None
    assert summary.success_interval.lower == 9.45
    assert summary.success_interval.upper == 90.55
    assert summary.median_duration_ms == 200
    assert summary.median_tokens == 20
    assert summary.variants[0].success_rate == 50
    assert summary.variants[0].evaluable_runs == 2
    assert summary.variants[0].success_interval is not None
    assert summary.variants[1].evaluable_runs == 0
    assert summary.variants[1].success_rate is None
    assert summary.variants[1].success_interval is None
    assert summary.variants[1].label == "Second"
