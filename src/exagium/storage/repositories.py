from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from exagium.core.events import AgentEvent
from exagium.core.models import (
    AgentMetadata,
    ExperimentManifest,
    TaskManifest,
    ValidationOutcome,
)
from exagium.core.redaction import redact_text
from exagium.core.status import RunStatus, require_transition
from exagium.storage.db import initialize_database
from exagium.storage.orm import (
    AgentRow,
    ArtifactRow,
    EventRow,
    ExperimentRow,
    RunRow,
    TaskRow,
    ValidationResultRow,
)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))


class Storage:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def initialize(self) -> None:
        initialize_database(self.engine)

    def register_agent(
        self,
        metadata: AgentMetadata,
        *,
        adapter_type: str,
        executable: str | None,
    ) -> str:
        with Session(self.engine) as session:
            row = session.scalar(select(AgentRow).where(AgentRow.name == metadata.name))
            if row is None:
                row = AgentRow(
                    id=str(uuid4()),
                    name=metadata.name,
                    adapter_type=adapter_type,
                    executable=executable,
                    version=metadata.version,
                    metadata_json=_json(metadata.metadata),
                )
                session.add(row)
            else:
                row.version = metadata.version
                row.executable = executable
                row.metadata_json = _json(metadata.metadata)
            session.commit()
            return row.id

    def register_task(self, task: TaskManifest) -> None:
        configuration = {
            "setup": [item.model_dump() for item in task.setup],
            "validation": [item.model_dump() for item in task.validation],
            "limits": task.limits.model_dump(),
            "manifest_path": str(task.manifest_path) if task.manifest_path else None,
        }
        with Session(self.engine) as session:
            row = session.get(TaskRow, task.id)
            if row is None:
                row = TaskRow(
                    id=task.id,
                    name=task.name,
                    description=task.description,
                    repo_source=str(task.repo.path),
                    base_ref=task.repo.base_ref,
                    prompt=task.prompt,
                    configuration_json=_json(configuration),
                    metadata_json=_json(task.metadata),
                )
                session.add(row)
            else:
                row.name = task.name
                row.description = task.description
                row.repo_source = str(task.repo.path)
                row.base_ref = task.repo.base_ref
                row.prompt = task.prompt
                row.configuration_json = _json(configuration)
                row.metadata_json = _json(task.metadata)
            session.commit()

    def register_experiment(self, experiment: ExperimentManifest, task_id: str) -> None:
        configuration = {
            "variants": [variant.model_dump() for variant in experiment.variants],
            "metadata": experiment.metadata,
            "manifest_path": (str(experiment.manifest_path) if experiment.manifest_path else None),
        }
        with Session(self.engine) as session:
            row = session.get(ExperimentRow, experiment.id)
            if row is None:
                row = ExperimentRow(
                    id=experiment.id,
                    name=experiment.name or experiment.id,
                    task_id=task_id,
                    created_at=utcnow(),
                    configuration_json=_json(configuration),
                )
                session.add(row)
            else:
                row.name = experiment.name or experiment.id
                row.task_id = task_id
                row.configuration_json = _json(configuration)
            session.commit()

    def create_run(
        self,
        *,
        run_id: UUID,
        task_id: str,
        agent_profile_id: str,
        agent: AgentMetadata,
        experiment_id: str | None = None,
        variant_id: str | None = None,
    ) -> None:
        with Session(self.engine) as session:
            session.add(
                RunRow(
                    id=str(run_id),
                    experiment_id=experiment_id,
                    variant_id=variant_id,
                    task_id=task_id,
                    agent_profile_id=agent_profile_id,
                    status=RunStatus.QUEUED,
                    agent_name=agent.name,
                    agent_version=agent.version,
                    model_name=agent.model_name,
                    provider_name=agent.provider_name,
                )
            )
            session.commit()

    def transition_run(self, run_id: UUID, target: RunStatus, **values: Any) -> None:
        with Session(self.engine) as session:
            row = session.get(RunRow, str(run_id))
            if row is None:
                raise LookupError(f"Run not found: {run_id}")
            require_transition(RunStatus(row.status), target)
            row.status = target
            for key, value in values.items():
                if key == "metrics":
                    row.metrics_json = _json(value)
                elif hasattr(row, key):
                    setattr(row, key, value)
                else:
                    raise AttributeError(f"Unknown run field: {key}")
            session.commit()

    def add_event(self, event: AgentEvent) -> None:
        with Session(self.engine) as session:
            session.add(
                EventRow(
                    id=str(event.id),
                    run_id=str(event.run_id),
                    seq=event.seq,
                    timestamp=event.timestamp,
                    source=event.source,
                    source_event_type=event.source_event_type,
                    type=event.type,
                    payload_json=_json(event.payload),
                    raw_event_json=_json(event.raw_event) if event.raw_event is not None else None,
                )
            )
            session.commit()

    def add_validation(self, run_id: UUID, outcome: ValidationOutcome) -> str:
        result_id = str(uuid4())
        with Session(self.engine) as session:
            session.add(
                ValidationResultRow(
                    id=result_id,
                    run_id=str(run_id),
                    validator="command",
                    name=outcome.name,
                    command=outcome.command,
                    status=outcome.status,
                    exit_code=outcome.exit_code,
                    duration_ms=outcome.duration_ms,
                    stdout=redact_text(outcome.stdout),
                    stderr=redact_text(outcome.stderr),
                    metadata_json=_json({"timed_out": outcome.timed_out}),
                )
            )
            session.commit()
        return result_id

    def add_artifact(self, run_id: UUID, artifact_type: str, path: Path) -> str:
        artifact_id = str(uuid4())
        with Session(self.engine) as session:
            session.add(
                ArtifactRow(
                    id=artifact_id,
                    run_id=str(run_id),
                    type=artifact_type,
                    path=str(path),
                )
            )
            session.commit()
        return artifact_id

    def get_run(self, run_id: UUID | str) -> dict[str, Any] | None:
        with Session(self.engine) as session:
            row = session.get(RunRow, str(run_id))
            return self._run_dict(row) if row else None

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(RunRow).order_by(RunRow.started_at.desc()).limit(limit)
            ).all()
            return [self._run_dict(row) for row in rows]

    def list_agents(self) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            rows = session.scalars(select(AgentRow).order_by(AgentRow.name)).all()
            return [
                {
                    "id": row.id,
                    "name": row.name,
                    "adapter_type": row.adapter_type,
                    "executable": row.executable,
                    "version": row.version,
                    "configuration": json.loads(row.configuration_json),
                    "metadata": json.loads(row.metadata_json),
                }
                for row in rows
            ]

    def list_tasks(self) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            rows = session.scalars(select(TaskRow).order_by(TaskRow.name, TaskRow.id)).all()
            return [self._task_dict(row) for row in rows]

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with Session(self.engine) as session:
            row = session.get(TaskRow, task_id)
            return self._task_dict(row) if row else None

    def get_experiment(self, experiment_id: str) -> dict[str, Any] | None:
        with Session(self.engine) as session:
            row = session.get(ExperimentRow, experiment_id)
            return self._experiment_dict(row) if row else None

    def list_experiments(self, limit: int = 20) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(ExperimentRow).order_by(ExperimentRow.created_at.desc()).limit(limit)
            ).all()
            return [self._experiment_dict(row) for row in rows]

    def list_experiment_runs(self, experiment_id: str) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(RunRow)
                .where(RunRow.experiment_id == experiment_id)
                .order_by(RunRow.started_at, RunRow.id)
            ).all()
            return [self._run_dict(row) for row in rows]

    def list_events(self, run_id: UUID | str) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(EventRow).where(EventRow.run_id == str(run_id)).order_by(EventRow.seq)
            ).all()
            return [
                {
                    "id": row.id,
                    "run_id": row.run_id,
                    "seq": row.seq,
                    "timestamp": row.timestamp.isoformat(),
                    "source": row.source,
                    "source_event_type": row.source_event_type,
                    "type": row.type,
                    "payload": json.loads(row.payload_json),
                    "raw_event": (
                        json.loads(row.raw_event_json) if row.raw_event_json is not None else None
                    ),
                }
                for row in rows
            ]

    def list_validations(self, run_id: UUID | str) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(ValidationResultRow).where(ValidationResultRow.run_id == str(run_id))
            ).all()
            return [
                {
                    "id": row.id,
                    "name": row.name,
                    "command": row.command,
                    "status": row.status,
                    "exit_code": row.exit_code,
                    "duration_ms": row.duration_ms,
                    "stdout": row.stdout,
                    "stderr": row.stderr,
                    "metadata": json.loads(row.metadata_json),
                }
                for row in rows
            ]

    def list_artifacts(self, run_id: UUID | str) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(ArtifactRow).where(ArtifactRow.run_id == str(run_id))
            ).all()
            return [
                {
                    "id": row.id,
                    "run_id": row.run_id,
                    "type": row.type,
                    "path": row.path,
                    "metadata": json.loads(row.metadata_json),
                }
                for row in rows
            ]

    @staticmethod
    def _run_dict(row: RunRow) -> dict[str, Any]:
        return {
            "id": row.id,
            "experiment_id": row.experiment_id,
            "variant_id": row.variant_id,
            "task_id": row.task_id,
            "agent_profile_id": row.agent_profile_id,
            "status": row.status,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "ended_at": row.ended_at.isoformat() if row.ended_at else None,
            "workspace_path": row.workspace_path,
            "agent_name": row.agent_name,
            "agent_version": row.agent_version,
            "model_name": row.model_name,
            "provider_name": row.provider_name,
            "exit_code": row.exit_code,
            "validation_status": row.validation_status,
            "metrics": json.loads(row.metrics_json),
            "error": row.error,
        }

    @staticmethod
    def _experiment_dict(row: ExperimentRow) -> dict[str, Any]:
        return {
            "id": row.id,
            "name": row.name,
            "task_id": row.task_id,
            "created_at": row.created_at.isoformat(),
            "configuration": json.loads(row.configuration_json),
        }

    @staticmethod
    def _task_dict(row: TaskRow) -> dict[str, Any]:
        return {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "repo_source": row.repo_source,
            "base_ref": row.base_ref,
            "prompt": row.prompt,
            "configuration": json.loads(row.configuration_json),
            "metadata": json.loads(row.metadata_json),
        }


def utcnow() -> datetime:
    return datetime.now(UTC)
