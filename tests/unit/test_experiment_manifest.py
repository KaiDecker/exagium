from pathlib import Path

import pytest

from exagium.core.errors import ManifestError
from exagium.core.models import load_experiment_manifest


def test_load_experiment_manifest_resolves_task_relative_to_manifest(
    sandbox_path: Path,
) -> None:
    task = sandbox_path / "task.yaml"
    task.write_text("placeholder", encoding="utf-8")
    manifest = sandbox_path / "experiment.yaml"
    manifest.write_text(
        """
id: codex-stability
name: Codex stability
task: ./task.yaml
variants:
  - id: codex-default
    agent: codex
    repeat: 3
""".strip(),
        encoding="utf-8",
    )

    experiment = load_experiment_manifest(manifest)

    assert experiment.task == task.resolve()
    assert experiment.variants[0].repeat == 3
    assert experiment.variants[0].label is None


def test_load_experiment_manifest_rejects_duplicate_variant_ids(sandbox_path: Path) -> None:
    task = sandbox_path / "task.yaml"
    task.write_text("placeholder", encoding="utf-8")
    manifest = sandbox_path / "experiment.yaml"
    manifest.write_text(
        """
id: duplicate-variants
task: ./task.yaml
variants:
  - id: same
  - id: same
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ManifestError, match="variant ids must be unique"):
        load_experiment_manifest(manifest)


def test_load_v2_manifest_separates_design_and_analysis(sandbox_path: Path) -> None:
    first = sandbox_path / "first.yaml"
    second = sandbox_path / "second.yaml"
    first.write_text("placeholder", encoding="utf-8")
    second.write_text("placeholder", encoding="utf-8")
    manifest = sandbox_path / "experiment.yaml"
    manifest.write_text(
        """
id: agent-comparison
tasks:
  - ./first.yaml
  - ./second.yaml
variants:
  - id: codex
    agent: codex
  - id: claude
    agent: claude
design:
  repeats: 4
  randomize_order: true
  block_by: [task]
  allocation_seed: 20260815
analysis:
  primary_metric:
    type: success
  secondary_metrics: [duration_ms, tokens_total]
  confidence_level: 0.9
  bootstrap:
    enabled: true
    cluster_by: task
    samples: 1000
""".strip(),
        encoding="utf-8",
    )

    experiment = load_experiment_manifest(manifest)

    assert experiment.task is None
    assert experiment.tasks == [first.resolve(), second.resolve()]
    assert experiment.repeats_for(experiment.variants[0]) == 4
    assert experiment.design.block_by == ["task"]
    assert experiment.design.allocation_seed == 20260815
    assert experiment.analysis.confidence_level == 0.9
    assert experiment.analysis.bootstrap.samples == 1000


def test_load_manifest_rejects_mixed_legacy_and_v2_task_fields(sandbox_path: Path) -> None:
    task = sandbox_path / "task.yaml"
    task.write_text("placeholder", encoding="utf-8")
    manifest = sandbox_path / "experiment.yaml"
    manifest.write_text(
        """
id: mixed-task-fields
task: ./task.yaml
tasks: [./task.yaml]
variants:
  - id: codex
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ManifestError, match="use either task or tasks"):
        load_experiment_manifest(manifest)


def test_task_blocking_rejects_unbalanced_variant_repeats(sandbox_path: Path) -> None:
    task = sandbox_path / "task.yaml"
    task.write_text("placeholder", encoding="utf-8")
    manifest = sandbox_path / "experiment.yaml"
    manifest.write_text(
        """
id: unbalanced-blocks
tasks: [./task.yaml]
variants:
  - id: codex
    repeat: 2
  - id: claude
    repeat: 3
design:
  block_by: [task]
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ManifestError, match="task-blocked variants must use equal repeat counts"):
        load_experiment_manifest(manifest)
