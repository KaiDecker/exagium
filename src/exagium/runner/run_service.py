from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from exagium.agents.base import AgentAdapter
from exagium.config import Settings
from exagium.core.errors import ExagiumError
from exagium.core.events import EventDraft, EventType
from exagium.core.models import AgentRunRequest, RunOutcome, TaskManifest
from exagium.core.status import TERMINAL_STATUSES, RunStatus
from exagium.runner.workspace import RunWorkspace, WorkspaceManager
from exagium.storage.repositories import Storage
from exagium.trace.recorder import TraceRecorder
from exagium.validation.command import CommandValidator


class RunService:
    def __init__(
        self,
        *,
        settings: Settings,
        storage: Storage,
        adapter: AgentAdapter,
    ) -> None:
        self.settings = settings
        self.storage = storage
        self.adapter = adapter
        self.workspace_manager = WorkspaceManager(settings.workspaces_path)
        self.validator = CommandValidator()

    async def execute(
        self,
        task: TaskManifest,
        *,
        keep_workspace: bool = False,
        timeout_seconds: int | None = None,
        experiment_id: str | None = None,
        variant_id: str | None = None,
    ) -> RunOutcome:
        started = time.perf_counter()
        run_id = uuid4()
        workspace: RunWorkspace | None = None
        agent_exit_code: int | None = None
        validation_status: str | None = None
        error: str | None = None
        metrics: dict[str, Any] = {}

        self.settings.ensure_directories()
        self.storage.initialize()
        agent_metadata = await self.adapter.metadata()
        agent_profile_id = self.storage.register_agent(
            agent_metadata,
            adapter_type=self.adapter.__class__.__name__,
            executable=getattr(self.adapter, "executable", None),
        )
        self.storage.register_task(task)
        self.storage.create_run(
            run_id=run_id,
            task_id=task.id,
            agent_profile_id=agent_profile_id,
            agent=agent_metadata,
            experiment_id=experiment_id,
            variant_id=variant_id,
        )
        recorder = TraceRecorder(self.storage, run_id)

        try:
            self.storage.transition_run(run_id, RunStatus.PREPARING, started_at=datetime.now(UTC))
            workspace = await self.workspace_manager.prepare(
                run_id=run_id,
                source_repo=task.repo.path,
                base_ref=task.repo.base_ref,
                keep=keep_workspace,
            )
            for setup in task.setup:
                setup_outcome = await self.validator.run(setup, workspace.path)
                if setup_outcome.status != "PASSED":
                    raise ExagiumError(
                        f"Setup command failed: {setup.command}\n{setup_outcome.stderr.strip()}"
                    )

            self.storage.transition_run(
                run_id,
                RunStatus.RUNNING,
                workspace_path=str(workspace.path),
            )
            await recorder.emit(
                EventDraft(
                    type=EventType.RUN_STARTED,
                    source="exagium",
                    payload={"task_id": task.id, "agent": self.adapter.name},
                )
            )
            agent_result = await self.adapter.run(
                AgentRunRequest(
                    run_id=run_id,
                    prompt=task.prompt,
                    workspace=workspace.path,
                    timeout_seconds=timeout_seconds or task.limits.run_timeout_seconds,
                ),
                recorder.emit,
            )
            agent_exit_code = agent_result.exit_code

            self.storage.transition_run(run_id, RunStatus.VALIDATING, exit_code=agent_exit_code)
            validation_passed = True
            for validation in task.validation:
                await recorder.emit(
                    EventDraft(
                        type=EventType.VALIDATION_STARTED,
                        source="exagium",
                        payload={"name": validation.name, "command": validation.command},
                    )
                )
                outcome = await self.validator.run(validation, workspace.path)
                self.storage.add_validation(run_id, outcome)
                validation_passed = validation_passed and outcome.status == "PASSED"
                await recorder.emit(
                    EventDraft(
                        type=EventType.VALIDATION_COMPLETED,
                        source="exagium",
                        payload={
                            "name": outcome.name,
                            "status": outcome.status,
                            "exit_code": outcome.exit_code,
                            "duration_ms": outcome.duration_ms,
                            "timed_out": outcome.timed_out,
                        },
                    )
                )
            validation_status = "PASSED" if validation_passed else "FAILED"

            diff = await self.workspace_manager.capture_diff(workspace)
            artifact_dir = self.settings.artifacts_path / str(run_id)
            artifact_dir.mkdir(parents=True, exist_ok=True)
            diff_path = artifact_dir / "diff.patch"
            diff_path.write_text(diff, encoding="utf-8")
            self.storage.add_artifact(run_id, "git_diff", diff_path)

            events = self.storage.list_events(run_id)
            metrics = self._calculate_metrics(events, started)
            if agent_result.timed_out:
                error = "Agent process timed out"
                final_status = RunStatus.ERROR
            elif agent_exit_code != 0:
                error = agent_result.stderr.strip() or f"Agent exited with code {agent_exit_code}"
                final_status = RunStatus.ERROR
            elif validation_passed:
                final_status = RunStatus.PASSED
            else:
                final_status = RunStatus.FAILED

            await recorder.emit(
                EventDraft(
                    type=(
                        EventType.RUN_FINISHED
                        if final_status == RunStatus.PASSED
                        else EventType.RUN_FAILED
                    ),
                    source="exagium",
                    payload={"status": final_status, "validation_status": validation_status},
                )
            )
            metrics = self._calculate_metrics(self.storage.list_events(run_id), started)
            metrics["run_success"] = final_status == RunStatus.PASSED
            model_name = self._reported_model(self.storage.list_events(run_id))
            self.storage.transition_run(
                run_id,
                final_status,
                ended_at=datetime.now(UTC),
                validation_status=validation_status,
                metrics=metrics,
                error=error,
                model_name=model_name,
            )
        except Exception as exc:
            error = str(exc)
            current = self.storage.get_run(run_id)
            if current and RunStatus(current["status"]) not in TERMINAL_STATUSES:
                await recorder.emit(
                    EventDraft(
                        type=EventType.RUN_FAILED,
                        source="exagium",
                        payload={"status": RunStatus.ERROR, "error": error},
                    )
                )
                metrics = self._calculate_metrics(self.storage.list_events(run_id), started)
                metrics["run_success"] = False
                model_name = self._reported_model(self.storage.list_events(run_id))
                self.storage.transition_run(
                    run_id,
                    RunStatus.ERROR,
                    ended_at=datetime.now(UTC),
                    exit_code=agent_exit_code,
                    validation_status=validation_status,
                    metrics=metrics,
                    error=error,
                    model_name=model_name,
                )
        finally:
            if workspace is not None:
                try:
                    await workspace.cleanup()
                except ExagiumError as cleanup_error:
                    error = f"{error}; {cleanup_error}" if error else str(cleanup_error)

        row = self.storage.get_run(run_id)
        assert row is not None
        return RunOutcome(
            run_id=run_id,
            status=RunStatus(row["status"]),
            agent_exit_code=row["exit_code"],
            duration_ms=int((time.perf_counter() - started) * 1000),
            validation_status=row["validation_status"],
            workspace_path=Path(row["workspace_path"]) if row["workspace_path"] else None,
            metrics=row["metrics"],
            error=error or row["error"],
        )

    @staticmethod
    def _calculate_metrics(events: list[dict[str, Any]], started: float) -> dict[str, Any]:
        types = [event["type"] for event in events]
        usage = next(
            (event["payload"] for event in reversed(events) if event["type"] == "USAGE_REPORTED"),
            {},
        )
        tokens_input = usage.get("input_tokens")
        tokens_output = usage.get("output_tokens")
        tokens_total = usage.get("total_tokens")
        if (
            tokens_total is None
            and isinstance(tokens_input, int)
            and isinstance(tokens_output, int)
        ):
            tokens_total = tokens_input + tokens_output
        return {
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "event_count": len(events),
            "command_count": types.count("COMMAND_STARTED"),
            "tool_call_count": types.count("TOOL_STARTED"),
            "file_change_count": types.count("FILE_CHANGED"),
            "validation_count": types.count("VALIDATION_COMPLETED"),
            "tokens_input": tokens_input,
            "tokens_output": tokens_output,
            "tokens_total": tokens_total,
            "cost": usage.get("cost"),
        }

    @staticmethod
    def _reported_model(events: list[dict[str, Any]]) -> str | None:
        # Adapter 在启动前不一定知道用户路由到的模型，因此从真实事件中回填。
        for event in events:
            payload = event.get("payload")
            if not isinstance(payload, dict):
                continue
            model = payload.get("model")
            if isinstance(model, str) and model.strip() and model != "<synthetic>":
                return model
        return None
