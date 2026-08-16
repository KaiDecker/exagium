from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from exagium.agents.claude_cli import ClaudeCliAdapter
from exagium.agents.codex_cli import CodexCliAdapter
from exagium.config import Settings
from exagium.core.models import (
    CommandSpec,
    ExperimentManifest,
    ExperimentVariant,
    RepoSpec,
    TaskManifest,
)
from exagium.experiments.service import ExperimentService
from exagium.storage.db import create_database_engine
from exagium.storage.repositories import Storage


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


@pytest.mark.asyncio
async def test_experiment_repeats_runs_sequentially_and_persists_membership(
    sandbox_path: Path,
) -> None:
    repo = sandbox_path / "source"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.name", "Exagium Test")
    git(repo, "config", "user.email", "exagium@example.invalid")
    (repo / "result.txt").write_text("broken", encoding="utf-8")
    git(repo, "add", "result.txt")
    git(repo, "commit", "-m", "initial")

    fake_agent = Path(__file__).parents[1] / "fixtures" / "fake_agent.py"
    adapter = CodexCliAdapter(executable=sys.executable, exec_prefix=(str(fake_agent),))
    settings = Settings.load(sandbox_path / "state")
    storage = Storage(create_database_engine(settings.database_path))
    task = TaskManifest(
        id="repeated-fix",
        name="Repeated fake fix",
        repo=RepoSpec(path=repo, base_ref="HEAD"),
        prompt="Fix result.txt",
        validation=[
            CommandSpec(
                name="result check",
                command=(
                    f'"{sys.executable}" -c "from pathlib import Path; '
                    "assert Path('result.txt').read_text() == 'fixed'\""
                ),
            )
        ],
    )
    experiment = ExperimentManifest(
        id="fake-stability",
        name="Fake stability",
        task=Path("unused.yaml"),
        variants=[ExperimentVariant(id="fake-default", agent="codex", repeat=3)],
    )
    service = ExperimentService(
        settings=settings,
        storage=storage,
        adapters={"codex": adapter},
    )

    outcome = await service.execute(experiment, task)

    assert outcome.runs == 3
    assert outcome.passed == 3
    assert outcome.success_rate == 100
    assert outcome.median_tokens == 15
    assert len(outcome.run_ids) == 3
    rows = storage.list_experiment_runs(experiment.id)
    assert len(rows) == 3
    assert {row["variant_id"] for row in rows} == {"fake-default"}
    assert all(row["status"] == "PASSED" for row in rows)
    stored = storage.get_experiment(experiment.id)
    assert stored is not None
    assert stored["configuration"]["variants"][0]["repeat"] == 3


@pytest.mark.asyncio
async def test_experiment_runs_codex_and_claude_variants_together(sandbox_path: Path) -> None:
    repo = sandbox_path / "source"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.name", "Exagium Test")
    git(repo, "config", "user.email", "exagium@example.invalid")
    (repo / "result.txt").write_text("broken", encoding="utf-8")
    git(repo, "add", "result.txt")
    git(repo, "commit", "-m", "initial")

    fixtures = Path(__file__).parents[1] / "fixtures"
    codex = CodexCliAdapter(
        executable=sys.executable,
        exec_prefix=(str(fixtures / "fake_agent.py"),),
    )
    claude = ClaudeCliAdapter(
        executable=sys.executable,
        print_prefix=(str(fixtures / "fake_claude_agent.py"),),
    )
    settings = Settings.load(sandbox_path / "state")
    storage = Storage(create_database_engine(settings.database_path))
    task = TaskManifest(
        id="cross-agent-fix",
        name="Cross-agent fake fix",
        repo=RepoSpec(path=repo, base_ref="HEAD"),
        prompt="Fix result.txt",
        validation=[
            CommandSpec(
                name="result check",
                command=(
                    f'"{sys.executable}" -c "from pathlib import Path; '
                    "assert Path('result.txt').read_text().startswith('fixed')\""
                ),
            )
        ],
    )
    experiment = ExperimentManifest(
        id="cross-agent-stability",
        name="Cross-agent stability",
        task=Path("unused.yaml"),
        variants=[
            ExperimentVariant(id="codex-default", agent="codex"),
            ExperimentVariant(id="claude-default", agent="claude"),
        ],
    )

    outcome = await ExperimentService(
        settings=settings,
        storage=storage,
        adapters={"codex": codex, "claude": claude},
    ).execute(experiment, task)

    assert outcome.runs == 2
    assert outcome.passed == 2
    rows = storage.list_experiment_runs(experiment.id)
    assert {(row["variant_id"], row["agent_name"]) for row in rows} == {
        ("codex-default", "codex"),
        ("claude-default", "claude"),
    }
