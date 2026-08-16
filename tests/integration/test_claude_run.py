from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from exagium.agents.claude_cli import ClaudeCliAdapter
from exagium.config import Settings
from exagium.core.models import CommandSpec, RepoSpec, TaskManifest
from exagium.core.status import RunStatus
from exagium.runner.run_service import RunService
from exagium.storage.db import create_database_engine
from exagium.storage.repositories import Storage


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


@pytest.mark.asyncio
async def test_claude_task_to_trace_to_validation_end_to_end(sandbox_path: Path) -> None:
    repo = sandbox_path / "source"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.name", "Exagium Test")
    git(repo, "config", "user.email", "exagium@example.invalid")
    (repo / "result.txt").write_text("broken", encoding="utf-8")
    git(repo, "add", "result.txt")
    git(repo, "commit", "-m", "initial")

    fake_agent = Path(__file__).parents[1] / "fixtures" / "fake_claude_agent.py"
    adapter = ClaudeCliAdapter(executable=sys.executable, print_prefix=(str(fake_agent),))
    settings = Settings.load(sandbox_path / "state")
    storage = Storage(create_database_engine(settings.database_path))
    task = TaskManifest(
        id="fake-claude-fix",
        name="Fake Claude integration",
        repo=RepoSpec(path=repo, base_ref="HEAD"),
        prompt="Fix result.txt",
        validation=[
            CommandSpec(
                name="result check",
                command=(
                    f'"{sys.executable}" -c "from pathlib import Path; '
                    "assert Path('result.txt').read_text() == 'fixed by claude'\""
                ),
            )
        ],
    )

    outcome = await RunService(settings=settings, storage=storage, adapter=adapter).execute(task)

    assert outcome.status == RunStatus.PASSED
    assert outcome.metrics["file_change_count"] == 1
    assert outcome.metrics["tokens_total"] == 16
    row = storage.get_run(outcome.run_id)
    assert row is not None
    assert row["agent_name"] == "claude"
    assert row["model_name"] == "claude-test"
    events = storage.list_events(outcome.run_id)
    assert any(event["type"] == "AGENT_MESSAGE" for event in events)
    assert any(event["type"] == "TOOL_COMPLETED" for event in events)
    assert any(event["type"] == "FILE_CHANGED" for event in events)
