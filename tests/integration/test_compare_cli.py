from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

from typer.testing import CliRunner

from exagium.cli.main import app
from exagium.config import Settings
from exagium.core.events import AgentEvent, EventType
from exagium.core.models import AgentMetadata, CommandSpec, RepoSpec, TaskManifest
from exagium.core.status import RunStatus
from exagium.storage.db import create_database_engine
from exagium.storage.repositories import Storage


def add_event(
    storage: Storage,
    run_id: UUID,
    seq: int,
    event_type: EventType,
    payload: dict[str, object],
) -> None:
    storage.add_event(
        AgentEvent(
            run_id=run_id,
            seq=seq,
            type=event_type,
            source="fake",
            payload=payload,
        )
    )


def create_terminal_run(
    storage: Storage,
    task: TaskManifest,
    agent_profile_id: str,
    status: RunStatus,
    operations: list[tuple[EventType, dict[str, object]]],
) -> UUID:
    run_id = uuid4()
    storage.create_run(
        run_id=run_id,
        task_id=task.id,
        agent_profile_id=agent_profile_id,
        agent=AgentMetadata(name="fake", version="1.0"),
    )
    storage.transition_run(run_id, RunStatus.PREPARING)
    storage.transition_run(run_id, RunStatus.RUNNING)
    for seq, (event_type, payload) in enumerate(operations, start=1):
        add_event(storage, run_id, seq, event_type, payload)
    storage.transition_run(run_id, RunStatus.VALIDATING)
    storage.transition_run(run_id, status)
    return run_id


def command(command_id: str, value: str) -> list[tuple[EventType, dict[str, object]]]:
    payload = {"id": command_id, "command": value}
    return [
        (EventType.COMMAND_STARTED, payload),
        (EventType.COMMAND_COMPLETED, {**payload, "exit_code": 0}),
    ]


def test_compare_cli_reports_first_semantic_divergence(sandbox_path: Path) -> None:
    repo = sandbox_path / "repo"
    repo.mkdir()
    settings = Settings.load(sandbox_path / "state")
    storage = Storage(create_database_engine(settings.database_path))
    storage.initialize()
    task = TaskManifest(
        id="compare-task",
        name="Compare task",
        repo=RepoSpec(path=repo),
        prompt="Fix it",
        validation=[CommandSpec(command="check")],
    )
    storage.register_task(task)
    agent_profile_id = storage.register_agent(
        AgentMetadata(name="fake", version="1.0"),
        adapter_type="fake",
        executable="fake",
    )
    shared = [
        *command("search", 'rg "needle" src'),
        *command("read", "Get-Content src/app.py"),
        (EventType.FILE_CHANGED, {"path": "src/app.py"}),
    ]
    run_a = create_terminal_run(
        storage,
        task,
        agent_profile_id,
        RunStatus.PASSED,
        [*shared, *command("test", "python -m pytest")],
    )
    run_b = create_terminal_run(
        storage,
        task,
        agent_profile_id,
        RunStatus.FAILED,
        [*shared, (EventType.FILE_CHANGED, {"path": "src/other.py"})],
    )

    result = CliRunner().invoke(
        app,
        ["compare", str(run_a), str(run_b), "--home", str(settings.home)],
    )

    assert result.exit_code == 0, result.output
    assert "First divergence: step 4" in result.output
    assert "Run A: TEST" in result.output
    assert "Run B: EDIT" in result.output
