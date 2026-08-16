from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from exagium.config import Settings
from exagium.core.errors import ExagiumError
from exagium.experiments.compare import CompareService
from exagium.statistics.intervals import wilson_interval
from exagium.storage.db import create_database_engine
from exagium.storage.repositories import Storage


def _median(values: list[int | float | None]) -> float | None:
    present = [
        value for value in values if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    return float(median(present)) if present else None


def _run_metrics(
    rows: list[dict[str, Any]],
    *,
    confidence_level: float = 0.95,
) -> dict[str, Any]:
    total = len(rows)
    passed = sum(row["status"] == "PASSED" for row in rows)
    failed = sum(row["status"] == "FAILED" for row in rows)
    evaluable_runs = passed + failed
    interval = wilson_interval(passed, evaluable_runs, confidence_level=confidence_level)
    return {
        "runs": total,
        "passed": passed,
        "failed": failed,
        "errors": sum(row["status"] == "ERROR" for row in rows),
        "evaluable_runs": evaluable_runs,
        "success_rate": round(passed / evaluable_runs * 100, 2) if evaluable_runs else None,
        "success_interval": (
            {
                "lower": round(interval.lower * 100, 2),
                "upper": round(interval.upper * 100, 2),
                "confidence_level": interval.confidence_level,
                "method": "wilson",
            }
            if interval
            else None
        ),
        "median_duration_ms": _median([row["metrics"].get("duration_ms") for row in rows]),
        "median_tokens": _median([row["metrics"].get("tokens_total") for row in rows]),
    }


def _experiment_view(storage: Storage, row: dict[str, Any]) -> dict[str, Any]:
    runs = storage.list_experiment_runs(row["id"])
    confidence_level = float(
        row["configuration"].get("analysis", {}).get("confidence_level", 0.95)
    )
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        grouped[run["variant_id"] or "unassigned"].append(run)
    variants = [
        {
            "id": variant_id,
            **_run_metrics(variant_runs, confidence_level=confidence_level),
        }
        for variant_id, variant_runs in sorted(grouped.items())
    ]
    return {
        **row,
        "metrics": _run_metrics(runs, confidence_level=confidence_level),
        "variants": variants,
    }


def _frontend_dist() -> Path | None:
    configured = os.getenv("EXAGIUM_FRONTEND_DIST")
    candidates = [
        Path(configured).expanduser() if configured else None,
        Path(__file__).resolve().parents[3] / "frontend" / "dist",
    ]
    return next((path.resolve() for path in candidates if path and path.is_dir()), None)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or Settings.load()
    resolved_settings.ensure_directories()
    storage = Storage(create_database_engine(resolved_settings.database_path))
    storage.initialize()

    app = FastAPI(
        title="Exagium API",
        version="0.1.0",
        description="Read-only API for local agent runs, traces, experiments, and comparisons.",
    )
    app.state.settings = resolved_settings
    app.state.storage = storage
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "database": str(resolved_settings.database_path)}

    @app.get("/api/agents")
    def agents() -> list[dict[str, Any]]:
        return storage.list_agents()

    @app.get("/api/tasks")
    def tasks() -> list[dict[str, Any]]:
        return storage.list_tasks()

    @app.get("/api/tasks/{task_id}")
    def task_detail(task_id: str) -> dict[str, Any]:
        row = storage.get_task(task_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
        return row

    @app.get("/api/experiments")
    def experiments(
        limit: int = Query(default=50, ge=1, le=200),
    ) -> list[dict[str, Any]]:
        return [_experiment_view(storage, row) for row in storage.list_experiments(limit)]

    @app.get("/api/experiments/{experiment_id}")
    def experiment_detail(experiment_id: str) -> dict[str, Any]:
        row = storage.get_experiment(experiment_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Experiment not found: {experiment_id}")
        return {
            "experiment": _experiment_view(storage, row),
            "runs": storage.list_experiment_runs(experiment_id),
        }

    @app.get("/api/runs")
    def runs(limit: int = Query(default=50, ge=1, le=200)) -> list[dict[str, Any]]:
        return storage.list_runs(limit)

    def require_run(run_id: UUID) -> dict[str, Any]:
        row = storage.get_run(run_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
        return row

    @app.get("/api/runs/{run_id}")
    def run_detail(run_id: UUID) -> dict[str, Any]:
        return require_run(run_id)

    @app.get("/api/runs/{run_id}/events")
    def run_events(run_id: UUID) -> list[dict[str, Any]]:
        require_run(run_id)
        return storage.list_events(run_id)

    @app.get("/api/runs/{run_id}/validations")
    def run_validations(run_id: UUID) -> list[dict[str, Any]]:
        require_run(run_id)
        return storage.list_validations(run_id)

    @app.get("/api/runs/{run_id}/artifacts")
    def run_artifacts(run_id: UUID) -> list[dict[str, Any]]:
        require_run(run_id)
        allowed_root = resolved_settings.artifacts_path.resolve()
        result = []
        for artifact in storage.list_artifacts(run_id):
            path = Path(artifact["path"]).resolve()
            content = None
            if (
                path.is_relative_to(allowed_root)
                and path.is_file()
                and path.stat().st_size <= 200_000
            ):
                content = path.read_text(encoding="utf-8", errors="replace")
            result.append({**artifact, "content": content})
        return result

    @app.get("/api/compare")
    def compare(run_a: UUID, run_b: UUID) -> dict[str, Any]:
        try:
            result = CompareService(storage).compare(run_a, run_b)
        except ExagiumError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return result.model_dump(mode="json")

    frontend = _frontend_dist()
    if frontend:
        assets = frontend / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            del path
            return FileResponse(frontend / "index.html")
    else:

        @app.get("/", include_in_schema=False)
        def api_root() -> dict[str, str]:
            return {
                "name": "Exagium",
                "message": "Build frontend/ and restart exagium serve to enable the Web UI.",
                "docs": "/docs",
            }

    return app
