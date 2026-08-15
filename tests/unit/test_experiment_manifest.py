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
