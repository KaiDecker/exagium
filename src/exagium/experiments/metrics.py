from __future__ import annotations

from collections.abc import Sequence
from statistics import median

from exagium.core.models import (
    ConfidenceIntervalSummary,
    ExperimentManifest,
    ExperimentOutcome,
    ExperimentVariant,
    ExperimentVariantSummary,
    RunOutcome,
)
from exagium.core.status import RunStatus
from exagium.statistics.intervals import wilson_interval


def _median(values: Sequence[int | float | None]) -> float | None:
    numeric = [
        value for value in values if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    return float(median(numeric)) if numeric else None


def _success_interval(
    passed: int,
    evaluable_runs: int,
    confidence_level: float,
) -> ConfidenceIntervalSummary | None:
    interval = wilson_interval(passed, evaluable_runs, confidence_level=confidence_level)
    if interval is None:
        return None
    return ConfidenceIntervalSummary(
        lower=round(interval.lower * 100, 2),
        upper=round(interval.upper * 100, 2),
        confidence_level=interval.confidence_level,
    )


def summarize_variant(
    variant: ExperimentVariant,
    outcomes: Sequence[RunOutcome],
    *,
    confidence_level: float = 0.95,
) -> ExperimentVariantSummary:
    total = len(outcomes)
    passed = sum(outcome.status == RunStatus.PASSED for outcome in outcomes)
    failed = sum(outcome.status == RunStatus.FAILED for outcome in outcomes)
    evaluable_runs = passed + failed
    return ExperimentVariantSummary(
        id=variant.id,
        label=variant.label or variant.id,
        agent=variant.agent,
        runs=total,
        passed=passed,
        failed=failed,
        errors=sum(outcome.status == RunStatus.ERROR for outcome in outcomes),
        cancelled=sum(outcome.status == RunStatus.CANCELLED for outcome in outcomes),
        evaluable_runs=evaluable_runs,
        success_rate=(round(passed / evaluable_runs * 100, 2) if evaluable_runs else None),
        success_interval=_success_interval(passed, evaluable_runs, confidence_level),
        median_duration_ms=_median([outcome.duration_ms for outcome in outcomes]),
        median_tokens=_median([outcome.metrics.get("tokens_total") for outcome in outcomes]),
    )


def summarize_experiment(
    experiment: ExperimentManifest,
    task_ids: str | Sequence[str],
    outcomes_by_variant: Sequence[tuple[ExperimentVariant, Sequence[RunOutcome]]],
) -> ExperimentOutcome:
    resolved_task_ids = [task_ids] if isinstance(task_ids, str) else list(task_ids)
    if not resolved_task_ids:
        raise ValueError("at least one task id is required")
    confidence_level = experiment.analysis.confidence_level
    summaries = [
        summarize_variant(variant, outcomes, confidence_level=confidence_level)
        for variant, outcomes in outcomes_by_variant
    ]
    outcomes = [
        outcome
        for _variant, variant_outcomes in outcomes_by_variant
        for outcome in variant_outcomes
    ]
    total = len(outcomes)
    passed = sum(outcome.status == RunStatus.PASSED for outcome in outcomes)
    failed = sum(outcome.status == RunStatus.FAILED for outcome in outcomes)
    evaluable_runs = passed + failed
    return ExperimentOutcome(
        experiment_id=experiment.id,
        name=experiment.name or experiment.id,
        task_id=resolved_task_ids[0],
        task_ids=resolved_task_ids,
        runs=total,
        passed=passed,
        failed=failed,
        errors=sum(outcome.status == RunStatus.ERROR for outcome in outcomes),
        cancelled=sum(outcome.status == RunStatus.CANCELLED for outcome in outcomes),
        evaluable_runs=evaluable_runs,
        success_rate=(round(passed / evaluable_runs * 100, 2) if evaluable_runs else None),
        success_interval=_success_interval(passed, evaluable_runs, confidence_level),
        median_duration_ms=_median([outcome.duration_ms for outcome in outcomes]),
        median_tokens=_median([outcome.metrics.get("tokens_total") for outcome in outcomes]),
        variants=summaries,
        run_ids=[outcome.run_id for outcome in outcomes],
    )
