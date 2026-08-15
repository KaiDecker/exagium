from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine

from exagium.storage.orm import Base


def create_database_engine(path: Path) -> Engine:
    path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{path.as_posix()}", future=True)


def initialize_database(engine: Engine) -> None:
    Base.metadata.create_all(engine)
