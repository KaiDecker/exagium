from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from exagium.agents.codex_cli import CodexCliAdapter
from exagium.config import Settings
from exagium.core.models import CommandSpec, RepoSpec, TaskManifest
from exagium.core.status import RunStatus
from exagium.runner.run_service import RunService
from exagium.storage.db import create_database_engine
from exagium.storage.repositories import Storage


def skip_if_process_creation_is_blocked(error: str | None) -> None:
    if error and ("WinError 5" in error or "拒绝访问" in error):
        pytest.skip("The execution sandbox blocks subprocess creation from tests")


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


@pytest.mark.asyncio
async def test_task_to_trace_to_validation_end_to_end(sandbox_path: Path) -> None:
    repo = sandbox_path / "source"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.name", "Exagium Test")
    git(repo, "config", "user.email", "exagium@example.invalid")
    (repo / "result.txt").write_text("broken", encoding="utf-8")
    git(repo, "add", "result.txt")
    git(repo, "commit", "-m", "initial")

    fake_agent = Path(__file__).parents[1] / "fixtures" / "fake_agent.py"
    adapter = CodexCliAdapter(executable=sys.executable, exec_prefix=(str(fake_agent),))
    settings = Settings.load(sandbox_path / "state")
    storage = Storage(create_database_engine(settings.database_path))
    task = TaskManifest(
        id="fake-fix",
        name="Fake agent integration",
        repo=RepoSpec(path=repo, base_ref="HEAD"),
        prompt="Fix result.txt",
        validation=[
            CommandSpec(
                name="result check",
                command=(
                    f'"{sys.executable}" -c "import os; from pathlib import Path; '
                    "path = Path(os.environ['EXAGIUM_WORKSPACE']) / 'result.txt'; "
                    "assert path.read_text() == 'fixed'\""
                ),
            )
        ],
    )
    service = RunService(settings=settings, storage=storage, adapter=adapter)
    service.validator = service.validator.__class__(use_workspace_as_cwd=False)

    outcome = await service.execute(task)
    skip_if_process_creation_is_blocked(outcome.error)

    assert outcome.status == RunStatus.PASSED
    assert outcome.validation_status == "PASSED"
    assert outcome.workspace_path is not None
    assert not outcome.workspace_path.exists()
    assert outcome.metrics["command_count"] == 1
    assert outcome.metrics["file_change_count"] == 1
    assert outcome.metrics["tokens_total"] == 15

    row = storage.get_run(outcome.run_id)
    assert row is not None
    assert row["status"] == "PASSED"
    events = storage.list_events(outcome.run_id)
    assert any(event["type"] == "AGENT_MESSAGE" for event in events)
    assert any(event["raw_event"] == "a future non-json event" for event in events)
    validations = storage.list_validations(outcome.run_id)
    assert validations[0]["status"] == "PASSED"
    diff_path = settings.artifacts_path / str(outcome.run_id) / "diff.patch"
    assert diff_path.is_file()
    assert "+fixed" in diff_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_agent_success_does_not_override_failed_validation(sandbox_path: Path) -> None:
    repo = sandbox_path / "source"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.name", "Exagium Test")
    git(repo, "config", "user.email", "exagium@example.invalid")
    (repo / "result.txt").write_text("broken", encoding="utf-8")
    git(repo, "add", "result.txt")
    git(repo, "commit", "-m", "initial")

    fake_agent = Path(__file__).parents[1] / "fixtures" / "fake_agent.py"
    adapter = CodexCliAdapter(executable=sys.executable, exec_prefix=(str(fake_agent),))
    settings = Settings.load(sandbox_path / "state")
    storage = Storage(create_database_engine(settings.database_path))
    task = TaskManifest(
        id="independent-ground-truth",
        name="Independent validation",
        repo=RepoSpec(path=repo, base_ref="HEAD"),
        prompt="Claim success",
        validation=[CommandSpec(command=f'"{sys.executable}" -c "raise SystemExit(1)"')],
    )

    service = RunService(settings=settings, storage=storage, adapter=adapter)
    service.validator = service.validator.__class__(use_workspace_as_cwd=False)
    outcome = await service.execute(task)
    skip_if_process_creation_is_blocked(outcome.error)

    assert outcome.agent_exit_code == 0
    assert outcome.status == RunStatus.FAILED
    assert outcome.validation_status == "FAILED"
