from __future__ import annotations

import asyncio
import json
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer

from exagium.agents.base import AgentAdapter
from exagium.agents.claude_cli import ClaudeCliAdapter
from exagium.agents.codex_cli import CodexCliAdapter
from exagium.config import Settings
from exagium.core.errors import ExagiumError
from exagium.core.models import load_experiment_manifest, load_task_manifest
from exagium.core.status import RunStatus
from exagium.experiments.compare import CompareService
from exagium.experiments.service import ExperimentService
from exagium.runner.run_service import RunService
from exagium.storage.db import create_database_engine
from exagium.storage.repositories import Storage
from exagium.trace.signatures import SemanticStep

app = typer.Typer(
    name="exagium",
    help="Bring your own agent. Run it, trace it, evaluate it, compare it.",
    no_args_is_help=True,
)
runs_app = typer.Typer(help="Inspect persisted runs.", no_args_is_help=True)
experiment_app = typer.Typer(help="Run repeatable agent experiments.", no_args_is_help=True)
app.add_typer(runs_app, name="runs")
app.add_typer(experiment_app, name="experiment")


def _agent_adapters() -> dict[str, AgentAdapter]:
    return {
        "codex": CodexCliAdapter(),
        "claude": ClaudeCliAdapter(),
    }


def _storage(settings: Settings) -> Storage:
    storage = Storage(create_database_engine(settings.database_path))
    storage.initialize()
    return storage


def _render_check(ok: bool, label: str, detail: str | None = None) -> None:
    marker = (
        typer.style("OK", fg=typer.colors.GREEN) if ok else typer.style("FAIL", fg=typer.colors.RED)
    )
    suffix = f"\n  {detail}" if detail else ""
    typer.echo(f"{marker} {label}{suffix}")


def _render_semantic_step(step: SemanticStep | None) -> str:
    if step is None:
        return "<no step>"
    signature = str(step.signature)
    detail = step.detail
    outcome = step.outcome
    suffix = f" | {detail}" if detail else ""
    if outcome:
        suffix += f" [{outcome}]"
    return f"{signature}{suffix}"


@app.command()
def doctor(
    component: Annotated[
        str | None,
        typer.Argument(help="Optional component: codex or claude"),
    ] = None,
    home: Annotated[Path | None, typer.Option(help="Exagium state directory.")] = None,
) -> None:
    """检查运行 Exagium 所需的本地工具和状态。"""
    adapters = _agent_adapters()
    if component not in {None, *adapters}:
        raise typer.BadParameter("Supported agent components: codex, claude")
    typer.echo("Exagium Doctor\n")
    agent_results = {name: asyncio.run(adapter.doctor()) for name, adapter in adapters.items()}
    if component:
        result = agent_results[component]
        _render_check(result.available, component, result.version or result.error)
        if not result.available:
            raise typer.Exit(1)
        return

    settings = Settings.load(home)
    git_path = shutil.which("git")
    _render_check(git_path is not None, "git", git_path)
    for name, result in agent_results.items():
        _render_check(result.available, name, result.version or result.error)

    database_ok = False
    database_detail = str(settings.database_path)
    try:
        settings.ensure_directories()
        _storage(settings)
        with sqlite3.connect(settings.database_path) as connection:
            connection.execute("SELECT 1").fetchone()
        database_ok = True
    except Exception as exc:
        database_detail = str(exc)
    _render_check(database_ok, "database", database_detail)

    workspace_ok = False
    workspace_detail = str(settings.workspaces_path)
    try:
        with tempfile.TemporaryDirectory(dir=settings.workspaces_path):
            workspace_ok = True
    except OSError as exc:
        workspace_detail = str(exc)
    _render_check(workspace_ok, "workspace", workspace_detail)

    ready = bool(git_path and database_ok and workspace_ok and any(
        result.available for result in agent_results.values()
    ))
    typer.echo("\nReady." if ready else "\nNot ready.")
    if not ready:
        raise typer.Exit(1)


