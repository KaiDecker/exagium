from __future__ import annotations

from collections.abc import Sequence
from statistics import median

from exagium.core.models import (
    ExperimentManifest,
    ExperimentOutcome,
    ExperimentVariant,
    ExperimentVariantSummary,
    RunOutcome,
)
from exagium.core.status import RunStatus


def _median(values: Sequence[int | float | None]) -> float | None:
    numeric = [
        value for value in values if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    return float(median(numeric)) if numeric else None


def summarize_variant(
    variant: ExperimentVariant,
    outcomes: Sequence[RunOutcome],
) -> ExperimentVariantSummary:
    total = len(outcomes)
    passed = sum(outcome.status == RunStatus.PASSED for outcome in outcomes)
    return ExperimentVariantSummary(
        id=variant.id,
        label=variant.label or variant.id,
        agent=variant.agent,
        runs=total,
        passed=passed,
        failed=sum(outcome.status == RunStatus.FAILED for outcome in outcomes),
        errors=sum(outcome.status == RunStatus.ERROR for outcome in outcomes),
        cancelled=sum(outcome.status == RunStatus.CANCELLED for outcome in outcomes),
        success_rate=round((passed / total * 100) if total else 0.0, 2),
        median_duration_ms=_median([outcome.duration_ms for outcome in outcomes]),
        median_tokens=_median([outcome.metrics.get("tokens_total") for outcome in outcomes]),
    )


def summarize_experiment(
    experiment: ExperimentManifest,
    task_id: str,
    outcomes_by_variant: Sequence[tuple[ExperimentVariant, Sequence[RunOutcome]]],
) -> ExperimentOutcome:
    summaries = [summarize_variant(variant, outcomes) for variant, outcomes in outcomes_by_variant]
    outcomes = [
        outcome
        for _variant, variant_outcomes in outcomes_by_variant
        for outcome in variant_outcomes
    ]
    total = len(outcomes)
    passed = sum(outcome.status == RunStatus.PASSED for outcome in outcomes)
    return ExperimentOutcome(
        experiment_id=experiment.id,
        name=experiment.name or experiment.id,
        task_id=task_id,
        runs=total,
        passed=passed,
        failed=sum(outcome.status == RunStatus.FAILED for outcome in outcomes),
        errors=sum(outcome.status == RunStatus.ERROR for outcome in outcomes),
        cancelled=sum(outcome.status == RunStatus.CANCELLED for outcome in outcomes),
        success_rate=round((passed / total * 100) if total else 0.0, 2),
        median_duration_ms=_median([outcome.duration_ms for outcome in outcomes]),
        median_tokens=_median([outcome.metrics.get("tokens_total") for outcome in outcomes]),
        variants=summaries,
        run_ids=[outcome.run_id for outcome in outcomes],
    )
