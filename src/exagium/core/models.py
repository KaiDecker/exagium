from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from exagium.core.errors import ManifestError
from exagium.core.status import RunStatus


class RepoSpec(BaseModel):
    path: Path
    base_ref: str = "HEAD"


class CommandSpec(BaseModel):
    name: str | None = None
    command: str
    timeout_seconds: int = Field(default=120, gt=0)
    expected_exit_code: int = 0

    @field_validator("command")
    @classmethod
    def command_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("command must not be blank")
        return value


class LimitsSpec(BaseModel):
    run_timeout_seconds: int = Field(default=900, gt=0)


class TaskManifest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str
    name: str
    description: str | None = None
    repo: RepoSpec
    prompt: str
    setup: list[CommandSpec] = Field(default_factory=list)
    validation: list[CommandSpec] = Field(min_length=1)
    limits: LimitsSpec = Field(default_factory=LimitsSpec)
    metadata: dict[str, Any] = Field(default_factory=dict)
    manifest_path: Path | None = Field(default=None, exclude=True)

    @field_validator("id", "name", "prompt")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class ExperimentVariant(BaseModel):
    id: str
    agent: str = "codex"
    label: str | None = None
    repeat: int = Field(default=1, ge=1, le=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", "agent")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("label")
    @classmethod
    def label_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be blank")
        return value


class ExperimentManifest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str
    name: str | None = None
    task: Path
    variants: list[ExperimentVariant] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    manifest_path: Path | None = Field(default=None, exclude=True)

    @field_validator("id")
    @classmethod
    def id_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def variant_ids_must_be_unique(self) -> ExperimentManifest:
        ids = [variant.id for variant in self.variants]
        if len(ids) != len(set(ids)):
            raise ValueError("variant ids must be unique")
        return self


class AgentMetadata(BaseModel):
    name: str
    version: str | None = None
    model_name: str | None = None
    provider_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentDoctorResult(BaseModel):
    available: bool
    executable: str
    version: str | None = None
    error: str | None = None


class AgentRunRequest(BaseModel):
    run_id: UUID
    prompt: str
    workspace: Path
    timeout_seconds: int


class AgentRunResult(BaseModel):
    exit_code: int
    duration_ms: int
    stderr: str = ""
    timed_out: bool = False


class ValidationOutcome(BaseModel):
    name: str
    command: str
    status: str
    exit_code: int | None
    duration_ms: int
    stdout: str
    stderr: str
    timed_out: bool = False


class RunOutcome(BaseModel):
    run_id: UUID
    status: RunStatus
    agent_exit_code: int | None = None
    duration_ms: int
    validation_status: str | None = None
    workspace_path: Path | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class ExperimentVariantSummary(BaseModel):
    id: str
    label: str
    agent: str
    runs: int
    passed: int
    failed: int
    errors: int
    cancelled: int
    success_rate: float
    median_duration_ms: float | None = None
    median_tokens: float | None = None


class ExperimentOutcome(BaseModel):
    experiment_id: str
    name: str
    task_id: str
    runs: int
    passed: int
    failed: int
    errors: int
    cancelled: int
    success_rate: float
    median_duration_ms: float | None = None
    median_tokens: float | None = None
    variants: list[ExperimentVariantSummary]
    run_ids: list[UUID]


def load_task_manifest(path: Path) -> TaskManifest:
    manifest_path = path.resolve()
    try:
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ManifestError(f"Cannot read task manifest {manifest_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ManifestError(f"Task manifest {manifest_path} must contain a YAML mapping")
    try:
        task = TaskManifest.model_validate(data)
    except ValidationError as exc:
        raise ManifestError(f"Invalid task manifest {manifest_path}: {exc}") from exc
    repo_path = task.repo.path
    if not repo_path.is_absolute():
        repo_path = (manifest_path.parent / repo_path).resolve()
    task.repo.path = repo_path
    task.manifest_path = manifest_path
    if not repo_path.is_dir():
        raise ManifestError(f"Task repository does not exist: {repo_path}")
    return task


def load_experiment_manifest(path: Path) -> ExperimentManifest:
    manifest_path = path.resolve()
    try:
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ManifestError(f"Cannot read experiment manifest {manifest_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ManifestError(f"Experiment manifest {manifest_path} must contain a YAML mapping")
    try:
        experiment = ExperimentManifest.model_validate(data)
    except ValidationError as exc:
        raise ManifestError(f"Invalid experiment manifest {manifest_path}: {exc}") from exc
    task_path = experiment.task
    if not task_path.is_absolute():
        task_path = (manifest_path.parent / task_path).resolve()
    experiment.task = task_path
    experiment.manifest_path = manifest_path
    if not task_path.is_file():
        raise ManifestError(f"Experiment task manifest does not exist: {task_path}")
    return experiment
