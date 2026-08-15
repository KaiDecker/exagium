from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from exagium.api.app import create_app
from exagium.config import Settings
from exagium.core.events import AgentEvent, EventType
from exagium.core.models import (
    AgentMetadata,
    CommandSpec,
    ExperimentManifest,
    ExperimentVariant,
    RepoSpec,
    TaskManifest,
    ValidationOutcome,
)
from exagium.core.status import RunStatus


def create_run(
    client: TestClient,
    *,
    task: TaskManifest,
    agent_profile_id: str,
    status: RunStatus,
    variant_id: str,
    duration_ms: int,
    tokens: int | None,
    extra_edit: bool = False,
) -> UUID:
    storage = client.app.state.storage
    run_id = uuid4()
    storage.create_run(
        run_id=run_id,
        task_id=task.id,
        agent_profile_id=agent_profile_id,
        agent=AgentMetadata(name="fake", version="1.0"),
        experiment_id="api-experiment",
        variant_id=variant_id,
    )
    storage.transition_run(run_id, RunStatus.PREPARING)
    storage.transition_run(run_id, RunStatus.RUNNING)
    events = [
        (EventType.COMMAND_COMPLETED, {"command": 'rg "needle"', "exit_code": 0}),
        (EventType.FILE_CHANGED, {"path": "src/app.py"}),
    ]
    if extra_edit:
        events.append((EventType.FILE_CHANGED, {"path": "src/other.py"}))
    else:
        events.append(
            (EventType.COMMAND_COMPLETED, {"command": "python -m pytest", "exit_code": 0})
        )
    for seq, (event_type, payload) in enumerate(events, start=1):
        storage.add_event(
            AgentEvent(
                run_id=run_id,
                seq=seq,
                type=event_type,
                source="fake",
                payload=payload,
            )
        )
    storage.transition_run(run_id, RunStatus.VALIDATING)
    storage.transition_run(
        run_id,
        status,
        metrics={"duration_ms": duration_ms, "tokens_total": tokens},
        validation_status="PASSED" if status == RunStatus.PASSED else "FAILED",
    )
    return run_id


def test_health_and_missing_resource(sandbox_path: Path) -> None:
    client = TestClient(create_app(Settings.load(sandbox_path / "state")))

    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/runs").json() == []
    assert client.get("/api/tasks/missing").status_code == 404


def test_app_serves_configured_spa_for_ui_routes(
    sandbox_path: Path,
    monkeypatch,
) -> None:
    frontend = sandbox_path / "dist"
    (frontend / "assets").mkdir(parents=True)
    (frontend / "index.html").write_text("<html>Exagium UI</html>", encoding="utf-8")
    monkeypatch.setenv("EXAGIUM_FRONTEND_DIST", str(frontend))
    client = TestClient(create_app(Settings.load(sandbox_path / "state")))

    assert "Exagium UI" in client.get("/").text
    assert "Exagium UI" in client.get("/runs/example").text


def test_read_api_exposes_experiment_run_evidence_and_comparison(sandbox_path: Path) -> None:
    settings = Settings.load(sandbox_path / "state")
    client = TestClient(create_app(settings))
    storage = client.app.state.storage
    repo = sandbox_path / "repo"
    repo.mkdir()
    task = TaskManifest(
        id="api-task",
        name="API task",
        repo=RepoSpec(path=repo),
        prompt="Fix it",
        validation=[CommandSpec(name="tests", command="pytest")],
    )
    experiment = ExperimentManifest(
        id="api-experiment",
        name="API experiment",
        task=Path("task.yaml"),
        variants=[ExperimentVariant(id="default", repeat=2)],
    )
    storage.register_task(task)
    storage.register_experiment(experiment, task.id)
    agent_profile_id = storage.register_agent(
        AgentMetadata(name="fake", version="1.0"),
        adapter_type="fake",
        executable="fake",
    )
    passed = create_run(
        client,
        task=task,
        agent_profile_id=agent_profile_id,
        status=RunStatus.PASSED,
        variant_id="default",
        duration_ms=100,
        tokens=50,
    )
    failed = create_run(
        client,
        task=task,
        agent_profile_id=agent_profile_id,
        status=RunStatus.FAILED,
        variant_id="default",
        duration_ms=300,
        tokens=None,
        extra_edit=True,
    )
    storage.add_validation(
        passed,
        ValidationOutcome(
            name="tests",
            command="pytest",
            status="PASSED",
            exit_code=0,
            duration_ms=5,
            stdout="2 passed",
            stderr="",
        ),
    )
    artifact_dir = settings.artifacts_path / str(passed)
    artifact_dir.mkdir(parents=True)
    diff_path = artifact_dir / "diff.patch"
    diff_path.write_text("+fixed\n", encoding="utf-8")
    storage.add_artifact(passed, "git_diff", diff_path)

    experiments = client.get("/api/experiments").json()
    assert experiments[0]["metrics"]["runs"] == 2
    assert experiments[0]["metrics"]["success_rate"] == 50
    assert experiments[0]["metrics"]["median_duration_ms"] == 200
    assert experiments[0]["metrics"]["median_tokens"] == 50
    assert client.get(f"/api/runs/{passed}").json()["status"] == "PASSED"
    assert len(client.get(f"/api/runs/{passed}/events").json()) == 3
    assert client.get(f"/api/runs/{passed}/validations").json()[0]["stdout"] == "2 passed"
    assert client.get(f"/api/runs/{passed}/artifacts").json()[0]["content"] == "+fixed\n"
    comparison = client.get(f"/api/compare?run_a={passed}&run_b={failed}").json()
    assert comparison["first_divergence"]["step"] == 3
    assert comparison["first_divergence"]["run_a"]["signature"] == "TEST"
    assert comparison["first_divergence"]["run_b"]["signature"] == "EDIT"
    assert client.get(f"/api/compare?run_a={passed}&run_b={passed}").status_code == 400
