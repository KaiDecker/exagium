from pathlib import Path

import pytest

from exagium.core.errors import ManifestError
from exagium.core.models import load_task_manifest


def test_load_task_manifest_resolves_repo_relative_to_manifest(sandbox_path: Path) -> None:
    repo = sandbox_path / "repo"
    repo.mkdir()
    manifest = sandbox_path / "task.yaml"
    manifest.write_text(
        """
id: task-1
name: Fix a bug
repo:
  path: ./repo
  base_ref: main
prompt: Fix it.
validation:
  - command: python -m pytest
""".strip(),
        encoding="utf-8",
    )

    task = load_task_manifest(manifest)

    assert task.repo.path == repo.resolve()
    assert task.validation[0].timeout_seconds == 120
    assert task.limits.run_timeout_seconds == 900


def test_load_task_manifest_rejects_missing_validation(sandbox_path: Path) -> None:
    repo = sandbox_path / "repo"
    repo.mkdir()
    manifest = sandbox_path / "task.yaml"
    manifest.write_text(
        f"id: task-1\nname: Bad task\nrepo:\n  path: {repo.as_posix()}\nprompt: Fix it.\n",
        encoding="utf-8",
    )

    with pytest.raises(ManifestError, match="validation"):
        load_task_manifest(manifest)
