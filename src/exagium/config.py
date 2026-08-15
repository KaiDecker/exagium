from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    home: Path

    @classmethod
    def load(cls, home: Path | None = None) -> Settings:
        configured = home or (Path(value) if (value := os.getenv("EXAGIUM_HOME")) else None)
        return cls(home=(configured or Path.cwd() / ".exagium").resolve())

    @property
    def database_path(self) -> Path:
        return self.home / "exagium.db"

    @property
    def workspaces_path(self) -> Path:
        return self.home / "workspaces"

    @property
    def artifacts_path(self) -> Path:
        return self.home / "artifacts"

    def ensure_directories(self) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        self.workspaces_path.mkdir(parents=True, exist_ok=True)
        self.artifacts_path.mkdir(parents=True, exist_ok=True)
