from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from exagium.config import Settings
from exagium.core.events import EventDraft, EventType
from exagium.core.models import (
    AgentDoctorResult,
    AgentMetadata,
    AgentRunResult,
    CommandSpec,
    RepoSpec,
    TaskManifest,
    ValidationOutcome,
)
from exagium.core.status import RunStatus
from exagium.runner.run_service import RunService
from exagium.storage.db import create_database_engine
from exagium.storage.repositories import Storage


class FakeAdapter:
    name = "fake"
    executable = "fake-agent"

    async def doctor(self) -> AgentDoctorResult:
        return AgentDoctorResult(available=True, executable=self.executable, version="1.0")

    async def metadata(self) -> AgentMetadata:
        return AgentMetadata(name=self.name, version="1.0")

    async def run(self, request, emit) -> AgentRunResult:
        await emit(
            EventDraft(
                type=EventType.COMMAND_STARTED,
                source="fake",
                payload={"command": "inspect"},
                raw_event={"type": "command.started", "token": "must-not-persist"},
            )
        )
        await emit(
            EventDraft(
                type=EventType.USAGE_REPORTED,
                source="fake",
                payload={"input_tokens": 40, "output_tokens": 2},
            )
        )
        return AgentRunResult(exit_code=0, duration_ms=1)

    async def cancel(self, run_id: str) -> None:
        return None


@dataclass
class FakeWorkspace:
    path: Path

    async def cleanup(self) -> None:
        return None


class FakeWorkspaceManager:
    def __init__(self, path: Path) -> None:
        self.path = path

    async def prepare(self, **kwargs) -> FakeWorkspace:
        return FakeWorkspace(self.path)

    async def capture_diff(self, workspace: FakeWorkspace) -> str:
        return "diff --git a/file b/file\n"


class FakeValidator:
    def __init__(self, passed: bool) -> None:
        self.passed = passed

    async def run(self, spec: CommandSpec, workspace: Path) -> ValidationOutcome:
        return ValidationOutcome(
            name=spec.name or spec.command,
            command=spec.command,
            status="PASSED" if self.passed else "FAILED",
            exit_code=0 if self.passed else 1,
            duration_ms=1,
            stdout="",
            stderr="",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("validation_passed", "expected_status"),
    [(True, RunStatus.PASSED), (False, RunStatus.FAILED)],
)
async def test_run_status_is_decided_by_independent_validation(
    sandbox_path: Path,
    validation_passed: bool,
    expected_status: RunStatus,
) -> None:
    repo = sandbox_path / "repo"
    repo.mkdir()
    settings = Settings.load(sandbox_path / "state")
    storage = Storage(create_database_engine(settings.database_path))
    service = RunService(settings=settings, storage=storage, adapter=FakeAdapter())
    service.workspace_manager = FakeWorkspaceManager(repo)
    service.validator = FakeValidator(validation_passed)
    task = TaskManifest(
        id=f"validation-{validation_passed}",
        name="Validation decides",
        repo=RepoSpec(path=repo, base_ref="HEAD"),
        prompt="Do the work",
        validation=[CommandSpec(name="ground truth", command="check")],
    )

    outcome = await service.execute(task)

    assert outcome.status == expected_status
    assert outcome.metrics["run_success"] is validation_passed
    assert outcome.metrics["command_count"] == 1
    assert outcome.metrics["tokens_total"] == 42
    raw = storage.list_events(outcome.run_id)[1]["raw_event"]
    assert raw["token"] == "[REDACTED]"
