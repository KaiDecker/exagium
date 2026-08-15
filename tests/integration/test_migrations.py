from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_migrations_build_current_schema_from_empty_database(sandbox_path: Path) -> None:
    database_path = sandbox_path / "migrations.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")

    command.upgrade(config, "0001_initial_schema")

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == {
        "agents",
        "alembic_version",
        "artifacts",
        "events",
        "experiments",
        "runs",
        "tasks",
        "validation_results",
    }
    assert "variant_id" not in {column["name"] for column in inspector.get_columns("runs")}
    engine.dispose()

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    inspector = inspect(engine)
    assert "variant_id" in {column["name"] for column in inspector.get_columns("runs")}
    assert "ix_runs_variant_id" in {
        index["name"] for index in inspector.get_indexes("runs")
    }
    engine.dispose()

    command.check(config)