@app.command("run")
def run_task(
    task_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    agent: Annotated[str, typer.Option(help="Agent adapter name.")] = "codex",
    keep_workspace: Annotated[
        bool, typer.Option("--keep-workspace", help="Retain the isolated worktree after the run.")
    ] = False,
    timeout: Annotated[int | None, typer.Option(min=1, help="Override the agent timeout.")] = None,
    label: Annotated[
        str | None,
        typer.Option(help="Optional human label (reserved for experiments)."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable output."),
    ] = False,
    home: Annotated[Path | None, typer.Option(help="Exagium state directory.")] = None,
) -> None:
    """使用已安装的本地 Agent 运行单个任务。"""
    del label
    try:
        task = load_task_manifest(task_path)
        settings = Settings.load(home)
        adapters = _agent_adapters()
        if agent not in adapters:
            raise ExagiumError(f"Unsupported agent: {agent}")
        adapter = adapters[agent]
        doctor_result = asyncio.run(adapter.doctor())
        if not doctor_result.available:
            raise ExagiumError(doctor_result.error or f"Agent is unavailable: {agent}")
        service = RunService(settings=settings, storage=_storage(settings), adapter=adapter)
        outcome = asyncio.run(
            service.execute(task, keep_workspace=keep_workspace, timeout_seconds=timeout)
        )
    except ExagiumError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(2) from exc

    if json_output:
        typer.echo(outcome.model_dump_json(indent=2))
    else:
        color = {
            RunStatus.PASSED: typer.colors.GREEN,
            RunStatus.FAILED: typer.colors.YELLOW,
            RunStatus.ERROR: typer.colors.RED,
        }.get(outcome.status)
        typer.echo(typer.style(outcome.status, fg=color, bold=True))
        typer.echo(f"Run: {outcome.run_id}")
        typer.echo(f"Duration: {outcome.duration_ms} ms")
        typer.echo(f"Validation: {outcome.validation_status or 'not run'}")
        if outcome.error:
            typer.echo(f"Error: {outcome.error}")
    if outcome.status != RunStatus.PASSED:
        raise typer.Exit(1 if outcome.status == RunStatus.FAILED else 2)


@experiment_app.command("run")
def run_experiment(
    experiment_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    keep_workspace: Annotated[
        bool, typer.Option("--keep-workspace", help="Retain every experiment worktree.")
    ] = False,
    timeout: Annotated[int | None, typer.Option(min=1, help="Override each agent timeout.")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    home: Annotated[Path | None, typer.Option(help="Exagium state directory.")] = None,
) -> None:
    """按顺序运行实验中的每个变体。"""
    try:
        experiment = load_experiment_manifest(experiment_path)
        task = load_task_manifest(experiment.task)
        settings = Settings.load(home)
        adapters = _agent_adapters()
        requested_agents = {variant.agent for variant in experiment.variants}
        unsupported = sorted(requested_agents - adapters.keys())
        if unsupported:
            raise ExagiumError(f"Unsupported experiment agent(s): {', '.join(unsupported)}")
        for agent_name in sorted(requested_agents):
            result = asyncio.run(adapters[agent_name].doctor())
            if not result.available:
                raise ExagiumError(result.error or f"Agent is unavailable: {agent_name}")
        service = ExperimentService(
            settings=settings,
            storage=_storage(settings),
            adapters=adapters,
        )
        outcome = asyncio.run(
            service.execute(
                experiment,
                task,
                keep_workspace=keep_workspace,
                timeout_seconds=timeout,
            )
        )
    except ExagiumError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(2) from exc

    if json_output:
        typer.echo(outcome.model_dump_json(indent=2))
        return

    typer.echo(f"Experiment: {outcome.name}")
    typer.echo(f"Runs: {outcome.runs}")
    typer.echo(f"Passed: {outcome.passed}")
    typer.echo(f"Failed: {outcome.failed}")
    typer.echo(f"Errors: {outcome.errors}")
    typer.echo(f"Success rate: {outcome.success_rate:.2f}%")
    if outcome.median_duration_ms is not None:
        typer.echo(f"Median duration: {outcome.median_duration_ms:.0f} ms")
    if outcome.median_tokens is not None:
        typer.echo(f"Median tokens: {outcome.median_tokens:.0f}")
    for variant in outcome.variants:
        typer.echo(
            f"  {variant.label}: {variant.passed}/{variant.runs} passed "
            f"({variant.success_rate:.2f}%)"
        )


@app.command("compare")
def compare_runs(
    run_a: UUID,
    run_b: UUID,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    home: Annotated[Path | None, typer.Option(help="Exagium state directory.")] = None,
) -> None:
    """对比两条已结束的运行并显示首次语义分歧。"""
    try:
        comparison = CompareService(_storage(Settings.load(home))).compare(run_a, run_b)
    except ExagiumError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(2) from exc

    if json_output:
        typer.echo(comparison.model_dump_json(indent=2))
        return

    typer.echo(f"Run A: {comparison.run_a.id}  {comparison.run_a.status}")
    typer.echo(f"Run B: {comparison.run_b.id}  {comparison.run_b.status}")
    if not comparison.same_task:
        typer.echo("Warning: the runs belong to different tasks.")
    divergence = comparison.first_divergence
    if divergence is None:
        typer.echo("No semantic divergence found.")
        return
    typer.echo(f"\nFirst divergence: step {divergence.step}")
    typer.echo(f"Run A: {_render_semantic_step(divergence.run_a)}")
    typer.echo(f"Run B: {_render_semantic_step(divergence.run_b)}")


@app.command("serve")
def serve(
    host: Annotated[str, typer.Option(help="Address for the local Web UI.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(min=1, max=65535)] = 8000,
    home: Annotated[Path | None, typer.Option(help="Exagium state directory.")] = None,
) -> None:
    """启动只读 API 和已构建的 Web UI。"""
    import uvicorn

    from exagium.api.app import create_app

    uvicorn.run(create_app(Settings.load(home)), host=host, port=port, log_level="info")


@runs_app.command("list")
def list_runs(
    limit: Annotated[int, typer.Option(min=1, max=200)] = 20,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    home: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """列出最近的运行。"""
    rows = _storage(Settings.load(home)).list_runs(limit)
    if json_output:
        typer.echo(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    for row in rows:
        typer.echo(f"{row['id']}  {row['status']:<10}  {row['task_id']}  {row['agent_name']}")


@runs_app.command("show")
def show_run(
    run_id: UUID,
    events: Annotated[bool, typer.Option(help="Include the normalized trace.")] = False,
    home: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """显示已持久化的运行及其验证结果。"""
    storage = _storage(Settings.load(home))
    row = storage.get_run(run_id)
    if row is None:
        typer.echo(f"Run not found: {run_id}", err=True)
        raise typer.Exit(1)
    result = {"run": row, "validations": storage.list_validations(run_id)}
    if events:
        result["events"] = storage.list_events(run_id)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
