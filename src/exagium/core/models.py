from __future__ import annotations

from pathlib import Path
from typing import Any, Literal
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
    repeat: int | None = Field(default=None, ge=1, le=1000)
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


class ExperimentDesign(BaseModel):
    """描述运行如何分配；它不试图控制 Agent 自身的随机性。"""

    repeats: int = Field(default=1, ge=1, le=1000)
    randomize_order: bool = False
    block_by: list[Literal["task"]] = Field(default_factory=list)
    allocation_seed: int | None = Field(default=None, ge=0, le=2**63 - 1)

    @field_validator("block_by")
    @classmethod
    def block_fields_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("block_by fields must be unique")
        return value

    @model_validator(mode="after")
    def seed_requires_randomization(self) -> ExperimentDesign:
        if self.allocation_seed is not None and not self.randomize_order:
            raise ValueError("allocation_seed requires randomize_order")
        return self


class PrimaryMetricSpec(BaseModel):
    type: Literal["success"] = "success"


class BootstrapSpec(BaseModel):
    enabled: bool = True
    cluster_by: Literal["task"] = "task"
    samples: int = Field(default=5000, ge=100, le=100_000)


class AnalysisPlan(BaseModel):
    """描述结果如何分析，与运行分配配置保持分离。"""

    primary_metric: PrimaryMetricSpec = Field(default_factory=PrimaryMetricSpec)
    secondary_metrics: list[
        Literal["duration_ms", "command_count", "tool_call_count", "tokens_total"]
    ] = Field(
        default_factory=lambda: [
            "duration_ms",
            "command_count",
            "tool_call_count",
            "tokens_total",
        ]
    )
    confidence_level: float = Field(default=0.95, gt=0, lt=1)
    bootstrap: BootstrapSpec = Field(default_factory=BootstrapSpec)

    @field_validator("secondary_metrics")
    @classmethod
    def secondary_metrics_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("secondary metrics must be unique")
        return value


class ExperimentManifest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str
    name: str | None = None
    task: Path | None = None
    tasks: list[Path] = Field(default_factory=list)
    variants: list[ExperimentVariant] = Field(min_length=1)
    design: ExperimentDesign = Field(default_factory=ExperimentDesign)
    analysis: AnalysisPlan = Field(default_factory=AnalysisPlan)
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
    def experiment_structure_must_be_valid(self) -> ExperimentManifest:
        ids = [variant.id for variant in self.variants]
        if len(ids) != len(set(ids)):
            raise ValueError("variant ids must be unique")
        if self.task is None and not self.tasks:
            raise ValueError("one of task or tasks is required")
        if self.task is not None and self.tasks:
            raise ValueError("use either task or tasks, not both")
        if len(self.tasks) != len(set(self.tasks)):
            raise ValueError("task paths must be unique")
        if "task" in self.design.block_by:
            repeats = {self.repeats_for(variant) for variant in self.variants}
            if len(repeats) != 1:
                raise ValueError("task-blocked variants must use equal repeat counts")
        return self

    @property
    def task_paths(self) -> list[Path]:
        """统一读取旧版单 Task 与 V2 多 Task 配置。"""

        return list(self.tasks) if self.tasks else [self.task] if self.task is not None else []

    def repeats_for(self, variant: ExperimentVariant) -> int:
        """变体可以覆盖全局重复次数，旧版 YAML 因而仍然有效。"""

        return variant.repeat if variant.repeat is not None else self.design.repeats


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
    task_ids: list[str]
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
    resolved_tasks = [
        task_path
        if task_path.is_absolute()
        else (manifest_path.parent / task_path).resolve()
        for task_path in experiment.task_paths
    ]
    if experiment.task is not None:
        experiment.task = resolved_tasks[0]
    else:
        experiment.tasks = resolved_tasks
    experiment.manifest_path = manifest_path
    for task_path in resolved_tasks:
        if not task_path.is_file():
            raise ManifestError(f"Experiment task manifest does not exist: {task_path}")
    return experiment
